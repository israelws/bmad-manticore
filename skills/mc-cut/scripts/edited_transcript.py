#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Reconstruct what the viewer actually hears: words.json intersected with the
kept EDL segments, carrying BOTH clean and source timecodes.

Usage:
    uv run {skill-root}/scripts/edited_transcript.py \
        {projects-path}/<slug>/transcript/words.json \
        --edl {projects-path}/<slug>/cut/edl.json \
        -o {projects-path}/<slug>/cut/edited-transcript.md \
        [-j {projects-path}/<slug>/cut/edited-words.json]

Why this exists:
    The content-editorial pass (references/editorial-pass.md) reads the
    delivered piece as an argument and recommends content cuts. It must read
    what SURVIVED THE CUT, not the script and not the raw transcript:
      - the script is what was planned, and delivery diverges from it
        (ad-libs, dropped lines, live rewrites; the first real project
        diverged from its script substantially);
      - the raw transcript still contains everything the mechanical cut
        removed, so a pass reading it would review words the viewer never
        hears.

    DUAL TIMECODES are the other half of the point. A recommendation is read
    by a human against the preview, which runs on CLEAN time, but applying it
    means editing the EDL, which is in SOURCE time. Every finding therefore
    needs both, and deriving one from the other by hand is exactly where the
    first editorial pass went wrong: its transcript-read source estimates
    drifted to the wrong windows, and a blind apply would have cut the wrong
    spans. Emitting both here removes that whole failure mode.

Contract:
    input     words.json (from transcribe.py) and cut/edl.json.
    keep rule a word is kept when its MIDPOINT falls inside a kept segment,
              so a word straddling a cut boundary belongs to whichever side
              holds most of it and is never emitted twice.
    output    -o markdown: the edited transcript in reading order, broken
              into paragraphs at pauses, each paragraph headed with its clean
              and source timecodes.
    json      -j optional: {"clean_duration", "words": [{word, clean_start,
              clean_end, src_start, src_end, segment}]}, the machine-readable
              form for any pass that needs to map a finding back to the EDL.
    summary   json.dumps on stdout: kept/dropped word counts, clean duration.

Exit codes: 0 ok, 1 failure, 2 usage error.

STATUS: implemented (pure logic covered by
scripts/tests/test-edited_transcript.py).
"""

import argparse
import json
import sys
from pathlib import Path

# A pause at or above this opens a new paragraph in the readable output.
PARAGRAPH_GAP_S = 0.9


def build_map(edl):
    """EDL segments as [{source, start, end, offset}] in timeline order (pure)."""
    out = []
    offset = 0.0
    for seg in edl["segments"]:
        out.append({"source": seg["source"], "start": seg["start"],
                    "end": seg["end"], "offset": offset})
        offset += seg["end"] - seg["start"]
    return out


def clean_duration(mapping):
    """Total length of the edited timeline (pure)."""
    return sum(s["end"] - s["start"] for s in mapping)


def keep_words(words, mapping, source=None):
    """The words that survive the cut, with dual timecodes (pure).

    A word is kept when its midpoint lands in a kept segment: a word
    straddling a boundary belongs to whichever side holds most of it, and is
    emitted exactly once. Clean times are the word's own span shifted by its
    segment's offset, clamped into the segment so a straddling word never
    reports a clean time outside the timeline.
    """
    out = []
    for w in words:
        mid = (float(w["start"]) + float(w["end"])) / 2.0
        for i, s in enumerate(mapping):
            if source is not None and s["source"] != source:
                continue
            if not (s["start"] <= mid <= s["end"]):
                continue
            cs = s["offset"] + (max(float(w["start"]), s["start"]) - s["start"])
            ce = s["offset"] + (min(float(w["end"]), s["end"]) - s["start"])
            out.append({
                "word": w["word"],
                "clean_start": round(cs, 3),
                "clean_end": round(max(cs, ce), 3),
                "src_start": round(float(w["start"]), 3),
                "src_end": round(float(w["end"]), 3),
                "segment": i,
            })
            break
    return out


def tc(seconds):
    """Seconds to m:ss (pure)."""
    seconds = max(0.0, float(seconds))
    return f"{int(seconds // 60)}:{seconds % 60:05.2f}"


def paragraphs(kept, gap=PARAGRAPH_GAP_S):
    """Group kept words into paragraphs at pauses or segment changes (pure).

    Breaking on a segment change matters as much as breaking on a pause: a
    seam is where the editorial pass most needs to see whether the sentence
    still reads, and burying it mid-paragraph hides exactly that.
    """
    out = []
    current = []
    for i, w in enumerate(kept):
        if current:
            prev = kept[i - 1]
            if (w["clean_start"] - prev["clean_end"] >= gap
                    or w["segment"] != prev["segment"]):
                out.append(current)
                current = []
        current.append(w)
    if current:
        out.append(current)
    return out


def render_markdown(kept, mapping, gap=PARAGRAPH_GAP_S):
    """The readable edited transcript (pure)."""
    total = clean_duration(mapping)
    lines = [
        "# Edited transcript",
        "",
        "What the viewer actually hears: `transcript/words.json` intersected "
        "with the kept segments of `cut/edl.json`.",
        "",
        f"Runtime {tc(total)} ({round(total, 2)}s), {len(kept)} words.",
        "",
        "Each paragraph is headed `clean-time (src source-time)`. Quote a "
        "finding by CLEAN time for the human at the gate, and apply it by "
        "SOURCE time against the EDL. Never convert between them by hand.",
        "",
    ]
    for para in paragraphs(kept, gap):
        head = para[0]
        lines.append(f"**{tc(head['clean_start'])}** "
                     f"(src {tc(head['src_start'])})")
        lines.append("")
        lines.append(" ".join(w["word"] for w in para))
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("words", help="path to transcript/words.json")
    p.add_argument("--edl", required=True, help="path to cut/edl.json")
    p.add_argument("-o", "--output", required=True,
                   help="path for the readable edited transcript markdown")
    p.add_argument("-j", "--json", default=None,
                   help="optional path for the machine-readable kept words")
    p.add_argument("--source", default=None,
                   help="restrict to one EDL source (multi-source projects)")
    p.add_argument("--paragraph-gap", type=float, default=PARAGRAPH_GAP_S)
    args = p.parse_args(argv)

    try:
        with open(args.words, encoding="utf-8") as f:
            transcript = json.load(f)
        with open(args.edl, encoding="utf-8") as f:
            edl = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"edited_transcript: cannot read input: {e}", file=sys.stderr)
        return 2
    if "words" not in transcript:
        print("edited_transcript: transcript has no 'words' key",
              file=sys.stderr)
        return 2
    if not edl.get("segments"):
        print("edited_transcript: edl has no segments", file=sys.stderr)
        return 2

    mapping = build_map(edl)
    words = transcript["words"]
    kept = keep_words(words, mapping, args.source)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(kept, mapping, args.paragraph_gap),
                      encoding="utf-8")

    if args.json:
        jout = Path(args.json)
        jout.parent.mkdir(parents=True, exist_ok=True)
        jout.write_text(json.dumps({
            "clean_duration": round(clean_duration(mapping), 3),
            "segments": len(mapping),
            "words": kept,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "output": str(output),
        "words_kept": len(kept),
        "words_dropped": len(words) - len(kept),
        "clean_duration": round(clean_duration(mapping), 3),
        "segments": len(mapping),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
