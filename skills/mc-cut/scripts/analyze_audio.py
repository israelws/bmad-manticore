#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Audio silence map for the cut stage: the TIMING source of truth.

Usage:
    uv run {skill-root}/scripts/analyze_audio.py {projects-path}/<slug>/raw/<take> \
        -o {projects-path}/<slug>/cut/audio-map.json \
        [--noise -30] [--map-granularity 0.10]

Why this exists (read before changing any of it):
    Cutting decisions used to be derived from TRANSCRIPT timestamps: the gap
    between one word's end and the next word's start. That is wrong, and it
    shipped a corrupted cut on the first real project (2026-07-24). parakeet
    absorbs a pause into the preceding word's end, so the word "about."
    was timestamped 32.16 -> 34.64: a single "word" lasting 2.5 seconds
    because it swallowed the silence after it. Every gap computed from those
    timestamps reads about 0.0 across real dead air, so the silence detector
    was blind. On a take with over 5 minutes of dead air it found 12 silences.
    ffmpeg silencedetect on the same audio found 402 intervals totalling 309
    seconds.

    So: the TRANSCRIPT is the authority on CONTENT (what words were said, in
    what order). The AUDIO is the authority on TIMING (where silence is, and
    therefore where it is safe to cut). This script produces the second one.
    Do not reintroduce gap-derived silence anywhere downstream.

    A second property makes this the right primitive: a cut that lands inside
    an audio-verified silence CANNOT clip a word. The "never cut inside a
    word" rule stops being an assertion about timestamps and becomes a
    structural guarantee.

Contract:
    input   any media file (audio or video); ffmpeg reads the audio stream.
    output  audio-map.json:
            {"media", "duration", "noise_db", "map_granularity",
             "silent_seconds", "speech_seconds",
             "counts": {"silence", "speech"},
             "silence": [{"start", "end", "dur"}, ...],
             "speech":  [{"start", "end", "dur"}, ...]}
            The two interval lists are exact complements over [0, duration],
            both sorted, non-overlapping, times to 3 decimals.
    summary json.dumps on stdout: counts, silent_seconds, speech_seconds,
            output path.

Consumers:
    verify_transcript.py  the completeness gate (speech with no words is
                          DROPPED SPEECH, not dead air)
    cutplan.py            silence candidates and candidate edge snapping

Both read the same file, so the two never disagree about where silence is and
the expensive decode happens once.

Tuning:
    --noise        dBFS floor below which audio counts as silence (default
                   -30). Room tone on a decent mic sits well under this; a
                   noisy room may need -35 or -40. Too high and speech onsets
                   get eaten; too low and nothing registers as silent.
    --map-granularity  shortest interval to report (default 0.10s). Deliberately
                   FINER than any cutting threshold: consumers filter up from
                   this list, and a coarse map cannot be refined later.

Exit codes: 0 ok, 1 ffmpeg/probe failure, 2 usage error.

STATUS: implemented (pure parsing and interval logic covered by
scripts/tests/test-analyze_audio.py).
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_NOISE_DB = -30.0
# Map granularity, NOT a cutting threshold. It must stay well below every
# consumer's threshold, because consumers filter UP from this list and a
# coarse map cannot be refined later.
#
# Two consumers need the small intervals specifically:
#   - edge snapping (cutplan.py) moves a cut edge into the nearest silence,
#     and the gaps between doubled words or around a clipped onset are
#     0.1 to 0.2s. A map that started at 0.3s would leave exactly those
#     edges unsnappable, which is the "n-now" artifact class.
#   - the transcript gate measures audible-but-untranscribed audio, so its
#     silence input has to be complete, not just the big pauses.
# On the real 2026-07-24 take this yields 929 intervals; at 0.3 it yields
# 400, and the 529 it drops are precisely the ones snapping needs.
DEFAULT_MAP_GRANULARITY = 0.10

_START_RE = re.compile(r"silence_start:\s*(-?[\d.]+)")
_END_RE = re.compile(r"silence_end:\s*(-?[\d.]+)")


def r3(x):
    return round(float(x), 3)


