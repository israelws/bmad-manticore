#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Write the VIRTUAL TIMELINE for an EDL: an ffconcat playlist (and optionally
an mpv EDL) that plays the cut with no render at all.

Usage:
    uv run {skill-root}/scripts/edl_to_ffconcat.py cut/edl.json \
        -o cut/preview.ffconcat [--source <path>] [--mpv cut/preview.mpv.edl]

Why this exists:
    The cut stage used to make the creator wait for a full re-encode before
    they could watch anything. On a 16-minute cut with 379 segments that was
    ~22 minutes, and it happened at gate 2, BEFORE a single call had been
    approved. An NLE does not work that way: it plays a virtual timeline,
    seeking into the source and jumping between segments live.

    This is that timeline, in a file. ffplay/ffmpeg read it directly:

        ffplay -f concat -safe 0 -i cut/preview.ffconcat

    Zero render, instant, seekable, video AND audio (so A/V sync is
    reviewable, which an audio-only preview cannot show).

THE KEYFRAME CONSTRAINT, which is the whole reason this needs a matching proxy:
    The concat demuxer's `inpoint` can only begin at a KEYFRAME. Against a
    normal long-GOP encode this silently produces the WRONG CUT: measured on a
    720p proxy with an 8.333s GOP against segments averaging 2.51s (163 of 379
    under 2s), every segment started up to 8.3s early. Total duration still
    matched the EDL to the millisecond, because `outpoint` clips the length --
    so the failure is invisible unless you compare frames.

    Against an ALL-INTRA source every frame is a keyframe, so every cut point
    is exact. Verified pixel-identical (PSNR inf) to source ground truth at
    four points including random seeks.

    So: point this at an all-intra proxy, which is what composite_core's
    build_proxy_command now produces. Pointing it at a long-GOP master or an
    old proxy gives a plausible-looking, wrong timeline. --require-intra
    (default) refuses rather than letting that happen.

Contract:
    input     edl.json: {source, source_duration, segments[]}; each segment
              {source, start, end, ...} in seconds against its source.
    output    -o: an ffconcat v1.0 playlist, one file/inpoint/outpoint triple
              per segment, with absolute source paths.
    --mpv     optionally also write an mpv EDL (`# mpv EDL v0`, one
              file,start,length line per segment, %len%-quoted paths).
    --source  override the source path every segment points at (e.g. swap the
              master for its proxy). Default: each segment's own source.
    summary   json.dumps on stdout: {ok, segments, duration_seconds, output,
              mpv, all_intra}.

Exit codes: 0 ok, 1 source unreadable or not all-intra (with
--require-intra), 2 usage error.

STATUS: implemented (pure logic covered by
scripts/tests/test-edl_to_ffconcat.py).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def ffconcat_lines(segments, source_override=None):
    """The ffconcat v1.0 body for these segments (pure)."""
    out = ["ffconcat version 1.0"]
    for seg in segments:
        src = source_override or seg["source"]
        out.append(f"file '{src}'")
        out.append(f"inpoint {float(seg['start']):.6f}")
        out.append(f"outpoint {float(seg['end']):.6f}")
    return out


def mpv_edl_lines(segments, source_override=None):
    """The mpv EDL v0 body for these segments (pure).

    mpv takes file,START,LENGTH (not end), and quotes a path as
    %<bytelen>%<path> so commas in filenames cannot split the record.
    """
    out = ["# mpv EDL v0"]
    for seg in segments:
        src = str(source_override or seg["source"])
        start = float(seg["start"])
        length = float(seg["end"]) - start
        out.append(f"%{len(src.encode())}%{src},{start:.6f},{length:.6f}")
    return out


def is_all_intra(path, probe_seconds=30):
    """True when every sampled video frame is a keyframe (impure: runs ffprobe).

    Sampling the head is enough: an encode is all-intra by GOP setting, not
    by content, so a mixed result means the wrong file, not a rare case.
    Returns None when ffprobe cannot read the file at all.
    """
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v",
           "-show_entries", "frame=key_frame", "-of", "csv=p=0",
           "-read_intervals", f"%{probe_seconds}", str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    flags = [ln.strip().rstrip(",") for ln in proc.stdout.splitlines()
             if ln.strip()]
    if not flags:
        return None
    return all(f == "1" for f in flags)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("edl", help="path to cut/edl.json")
    ap.add_argument("-o", "--output", required=True,
                    help="where to write the ffconcat playlist")
    ap.add_argument("--mpv", default=None,
                    help="also write an mpv EDL here")
    ap.add_argument("--source", default=None,
                    help="override the source every segment points at")
    ap.add_argument("--require-intra", action="store_true", default=True,
                    help="refuse a source that is not all-intra (default)")
    ap.add_argument("--allow-long-gop", dest="require_intra",
                    action="store_false",
                    help="opt out of the all-intra check; the timeline will "
                         "be WRONG at every segment shorter than the GOP")
    args = ap.parse_args(argv)

    edl = json.loads(Path(args.edl).read_text(encoding="utf-8"))
    segments = edl.get("segments") or []
    if not segments:
        print("error: EDL has no segments", file=sys.stderr)
        return 2

    override = str(Path(args.source).resolve()) if args.source else None
    sources = ({override} if override
               else {str(Path(s["source"]).resolve()) for s in segments})

    all_intra = True
    for src in sorted(sources):
        verdict = is_all_intra(src)
        if verdict is None:
            print(f"error: cannot probe {src}", file=sys.stderr)
            return 1
        if not verdict:
            all_intra = False
            msg = (f"{src} is NOT all-intra. The concat demuxer can only cut "
                   f"on keyframes, so this timeline would silently play the "
                   f"WRONG frames while still reporting the right duration.")
            if args.require_intra:
                print(f"error: {msg}\nBuild an all-intra proxy first, or pass "
                      f"--allow-long-gop if you accept a wrong timeline.",
                      file=sys.stderr)
                return 1
            print(f"warning: {msg}", file=sys.stderr)

    # Resolve every segment's source to an absolute path so the playlist works
    # from any working directory.
    resolved = [dict(s, source=override or str(Path(s["source"]).resolve()))
                for s in segments]

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(ffconcat_lines(resolved)) + "\n",
                   encoding="utf-8")

    mpv_out = None
    if args.mpv:
        mpv_out = Path(args.mpv)
        mpv_out.parent.mkdir(parents=True, exist_ok=True)
        mpv_out.write_text("\n".join(mpv_edl_lines(resolved)) + "\n",
                           encoding="utf-8")

    duration = sum(float(s["end"]) - float(s["start"]) for s in segments)
    print(json.dumps({
        "ok": True,
        "segments": len(segments),
        "duration_seconds": round(duration, 3),
        "output": str(out),
        "mpv": str(mpv_out) if mpv_out else None,
        "all_intra": all_intra,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
