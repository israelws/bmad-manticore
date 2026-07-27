#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Corrective spatial normalize: crop out baked-in frame defects and reframe.

Usage:
    uv run {skill-root}/scripts/normalize_source.py {projects-path}/<slug>/raw/<take> \
        -o {projects-path}/<slug>/raw/<take>-normalized.mp4 \
        [--auto | --crop W:H:X:Y] [--offset-x N] [--offset-y N] \
        [--target-aspect 16:9] [--output-size WxH]

Why this exists:
    A 4K take arrived with a decorative frame RECORDED INTO THE PIXELS (a
    black outer border plus a rounded orange ring, an Ecamm frame effect left
    on during capture) and the subject framed about 5 percent left of centre.
    The pipeline had no way to fix it. cut/edl.json is purely TEMPORAL,
    {source, start, end}, and the renderers bake those spans with no crop,
    scale or position transform anywhere. So a baked-in border could only be
    corrected by hand, or downstream in the creator's own editor.

    This is the missing spatial stage.

THE PROPERTY THAT MATTERS: THIS TOUCHES NO TIMECODES.
    A spatial crop moves nothing in time. Every frame keeps its presentation
    timestamp, the duration is unchanged, and the audio is copied through
    untouched. So an existing transcript, EDL, cutplan, beat table and
    boundary-frame set all stay valid against the corrected master.

    DO NOT re-transcribe. DO NOT re-cut. DO NOT re-plan beats. An agent that
    "helpfully" rebuilds them after a normalize is throwing away the
    creator's approved work for no reason. The script asserts the duration
    is preserved and refuses to publish if it is not, so this is a checked
    guarantee rather than a promise.

Where it belongs in the pipeline:
    Immediately after preflight, BEFORE beats and graphics. Overlays are
    positioned against the canvas, so normalizing after graphics would force
    every overlay to be repositioned. The corrected master is registered as
    the project source (project.json `sources`, `cfr_master`) and every later
    step inherits it automatically.

    Keep this distinct from CREATIVE reframing. Corrective normalize is
    global, defect-driven, and belongs here. Motion zooms and punch-ins are
    per-moment emphasis and belong in the beats stage, on the already-clean
    canvas.

Contract:
    input     a media file, plus a crop rectangle: --crop W:H:X:Y explicitly,
              or --auto to infer it from the same border detection preflight
              uses.
    reframe   --offset-x / --offset-y pan the crop window (positive is right
              and down) to recentre an off-centre subject, clamped so the
              window never leaves the frame.
    aspect    --target-aspect (e.g. 16:9) shrinks the crop to an exact
              aspect, so a corrected master is never subtly non-standard.
    size      --output-size WxH scales the cropped result back up, so the
              delivery resolution is unchanged by the correction. Omit to
              keep the cropped size.
    output    a corrected CFR master at -o, with the source's frame rate and
              its audio stream copied. The path is reported as
              `normalized_master` for the caller to record in project.json.
    summary   json.dumps on stdout: source, output, crop, output_size,
              source_duration, output_duration, timecodes_preserved.

Exit codes: 0 ok, 1 failure (probe, encode, or a duration change), 2 usage.

STATUS: implemented (crop geometry covered by
scripts/tests/test-normalize_source.py; encode path covered by its
synthesized-fixture integration test).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # noqa: E402
import composite_core as core  # noqa: E402
import preflight  # noqa: E402

# A normalize that changes the duration has broken the one guarantee this
# script makes, so the tolerance is tight: a frame or two, not a second.
DURATION_TOLERANCE_S = 0.1


def parse_crop(text):
    """'W:H:X:Y' to an (x, y, w, h) rectangle (pure). Raises ValueError."""
    parts = text.split(":")
    if len(parts) != 4:
        raise ValueError("crop must be W:H:X:Y")
    try:
        w, h, x, y = (int(p) for p in parts)
    except ValueError:
        raise ValueError("crop values must be integers") from None
    if w <= 0 or h <= 0 or x < 0 or y < 0:
        raise ValueError("crop must have positive size and non-negative origin")
    return (x, y, w, h)


def parse_size(text):
    """'WxH' to an (w, h) pair (pure). Raises ValueError."""
    parts = text.lower().split("x")
    if len(parts) != 2:
        raise ValueError("size must be WxH")
    try:
        w, h = (int(p) for p in parts)
    except ValueError:
        raise ValueError("size values must be integers") from None
    if w <= 0 or h <= 0:
        raise ValueError("size must be positive")
    return (w, h)