def probe_duration(media):
    """Media duration in seconds via ffprobe. Raises on failure."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", str(media)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def parse_silencedetect(stderr_text, duration):
    """Parse ffmpeg silencedetect stderr into silence intervals (pure).

    silencedetect emits paired lines:
        [silencedetect @ ...] silence_start: 12.345
        [silencedetect @ ...] silence_end: 14.567 | silence_duration: 2.222
    A file that ENDS in silence gets a silence_start with no matching
    silence_end, so the open interval is closed at `duration`. Intervals are
    clamped into [0, duration], zero-length ones dropped, and the result is
    sorted and merged so consumers can rely on non-overlapping order.
    """
    intervals = []
    open_start = None
    for line in stderr_text.splitlines():
        m = _START_RE.search(line)
        if m:
            open_start = float(m.group(1))
            continue
        m = _END_RE.search(line)
        if m and open_start is not None:
            intervals.append((open_start, float(m.group(1))))
            open_start = None
    if open_start is not None:
        intervals.append((open_start, duration))
    return _clean(intervals, duration)


def _clean(intervals, duration):
    """Clamp into [0, duration], drop empties, sort, merge overlaps (pure)."""
    cleaned = []
    for start, end in intervals:
        start = max(0.0, min(float(start), duration))
        end = max(0.0, min(float(end), duration))
        if end - start > 1e-6:
            cleaned.append((start, end))
    cleaned.sort()
    merged = []
    for start, end in cleaned:
        if merged and start <= merged[-1][1] + 1e-6:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def complement(intervals, duration):
    """The gaps between intervals over [0, duration] (pure).

    Given the silence list this yields the speech list, and vice versa. Both
    directions are used: consumers ask "is this span silent" and "is this
    span speech" and neither should have to invert the other by hand.
    """
    out = []
    cursor = 0.0
    for start, end in intervals:
        if start - cursor > 1e-6:
            out.append((cursor, start))
        cursor = max(cursor, end)
    if duration - cursor > 1e-6:
        out.append((cursor, duration))
    return out


def as_records(intervals):
    """Interval tuples to the JSON record shape (pure)."""
    return [{"start": r3(s), "end": r3(e), "dur": r3(e - s)}
            for s, e in intervals]


def to_pairs(records):
    """JSON records back to interval tuples (pure). The read side of
    as_records, for consumers loading an audio-map.json."""
    return [(float(r["start"]), float(r["end"])) for r in records]


def total(intervals):
    """Summed length of an interval list (pure)."""
    return sum(e - s for s, e in intervals)


def overlap_seconds(intervals, start, end):
    """How much of [start, end] is covered by `intervals` (pure).

    The primitive both consumers are built on: "how silent is this span?"
    for the transcript gate, and "is this candidate edge inside silence?"
    for the cutter.
    """
    if end <= start:
        return 0.0
    covered = 0.0
    for a, b in intervals:
        if b <= start:
            continue
        if a >= end:
            break
        covered += min(b, end) - max(a, start)
    return covered


def silent_fraction(silence, start, end):
    """Fraction of [start, end] that is silent, 0.0 to 1.0 (pure)."""
    span = end - start
    if span <= 0:
        return 1.0
    return overlap_seconds(silence, start, end) / span


def enclosing(intervals, t):
    """The interval containing t, or None (pure)."""
    for a, b in intervals:
        if a <= t <= b:
            return (a, b)
        if a > t:
            break
    return None


def nearest_silence(silence, t, max_shift, direction="nearest"):
    """Nearest point inside a silence interval to t, within max_shift (pure).

    Returns t unchanged when it already sits in silence, the nearest
    qualifying point inside some silence interval when one is close enough,
    or None when nothing qualifies within max_shift. Used to snap cut edges
    so a cut can never land mid-word (see the module docstring).

    direction constrains which way t may move:
        "back"     only earlier (or unchanged)
        "forward"  only later (or unchanged)
        "nearest"  either way

    Direction matters and "nearest" is the wrong default for cut edges. A cut
    candidate is a span to REMOVE, so its start must only move earlier and
    its end only later: the span may widen into surrounding silence, which is
    always safe, and can never invert or collapse. Snapping both edges to the
    unconstrained nearest silence can pull an end backwards past its own
    start and annihilate the candidate.
    """
    if enclosing(silence, t) is not None:
        return t
    best = None
    for a, b in silence:
        # The point inside [a, b] closest to t, biased just inside the edge.
        cand = min(max(t, a), b)
        if direction == "back" and cand > t:
            continue
        if direction == "forward" and cand < t:
            continue
        dist = abs(cand - t)
        if dist <= max_shift and (best is None or dist < best[0]):
            best = (dist, cand)
    return None if best is None else best[1]


def run_silencedetect(media, noise_db, granularity):
    """Run ffmpeg silencedetect and return its stderr text. Raises on failure."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(media),
         "-af", f"silencedetect=noise={noise_db}dB:d={granularity}",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    # silencedetect writes to stderr and ffmpeg exits 0; a non-zero exit is a
    # real failure (no audio stream, unreadable file).
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[-2000:])
    return proc.stderr


def build(media, duration, silence_pairs, noise_db, granularity):
    """Assemble the audio-map payload (pure)."""
    speech_pairs = complement(silence_pairs, duration)
    return {
        "media": str(media),
        "duration": r3(duration),
        "noise_db": noise_db,
        "map_granularity": granularity,
        "silent_seconds": r3(total(silence_pairs)),
        "speech_seconds": r3(total(speech_pairs)),
        "counts": {"silence": len(silence_pairs), "speech": len(speech_pairs)},
        "silence": as_records(silence_pairs),
        "speech": as_records(speech_pairs),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("media", help="path to the media file (audio or video)")
    p.add_argument("-o", "--output", required=True, help="path to audio-map.json")
    p.add_argument("--noise", type=float, default=DEFAULT_NOISE_DB,
                   help=f"silence floor in dBFS (default {DEFAULT_NOISE_DB})")
    p.add_argument("--map-granularity", type=float,
                   default=DEFAULT_MAP_GRANULARITY,
                   help=f"shortest silence to report (default "
                        f"{DEFAULT_MAP_GRANULARITY}s). This is MAP RESOLUTION, "
                        "not a cutting threshold: keep it finer than every "
                        "consumer, since a coarse map cannot be refined later")
    args = p.parse_args(argv)

    media = Path(args.media)
    if not media.is_file():
        print(f"analyze_audio: media not found: {media}", file=sys.stderr)
        return 2
    if args.map_granularity <= 0:
        print("analyze_audio: --map-granularity must be positive",
              file=sys.stderr)
        return 2

    try:
        duration = probe_duration(media)
        stderr_text = run_silencedetect(media, args.noise,
                                        args.map_granularity)
    except (subprocess.CalledProcessError, RuntimeError, ValueError) as e:
        print(f"analyze_audio: cannot analyze {media}: {e}", file=sys.stderr)
        return 1

    silence_pairs = parse_silencedetect(stderr_text, duration)
    payload = build(media, duration, silence_pairs, args.noise,
                    args.map_granularity)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "output": str(output),
        "duration": payload["duration"],
        "counts": payload["counts"],
        "silent_seconds": payload["silent_seconds"],
        "speech_seconds": payload["speech_seconds"],
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
