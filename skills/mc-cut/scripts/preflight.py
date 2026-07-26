#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Source preflight for the cut stage: probe, VFR detection, disk check,
CFR remux, and QC frame extraction. Runs before any transcription or render.

Usage:
    uv run {skill-root}/scripts/preflight.py raw/<take> [raw/<other> ...] \
        [--remux] [--remux-suffix -cfr] [--qc-frames cut/qc/] \
        [--disk-path <dir>] [--json]

Contract:
    probe    each media file is ffprobed for its video stream (codec, width,
             height, r_frame_rate, avg_frame_rate) and container duration.
             A file is VFR when r_frame_rate and avg_frame_rate disagree by
             more than 0.5 percent.
    disk     free bytes on --disk-path (default: the first file's directory)
             are checked BEFORE any remux write against a rough estimate:
             3x total source size (transcripts, previews, renders) plus the
             estimated CFR-master size of each planned remux (duration times
             the master bitrate for the source height). "ok" false means stop
             and tell the creator before rendering; when a --remux is planned
             and the estimate does not fit, the remux is refused (exit 1, the
             summary still printed) so a runaway master is never written.
    remux    with --remux, each VFR file is re-encoded to constant frame rate
             at the nearest standard rate (23.976, 24, 25, 29.97, 30, 50,
             59.94, 60) into <stem><suffix>.mp4 beside the original (audio
             copied; hardware encoder when available at the master bitrate
             for the source height, 2x the delivery ladder for headroom;
             libx264 crf 18 otherwise). Runs only after the disk gate passes.
             The remuxed path is reported as cfr_master so the caller records
             it in project.json sources as the project source of truth; every
             later step (transcription, EDL times, renders, timeline export)
             must use it, never the VFR original.
    qc       edge-defect QC that ASSERTS AND HALTS (exit 3). Several frames
             across each take (not just the first and last: a frame effect
             can be switched on mid-recording) are analysed for a flat
             decorative border ring and for an active area whose aspect does
             not match the container. On a hit the inferred active-content
             rectangle is reported and the stage stops, because a baked-in
             border cannot be fixed downstream: the EDL is time-only, so
             every later stage inherits the bad canvas. Fix with
             normalize_source.py, or pass --allow-qc-defects when the
             framing is intentional. --qc-frames <dir> additionally writes
             the sampled stills for the creator to eyeball.
    summary  json.dumps on stdout: per-file {path, codec, width, height,
             duration, fps, vfr, cfr_master, qc_frames, qc}, plus
             {"disk": {free_bytes, needed_bytes, ok}}, "all_cfr" and "qc_ok".

Exit codes: 0 ok (VFR found still exits 0; the caller reads "vfr" and
"all_cfr"), 1 probe/remux failure or disk refusal of a planned remux, 2
usage, 3 source QC defect (stop and get the creator's call).

STATUS: implemented (pure logic covered by scripts/tests/test-preflight.py;
probe/remux path covered by the synthesized-fixture integration test there).
"""

import argparse
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # noqa: E402
import composite_core as core  # noqa: E402

STANDARD_RATES = ("24000/1001", "24/1", "25/1", "30000/1001", "30/1",
                  "50/1", "60000/1001", "60/1")

# Frames sampled across a take for the edge-defect QC pass. More than two,
# because a frame effect can be switched on after recording starts.
DEFAULT_QC_SAMPLES = 7
# Analysis thumbnail size. Small on purpose: downscaling averages out sensor
# noise so a flat decorative border reads as genuinely flat.
QC_ANALYSIS_SIZE = (96, 54)
# Per-channel variance under which a ring of pixels counts as a flat colour.
DEFAULT_RING_VARIANCE = 12.0
# How far a border's colour must sit from the picture inside it before it is
# a decorative frame rather than just a dark scene.
DEFAULT_RING_DISTANCE = 24.0


def parse_rate(text):
    """'30000/1001' or '30' -> Fraction, None for unknown/zero sentinels."""
    if not text:
        return None
    try:
        f = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None
    return f if f > 0 else None


def is_vfr(r_rate, avg_rate, tolerance=0.005):
    """True when the container's nominal and average rates disagree by more
    than `tolerance` (fraction). Unknown rates count as VFR (must remux)."""
    r, avg = parse_rate(r_rate), parse_rate(avg_rate)
    if r is None or avg is None:
        return True
    return abs(float(r) - float(avg)) / float(r) > tolerance


def nearest_standard_rate(avg_rate):
    """The standard CFR rate string closest to the measured average rate."""
    avg = parse_rate(avg_rate)
    if avg is None:
        return "30/1"
    return min(STANDARD_RATES, key=lambda r: abs(float(Fraction(r)) - float(avg)))


def master_bitrate_for(height):
    """CFR-master video bitrate (kbps): 2x the delivery ladder for the source
    height, for master headroom. Unknown height falls back to the 1080 tier."""
    return core.bitrate_for(height or 1080) * 2


def estimate_master_bytes(duration, height, source_bytes):
    """Rough CFR-master output size: duration times the master bitrate.
    Unknown duration falls back to 2x the source file size."""
    if not duration:
        return source_bytes * 2
    return int(duration * master_bitrate_for(height) * 1000 / 8)


def remux_command(src, dst, rate, encoder="libx264", crf=18, height=None):
    """ffmpeg argv re-encoding src to CFR at `rate` (audio copied).
    Hardware encoders have no dependable CRF mode, so they take the master
    bitrate for the source height (videotoolbox additionally -allow_sw;
    vaapi additionally device init and an hwupload chain, and no forced
    -pix_fmt since the encoder receives hardware frames); libx264 takes
    -crf."""
    argv = ["ffmpeg", "-y", *core.encoder_init_flags(encoder), "-i", str(src)]
    vf = f"fps={rate}"
    if core.encoder_needs_hwupload(encoder):
        vf += ",format=nv12,hwupload"
    argv += ["-vf", vf]
    if core.is_hardware_encoder(encoder):
        argv += ["-c:v", encoder, "-b:v", f"{master_bitrate_for(height)}k"]
        if encoder.endswith("_videotoolbox"):
            argv += ["-allow_sw", "1"]
    else:
        argv += ["-c:v", encoder, "-crf", str(crf), "-preset", "fast"]
    if not core.encoder_needs_hwupload(encoder):
        argv += ["-pix_fmt", "yuv420p"]
    argv += ["-c:a", "copy", "-movflags", "+faststart", str(dst)]
    return argv


def probe_media(path):
    """First video stream facts + duration, or None on probe failure."""
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries",
         "stream=codec_name,width,height,r_frame_rate,avg_frame_rate"
         ":format=duration",
         "-print_format", "json", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    data = json.loads(proc.stdout)
    streams = data.get("streams") or []
    if not streams:
        return None
    s = streams[0]
    dur = data.get("format", {}).get("duration")
    return {
        "codec": s.get("codec_name"),
        "width": s.get("width"),
        "height": s.get("height"),
        "r_frame_rate": s.get("r_frame_rate"),
        "avg_frame_rate": s.get("avg_frame_rate"),
        "duration": float(dur) if dur is not None else None,
    }


def qc_sample_times(duration, samples=DEFAULT_QC_SAMPLES):
    """Timestamps to inspect across a take (pure).

    Two frames is not a QC pass. The original check looked at frame 0 and a
    frame half a second from the end, which cannot see a defect that starts
    mid-take (a frame effect toggled on after recording began). These sample
    evenly across the interior, avoiding the very first and last frames where
    fades and encoder warm-up live.
    """
    if not duration or duration <= 0:
        return [0.0]
    samples = max(2, samples)
    lo, hi = duration * 0.02, duration * 0.98
    if hi <= lo:
        return [max(0.0, duration / 2)]
    step = (hi - lo) / (samples - 1)
    return [round(lo + i * step, 3) for i in range(samples)]


def extract_qc_frames(media, qc_dir, duration, times=None):
    """QC stills across the take, for the creator to eyeball after a halt."""
    qc_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(media).stem
    written = []
    for i, t in enumerate(times if times is not None
                          else qc_sample_times(duration)):
        dest = qc_dir / f"{stem}-qc{i:02d}.jpg"
        proc = subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(media),
             "-frames:v", "1", "-q:v", "3", "-update", "1", str(dest)],
            capture_output=True, text=True,
        )
        if proc.returncode == 0 and dest.is_file():
            written.append(str(dest))
    return written


# --- source QC: edge defects ------------------------------------------------
#
# On the first real project a 4K take carried a decorative frame RECORDED
# INTO THE PIXELS: a black outer border plus a rounded orange ring, an Ecamm
# frame effect left on during capture, with the subject framed off-centre.
# It passed preflight, transcription, candidate detection, the EDL, gate 2
# and the preview render completely untouched. The creator caught it by eye
# after the cut was already locked.
#
# The step-2 QC pass named this exact defect class ("black edges, wrong
# aspect, letterboxed or cropped content") and still let it through, because
# it only EXTRACTED frames and left the looking to whoever happened to
# remember. QC that cannot halt is not QC, so this asserts and exits 3.
#
# It is deliberately a HALT-AND-ASK, not an auto-fix: a uniform edge can be
# legitimate (a dark set, a vignette, an intentional letterbox). The script
# reports the inferred active-content rectangle and stops; the creator
# confirms, and normalize_source.py does the correction.


def _px(pixels, w, i, x, y):
    o = ((y * w) + x) * 3
    return pixels[o], pixels[o + 1], pixels[o + 2]


def ring_pixels(pixels, w, h, depth):
    """The pixels exactly `depth` in from the frame edge (pure)."""
    out = []
    if depth < 0 or depth * 2 >= min(w, h):
        return out
    for x in range(depth, w - depth):
        out.append(_px(pixels, w, 0, x, depth))
        out.append(_px(pixels, w, 0, x, h - 1 - depth))
    for y in range(depth + 1, h - depth - 1):
        out.append(_px(pixels, w, 0, depth, y))
        out.append(_px(pixels, w, 0, w - 1 - depth, y))
    return out


def mean_color(px):
    """Per-channel mean of a pixel list (pure)."""
    if not px:
        return (0.0, 0.0, 0.0)
    n = len(px)
    return tuple(sum(p[c] for p in px) / n for c in range(3))


def max_channel_variance(px):
    """Largest per-channel variance across a pixel list (pure).

    A decorative border is a FLAT colour, so its variance is near zero, while
    real picture content at the frame edge varies. This is the whole
    discriminator."""
    if len(px) < 2:
        return 0.0
    means = mean_color(px)
    return max(
        sum((p[c] - means[c]) ** 2 for p in px) / len(px)
        for c in range(3)
    )


def color_distance(a, b):
    """Euclidean distance between two mean colours (pure)."""
    return sum((a[c] - b[c]) ** 2 for c in range(3)) ** 0.5


def detect_border_depth(pixels, w, h, var_limit=DEFAULT_RING_VARIANCE,
                        max_frac=0.25):
    """How many pixels of flat border ring the frame carries (pure).

    Walks inward from the edge while each successive ring is FLAT (low
    variance). Stops at the first ring carrying real picture detail. A
    multi-colour decorative frame (black outer border then an orange ring) is
    still one contiguous run of flat rings, so both layers are counted, which
    is what the real defect needed.

    Returns 0 when the outermost ring already carries picture content, which
    is the normal, healthy case.
    """
    limit = int(min(w, h) * max_frac)
    depth = 0
    while depth < limit:
        px = ring_pixels(pixels, w, h, depth)
        if not px or max_channel_variance(px) > var_limit:
            break
        depth += 1
    return depth


def border_is_distinct(pixels, w, h, depth, min_distance=DEFAULT_RING_DISTANCE):
    """True when the flat border differs from the picture inside it (pure).

    Guards the false positive that matters: a genuinely dark or flat SCENE
    whose edges happen to be uniform. If the border and the interior are the
    same colour there is no decorative frame, just a flat shot.
    """
    if depth <= 0:
        return False
    border = mean_color(ring_pixels(pixels, w, h, 0))
    inner = ring_pixels(pixels, w, h, depth + 1)
    if not inner:
        return False
    return color_distance(border, mean_color(inner)) >= min_distance


def active_rect(w, h, depth):
    """The content rectangle inside a border of `depth` (pure)."""
    return (depth, depth, w - 2 * depth, h - 2 * depth)


def scale_rect(rect, from_size, to_size):
    """Map a rectangle measured on a thumbnail onto the full frame (pure).

    Values round to even numbers because encoders reject odd dimensions.
    """
    fx, fy = from_size
    tx, ty = to_size
    sx, sy = tx / fx, ty / fy
    x, y, rw, rh = rect
    return (core.even(x * sx), core.even(y * sy),
            core.even(rw * sx), core.even(rh * sy))


def aspect_of(rect):
    """Width over height of a rectangle (pure)."""
    _, _, w, h = rect
    return (w / h) if h else 0.0


def sample_frame_rgb(media, t, w, h):
    """One frame as raw rgb24 bytes at a small analysis size, or None.

    Downscaling before analysis is deliberate: it averages away sensor noise
    and compression artefacts, so a flat border reads as genuinely flat, and
    it keeps the whole check in stdlib with no imaging dependency.
    """
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(media),
         "-frames:v", "1", "-vf", f"scale={w}:{h}",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
    )
    if proc.returncode != 0 or len(proc.stdout) < w * h * 3:
        return None
    return proc.stdout[:w * h * 3]


def qc_source(media, duration, width, height, samples=DEFAULT_QC_SAMPLES,
              aspect_tolerance=0.02):
    """Inspect a source for edge defects. Returns a QC verdict dict.

    Reports the WORST (deepest) border found across the sampled frames, so a
    frame effect that starts mid-take is caught even though the first frame
    is clean. `ok` false means stop and ask the creator.
    """
    verdict = {
        "ok": True,
        "samples": 0,
        "border_depth_frac": 0.0,
        "active_rect": None,
        "active_aspect": None,
        "declared_aspect": (width / height) if width and height else None,
        "defects": [],
    }
    aw, ah = QC_ANALYSIS_SIZE
    worst_depth, worst_pixels = 0, None
    times = qc_sample_times(duration, samples)
    for t in times:
        pixels = sample_frame_rgb(media, t, aw, ah)
        if pixels is None:
            continue
        verdict["samples"] += 1
        depth = detect_border_depth(pixels, aw, ah)
        if depth > worst_depth and border_is_distinct(pixels, aw, ah, depth):
            worst_depth, worst_pixels = depth, pixels
    if not verdict["samples"]:
        verdict["defects"].append("could not sample any frame for QC")
        verdict["ok"] = False
        return verdict

    if worst_depth > 0 and worst_pixels is not None:
        thumb_rect = active_rect(aw, ah, worst_depth)
        full_rect = scale_rect(thumb_rect, (aw, ah), (width, height))
        verdict["border_depth_frac"] = round(worst_depth / min(aw, ah), 4)
        verdict["active_rect"] = list(full_rect)
        verdict["active_aspect"] = round(aspect_of(full_rect), 4)
        verdict["defects"].append(
            f"flat border ring {verdict['border_depth_frac'] * 100:.1f}% deep "
            f"on every edge; active content is "
            f"{full_rect[2]}x{full_rect[3]} at +{full_rect[0]}+{full_rect[1]} "
            f"of {width}x{height}")
        declared = verdict["declared_aspect"]
        if declared and abs(verdict["active_aspect"] - declared) > \
                aspect_tolerance:
            verdict["defects"].append(
                f"active area aspect {verdict['active_aspect']:.3f} does not "
                f"match the container's {declared:.3f} (letterboxed, "
                "pillarboxed, or a non-16:9 recording region)")
        verdict["ok"] = False
    return verdict


def build_summary(files, disk):
    return {
        "files": files,
        "all_cfr": all(not f["vfr"] or f["cfr_master"] for f in files),
        "disk": disk,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("media", nargs="+", help="media files to preflight")
    parser.add_argument("--remux", action="store_true",
                        help="re-encode VFR files to CFR beside the original")
    parser.add_argument("--remux-suffix", default="-cfr")
    parser.add_argument("--qc-frames", default=None,
                        help="dir for first/last frame QC stills")
    parser.add_argument("--disk-path", default=None,
                        help="volume to disk-check (default: first file's dir)")
    parser.add_argument("--qc-samples", type=int, default=DEFAULT_QC_SAMPLES,
                        help=f"frames sampled across each take for the "
                             f"edge-defect QC (default {DEFAULT_QC_SAMPLES})")
    parser.add_argument("--no-qc", action="store_true",
                        help="skip the edge-defect QC pass entirely")
    parser.add_argument("--allow-qc-defects", action="store_true",
                        help="report QC defects but do not halt (use only "
                             "when the framing is intentional)")
    args = parser.parse_args(argv)

    files = []
    remux_jobs = []
    total_bytes = 0
    master_bytes = 0
    for m in args.media:
        path = Path(m)
        if not path.is_file():
            print(f"preflight: media not found: {path}", file=sys.stderr)
            return 1
        info = probe_media(path)
        if info is None:
            print(f"preflight: cannot probe {path}", file=sys.stderr)
            return 1
        size = path.stat().st_size
        total_bytes += size
        vfr = is_vfr(info["r_frame_rate"], info["avg_frame_rate"])
        avg = parse_rate(info["avg_frame_rate"])
        entry = {
            "path": str(path),
            "codec": info["codec"],
            "width": info["width"],
            "height": info["height"],
            "duration": info["duration"],
            "fps": round(float(avg), 3) if avg else None,
            "vfr": vfr,
            "cfr_master": None,
            "qc_frames": [],
        }
        files.append(entry)
        if vfr and args.remux:
            master_bytes += estimate_master_bytes(
                info["duration"], info["height"], size)
            remux_jobs.append((entry, path, info))

    # Disk gate BEFORE any remux write: the CFR masters are the biggest
    # writes this script makes, so their estimated size is checked up front
    # and the remux refused when it does not fit (runaway-write hardening).
    disk_dir = Path(args.disk_path) if args.disk_path else Path(args.media[0]).parent
    needed = total_bytes * 3 + master_bytes
    ok, free = core.check_disk(disk_dir, needed, factor=1.0)
    disk = {"free_bytes": free, "needed_bytes": needed, "ok": ok}
    if not ok and remux_jobs:
        print(f"preflight: insufficient disk space: needs about "
              f"{needed / 1e9:.1f} GB (3x source size plus "
              f"{master_bytes / 1e9:.1f} GB of estimated CFR masters), "
              f"{free / 1e9:.1f} GB free on {disk_dir}. Refusing the remux; "
              "free space and re-run.", file=sys.stderr)
        print(json.dumps(build_summary(files, disk), indent=2))
        return 1

    # One encoder pick for every remux in this run (pick_encoder's hardware
    # probes are cached per process, but there is no reason to ask twice).
    encoder = core.pick_encoder("auto") if remux_jobs else None
    for entry, path, info in remux_jobs:
        rate = nearest_standard_rate(info["avg_frame_rate"])
        dst = path.with_name(path.stem + args.remux_suffix + ".mp4")
        cmd = remux_command(path, dst, rate, encoder, height=info["height"])
        print(f"preflight: remuxing VFR {path.name} to CFR {rate} "
              f"({encoder})...", file=sys.stderr)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print("preflight: remux failed:", file=sys.stderr)
            print(" ".join(cmd), file=sys.stderr)
            print(proc.stderr.strip()[-2000:], file=sys.stderr)
            return 1
        entry["cfr_master"] = str(dst)

    # Source QC: assert, then HALT. Extracting frames and hoping someone
    # looks at them is what let a baked-in border reach a locked cut.
    qc_failed = []
    for entry in files:
        media = entry["cfr_master"] or entry["path"]
        if args.qc_frames:
            entry["qc_frames"] = extract_qc_frames(
                media, Path(args.qc_frames), entry["duration"])
        if args.no_qc:
            continue
        entry["qc"] = qc_source(media, entry["duration"], entry["width"],
                                entry["height"], samples=args.qc_samples)
        if not entry["qc"]["ok"]:
            qc_failed.append(entry)

    summary = build_summary(files, disk)
    summary["qc_ok"] = not qc_failed
    print(json.dumps(summary, indent=2))

    if qc_failed and not args.allow_qc_defects:
        print("\nSOURCE QC FAILED. Stopping before transcription or any "
              "render.", file=sys.stderr)
        for entry in qc_failed:
            print(f"\n  {entry['path']}", file=sys.stderr)
            for d in entry["qc"]["defects"]:
                print(f"    - {d}", file=sys.stderr)
            rect = entry["qc"].get("active_rect")
            if rect:
                print(f"    inferred active content: crop="
                      f"{rect[2]}:{rect[3]}:{rect[0]}:{rect[1]}",
                      file=sys.stderr)
        print("\nA baked-in border or a non-matching active area cannot be "
              "fixed later: the EDL is time-only, so every downstream stage "
              "inherits the bad canvas.\nEither correct it now with "
              "normalize_source.py (a spatial crop moves nothing in time, so "
              "an existing transcript, EDL and cutplan stay valid), or "
              "re-run with --allow-qc-defects if the framing is "
              "intentional.", file=sys.stderr)
        if args.qc_frames:
            print(f"QC stills for eyeballing: {args.qc_frames}",
                  file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