def parse_aspect(text):
    """'16:9' or '1.777' to a float (pure). Raises ValueError."""
    if ":" in text:
        a, _, b = text.partition(":")
        num, den = float(a), float(b)
        if den == 0:
            raise ValueError("aspect denominator must not be zero")
        return num / den
    value = float(text)
    if value <= 0:
        raise ValueError("aspect must be positive")
    return value


def shift_crop(rect, dx, dy, frame_w, frame_h):
    """Pan a crop window, clamped inside the frame (pure).

    Clamping rather than erroring is deliberate: recentring is a taste
    adjustment the creator nudges, and a nudge that would run off the edge
    should stop at the edge, not fail the run.
    """
    x, y, w, h = rect
    x = max(0, min(int(round(x + dx)), max(0, frame_w - w)))
    y = max(0, min(int(round(y + dy)), max(0, frame_h - h)))
    return (x, y, w, h)


def fit_aspect(rect, aspect):
    """Shrink a rect to an exact aspect, keeping its centre (pure).

    Only ever shrinks. Growing could pull the baked-in border back into the
    frame, which is the entire thing being removed.
    """
    x, y, w, h = rect
    if aspect <= 0:
        return rect
    target_w = core.even(min(w, h * aspect))
    target_h = core.even(min(h, w / aspect))
    if target_w / max(1, target_h) > aspect:
        target_w = core.even(target_h * aspect)
    else:
        target_h = core.even(target_w / aspect)
    nx = x + (w - target_w) // 2
    ny = y + (h - target_h) // 2
    return (max(0, core.even(nx)), max(0, core.even(ny)),
            max(2, target_w), max(2, target_h))


def clamp_rect(rect, frame_w, frame_h):
    """Keep a rect inside the frame, with even dimensions (pure)."""
    x, y, w, h = rect
    w = core.even(max(2, min(w, frame_w)))
    h = core.even(max(2, min(h, frame_h)))
    x = max(0, min(core.even(x), frame_w - w))
    y = max(0, min(core.even(y), frame_h - h))
    return (x, y, w, h)


def build_normalize_command(src, dst, rect, fps, output_size=None,
                            encoder="libx264", crf=18, height=None):
    """ffmpeg argv cropping (and optionally rescaling) a source (pure).

    fps is forced so the corrected master stays constant frame rate, and the
    audio is stream-copied: no re-encode, no resample, no drift.
    """
    x, y, w, h = rect
    vf = [f"crop={w}:{h}:{x}:{y}"]
    if output_size:
        ow, oh = output_size
        vf.append(f"scale={core.even(ow)}:{core.even(oh)}")
    vf.append(f"fps={fps}")
    argv = ["ffmpeg", "-y", "-hide_banner", *core.encoder_init_flags(encoder),
            "-i", str(src)]
    chain = ",".join(vf)
    if core.encoder_needs_hwupload(encoder):
        chain += ",format=nv12,hwupload"
    argv += ["-vf", chain]
    if core.is_hardware_encoder(encoder):
        argv += ["-c:v", encoder,
                 "-b:v", f"{preflight.master_bitrate_for(height or h)}k"]
        if encoder.endswith("_videotoolbox"):
            argv += ["-allow_sw", "1"]
    else:
        argv += ["-c:v", encoder, "-crf", str(crf), "-preset", "medium"]
    if not core.encoder_needs_hwupload(encoder):
        argv += ["-pix_fmt", "yuv420p"]
    argv += ["-c:a", "copy", "-movflags", "+faststart", str(dst)]
    return argv


