#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Snap arbitrary cut spans into audio-verified silences.

Usage:
    uv run {skill-root}/scripts/snap_spans.py {projects-path}/<slug>/cut/approved-spans.json \
        --audio-map {projects-path}/<slug>/cut/audio-map.json \
        [--snap-ms 250] [-o {projects-path}/<slug>/cut/snapped-spans.json]

Why this exists:
    Step 7a applies the creator's content-tier calls after gate 2, and it used
    to say "re-detect every content-tier span against the audio, snap the
    edges into silences from the audio map". Snapping a time into the nearest
    silence is a pure function that cutplan.py already owns
    (snap_candidates), but cutplan's CLI only turns a transcript into
    candidates, so there was no way to snap a span the creator approved. The
    step was asking a model to redo by hand a computation the skill already
    had in Python, at the exact point where getting it wrong cuts the wrong
    words. An eyeballed snap is how a cut lands inside a word.

    So this is the same mechanic with a CLI in front of it. Judgment stays
    with the creator (which spans to cut); the arithmetic comes here.

Snapping is DIRECTIONAL, and that is load-bearing:
    A span here is material to REMOVE, so its start may only move EARLIER and
    its end only LATER. The span may widen into surrounding silence, which is
    always safe, and can never invert or collapse onto itself. Snapping both
    edges to the unconstrained nearest silence can pull an end backwards past
    its own start and annihilate the span.

Contract:
    input     a JSON list of spans, or an object with a "spans" key. Each span
              is {"start", "end", ...}; every other key is carried through
              untouched, so ids, quotes and reasons survive the round trip.
    output    the same spans with snapped start/end, plus "snapped" (bool) and
              "shift" (seconds each edge moved) on each. -o writes the full
              payload; stdout carries the summary.
    summary   json.dumps: {"ok", "spans", "snapped", "unsnapped": [...]}

`ok` is true only when every span reached a silence on BOTH edges. Spans that
could not are left at their original times, marked "snapped": false, and
named in `unsnapped`: they still carry timestamp risk and need an ear before
they go into the EDL. This script never pretends an edge is safe.

Exit codes: 0 every span snapped, 1 one or more spans unsnapped (check them
by ear), 2 usage error.

STATUS: implemented (pure logic covered by scripts/tests/test-snap_spans.py).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # noqa: E402
import analyze_audio as audio  # noqa: E402

# Matches cutplan.py's DEFAULT_SNAP_MS: the two paths must agree about how far
# an edge may travel, or a span snapped here would not survive verify_edl.py.
DEFAULT_SNAP_MS = 250


def r3(x):
    return round(float(x), 3)


def snap_span(span, silence, max_shift):
    """Snap one span's edges into silence, directionally (pure)."""
    out = dict(span)
    start = float(span["start"])
    end = float(span["end"])
    new_start = audio.nearest_silence(silence, start, max_shift,
                                      direction="back")
    new_end = audio.nearest_silence(silence, end, max_shift,
                                    direction="forward")
    out["snapped"] = new_start is not None and new_end is not None
    resolved_start = start if new_start is None else new_start
    resolved_end = end if new_end is None else new_end
    if resolved_end < resolved_start:
        resolved_end = resolved_start
    out["start"] = r3(resolved_start)
    out["end"] = r3(resolved_end)
    out["dur"] = r3(resolved_end - resolved_start)
    out["shift"] = {"start": r3(resolved_start - start),
                    "end": r3(resolved_end - end)}
    if not out["snapped"]:
        out["unsnapped_edges"] = [
            edge for edge, value in (("start", new_start), ("end", new_end))
            if value is None]
    return out


def snap_all(spans, silence, max_shift):
    """Snap every span (pure)."""
    return [snap_span(s, silence, max_shift) for s in spans]


def build_report(snapped):
    """Assemble the verdict (pure)."""
    unsnapped = [s for s in snapped if not s["snapped"]]
    return {
        "ok": not unsnapped,
        "spans": len(snapped),
        "snapped": len(snapped) - len(unsnapped),
        "unsnapped": [{k: s[k] for k in ("start", "end", "unsnapped_edges")
                       if k in s} for s in unsnapped],
    }


def parse_spans(payload):
    """Accept a bare list or an object with a spans key (pure)."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("spans", "candidates", "cuts"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("spans", help="path to the approved spans JSON")
    p.add_argument("--audio-map", required=True,
                   help="path to cut/audio-map.json from analyze_audio.py")
    p.add_argument("-o", "--output", default=None,
                   help="optional path for the snapped spans JSON")
    p.add_argument("--snap-ms", type=int, default=DEFAULT_SNAP_MS,
                   help=f"how far an edge may move to reach a silence "
                        f"(default {DEFAULT_SNAP_MS})")
    args = p.parse_args(argv)

    try:
        with open(args.spans, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"snap_spans: cannot read spans {args.spans}: {e}",
              file=sys.stderr)
        return 2
    spans = parse_spans(payload)
    if spans is None:
        print("snap_spans: expected a JSON list of spans, or an object with a "
              "'spans' key", file=sys.stderr)
        return 2
    for i, s in enumerate(spans):
        if not isinstance(s, dict) or "start" not in s or "end" not in s:
            print(f"snap_spans: span {i} needs both 'start' and 'end'",
                  file=sys.stderr)
            return 2

    try:
        with open(args.audio_map, encoding="utf-8") as f:
            audio_map = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"snap_spans: cannot read audio map {args.audio_map}: {e}",
              file=sys.stderr)
        return 2
    if "silence" not in audio_map:
        print("snap_spans: audio map has no 'silence' key; regenerate it with "
              "analyze_audio.py", file=sys.stderr)
        return 2

    silence = audio.to_pairs(audio_map["silence"])
    snapped = snap_all(spans, silence, args.snap_ms / 1000.0)
    report = build_report(snapped)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(snapped, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    else:
        print(json.dumps(snapped, indent=2, ensure_ascii=False))

    print(json.dumps(report, indent=2))
    if report["ok"]:
        return 0
    print(f"\n{len(report['unsnapped'])} span(s) could not reach a silence "
          "within the snap budget. They keep their original times and still "
          "carry timestamp risk: check them by ear before they go into the "
          "EDL.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