def auto_rect(media, duration, width, height, samples):
    """Infer the active-content rectangle, or None when the source is clean.

    Shares preflight's detector so --auto corrects exactly what QC halted on;
    two implementations would inevitably disagree about where the border is.
    """
    verdict = preflight.qc_source(media, duration, width, height,
                                  samples=samples)
    rect = verdict.get("active_rect")
    return (tuple(rect) if rect else None), verdict


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("media", help="path to the source media file")
    p.add_argument("-o", "--output", required=True,
                   help="path for the corrected master")
    p.add_argument("--crop", default=None,
                   help="explicit crop rectangle W:H:X:Y")
    p.add_argument("--auto", action="store_true",
                   help="infer the crop from the detected border ring")
    p.add_argument("--offset-x", type=int, default=0,
                   help="pan the crop window right (negative for left) to "
                        "recentre the subject")
    p.add_argument("--offset-y", type=int, default=0,
                   help="pan the crop window down (negative for up)")
    p.add_argument("--target-aspect", default=None,
                   help="shrink the crop to an exact aspect, e.g. 16:9")
    p.add_argument("--output-size", default=None,
                   help="scale the cropped result to WxH (default: keep the "
                        "cropped size)")
    p.add_argument("--qc-samples", type=int,
                   default=preflight.DEFAULT_QC_SAMPLES)
    p.add_argument("--crf", type=int, default=18)
    args = p.parse_args(argv)

    media = Path(args.media)
    if not media.is_file():
        print(f"normalize_source: media not found: {media}", file=sys.stderr)
        return 2
    if bool(args.crop) == bool(args.auto):
        print("normalize_source: pass exactly one of --crop or --auto",
              file=sys.stderr)
        return 2

    info = preflight.probe_media(media)
    if info is None:
        print(f"normalize_source: cannot probe {media}", file=sys.stderr)
        return 1
    width, height = info["width"], info["height"]
    duration = info["duration"]
    fps = preflight.nearest_standard_rate(info["avg_frame_rate"])

    qc = None
    if args.auto:
        rect, qc = auto_rect(media, duration, width, height, args.qc_samples)
        if rect is None:
            print("normalize_source: no border ring detected; nothing to "
                  "correct. Pass --crop explicitly to reframe anyway.",
                  file=sys.stderr)
            return 1
    else:
        try:
            rect = parse_crop(args.crop)
        except ValueError as e:
            print(f"normalize_source: {e}", file=sys.stderr)
            return 2

    if args.offset_x or args.offset_y:
        rect = shift_crop(rect, args.offset_x, args.offset_y, width, height)
    if args.target_aspect:
        try:
            rect = fit_aspect(rect, parse_aspect(args.target_aspect))
        except ValueError as e:
            print(f"normalize_source: {e}", file=sys.stderr)
            return 2
    rect = clamp_rect(rect, width, height)

    output_size = None
    if args.output_size:
        try:
            output_size = parse_size(args.output_size)
        except ValueError as e:
            print(f"normalize_source: {e}", file=sys.stderr)
            return 2

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    encoder = core.pick_encoder("auto")
    tmp = output.with_name(f".{output.stem}.normalizing{output.suffix}")

    x, y, w, h = rect
    print(f"normalize_source: crop={w}:{h}:{x}:{y} from {width}x{height} "
          f"at {fps} ({encoder})", file=sys.stderr)
    cmd = build_normalize_command(media, tmp, rect, fps, output_size,
                                  encoder, args.crf, height)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        core.discard_render(tmp)
        print("normalize_source: encode failed:", file=sys.stderr)
        print(" ".join(cmd), file=sys.stderr)
        print(proc.stderr.strip()[-2000:], file=sys.stderr)
        return 1

    # The load-bearing assertion: a spatial correction must not have moved
    # anything in time, or every downstream artifact silently desyncs.
    out_duration = core.probe_duration(tmp)
    if out_duration is None:
        core.discard_render(tmp)
        print("normalize_source: corrected master has no readable duration",
              file=sys.stderr)
        return 1
    drift = abs(out_duration - (duration or out_duration))
    if drift > DURATION_TOLERANCE_S:
        core.discard_render(tmp)
        print(f"normalize_source: duration changed by {drift:.3f}s "
              f"({duration:.3f}s to {out_duration:.3f}s). A spatial crop must "
              "not move anything in time; refusing to publish, because the "
              "existing transcript and EDL would silently desync against "
              "this master.", file=sys.stderr)
        return 1

    core.publish_render(tmp, output)

    final_w, final_h = (output_size if output_size else (w, h))
    summary = {
        "source": str(media),
        "normalized_master": str(output.resolve()),
        "source_size": [width, height],
        "crop": f"{w}:{h}:{x}:{y}",
        "output_size": [core.even(final_w), core.even(final_h)],
        "fps": fps,
        "source_duration": round(duration, 3) if duration else None,
        "output_duration": round(out_duration, 3),
        "timecodes_preserved": True,
        "auto_detected": bool(args.auto),
    }
    if qc:
        summary["qc_defects"] = qc["defects"]
    print(json.dumps(summary, indent=2))
    print("\nRegister this as the project source (project.json `sources` /"
          " `cfr_master`) so every later step inherits it.\n"
          "Timecodes are unchanged: the existing transcript, EDL, cutplan "
          "and beat table stay valid. Do NOT re-transcribe or re-cut.",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
