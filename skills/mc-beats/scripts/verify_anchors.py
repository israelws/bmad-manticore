#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Beat anchor placement gate: prove every graphic lands on the words it rides.

Usage:
    uv run {skill-root}/scripts/verify_anchors.py {projects-path}/<slug>/beats/beats.md \
        --edl {projects-path}/<slug>/cut/edl.json \
        --words {projects-path}/<slug>/transcript/words.json \
        [--tolerance 0.5] [-o {projects-path}/<slug>/beats/anchor-check.json]

Why this exists:
    mc-beats' checklist has always said "every beat has an anchor word that
    exists in the transcript at that timestamp". Nothing enforced it. Beat
    times were written by eye against the edited timeline, and an overlay
    landing a second off its anchor phrase is invisible in a beat table and
    obvious in the render, after the graphics work is already done.

    It is the same defect shape as the QC frames that were extracted but
    never asserted on, and the boundary frames that were eyeballed while the
    underlying audio was wrong: a documented check with no mechanical
    assertion behind it. An assertion is a mechanic, not a taste call, so it
    belongs in a script that exits non-zero.

How a beat time SHOULD be derived (and what this checks):
    Never estimate. Take the anchor word's timestamp from the transcript,
    which is in ORIGINAL source time, and remap it through the EDL onto the
    clean edited timeline. That mapping is exactly what this script redoes
    independently, so a beat whose time was estimated rather than derived
    fails here.

Checks, per beat row:
    1. The anchor word appears in the transcript at all.
    2. Its source time falls inside a KEPT EDL segment. An anchor sitting in
       a span the cut removed is a hard failure: the graphic rides on words
       the viewer never hears.
    3. Its remapped clean time is within --tolerance of the beat's start.
       When several occurrences of the word exist, the NEAREST one is used,
       so the failure means "no occurrence of this word is anywhere near
       where you placed this beat".
    4. When the table carries an `anchor ts` column, that value agrees with
       the derived clean time too (anchors are measured against the edited
       timeline, per PIPELINE.md).

Rows with no anchor word are reported as unverifiable rather than failed,
per PIPELINE.md's tolerance rule for legacy 0.x beat tables.

Contract:
    input     beats.md (the engine-neutral beat table), cut/edl.json, and
              transcript/words.json.
    output    optional -o report JSON: {"ok", "checked", "violations": [...],
              "unverifiable": [...]}
    summary   json.dumps on stdout either way.

Exit codes: 0 every anchor verified, 1 one or more violations (do not render
graphics against this table), 2 usage error.

Note on duplication: the orig-to-clean mapping below is a deliberate copy of
the same logic in mc-cut/scripts/remap_timecode.py, per the module's
script-duplication convention (a skill reads only its own folder).

STATUS: implemented (pure logic covered by
scripts/tests/test-verify_anchors.py).
"""

import argparse
import json
import string
import sys
from pathlib import Path

DEFAULT_TOLERANCE_S = 0.5
_STRIP = string.punctuation


def norm(word):
    """Lowercase, strip surrounding punctuation (pure)."""
    return str(word).strip(_STRIP).lower()


def build_map(edl):
    """EDL segments as [{source, start, end, offset}] in timeline order (pure)."""
    out = []
    offset = 0.0
    for seg in edl["segments"]:
        out.append({"source": seg["source"], "start": seg["start"],
                    "end": seg["end"], "offset": offset})
        offset += seg["end"] - seg["start"]
    return out


def orig_to_clean(mapping, t, source=None):
    """Map an original-source time onto the clean timeline, or None (pure).

    None means the time falls in a span the cut removed. That is a real
    answer here, not an error: it is exactly the "anchor was cut away" case
    check 2 exists to catch, so this deliberately does NOT snap to the
    nearest kept segment the way the chapter remapper does.
    """
    for s in mapping:
        if source is not None and s["source"] != source:
            continue
        if s["start"] <= t <= s["end"]:
            return s["offset"] + (t - s["start"])
    return None


def parse_beats(text):
    """Parse the beat table, keeping the anchor columns (pure).

    Returns (rows, skipped). Columns are matched by header name so extra
    columns and any order are fine, matching composite_core's parser.
    """
    header = None
    col = {}
    rows, skipped = [], []
    for line in text.splitlines():
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        low = [c.lower() for c in cells]
        if header is None:
            if "id" in low and "start" in low:
                header = low
                col = {name: i for i, name in enumerate(low)}
            continue
        if all(set(c) <= set("-: ") for c in cells if c):
            continue  # the ---|--- separator row
        if len(cells) < len(header):
            skipped.append(f"row has {len(cells)} cells, expected "
                           f"{len(header)}: {cells[:2]}")
            continue

        def cell(name):
            i = col.get(name)
            if i is None or i >= len(cells):
                return ""
            return cells[i]

        bid = cell("id")
        if not bid:
            skipped.append(f"row has no id: {cells[:3]}")
            continue
        try:
            start = float(cell("start"))
        except ValueError:
            skipped.append(f"beat {bid}: start {cell('start')!r} is not a number")
            continue
        anchor_ts = None
        raw_ts = cell("anchor ts")
        if raw_ts and raw_ts.lower() not in ("null", "none", "-"):
            try:
                anchor_ts = float(raw_ts)
            except ValueError:
                anchor_ts = None
        rows.append({
            "id": bid,
            "start": start,
            "anchor_word": cell("anchor word"),
            "anchor_ts": anchor_ts,
            "phrase": cell("spoken phrase"),
        })
    return rows, skipped


def find_anchor_occurrences(words, anchor):
    """Every transcript word matching the anchor text (pure).

    A multi-word anchor matches a consecutive run; the occurrence's time is
    the first word's start.
    """
    tokens = [norm(t) for t in str(anchor).split() if norm(t)]
    if not tokens:
        return []
    nwords = [norm(w["word"]) for w in words]
    out = []
    for i in range(len(nwords) - len(tokens) + 1):
        if nwords[i:i + len(tokens)] == tokens:
            out.append(words[i])
    return out


def verify_beat(beat, words, mapping, tolerance=DEFAULT_TOLERANCE_S):
    """Verify one beat row. Returns a result dict (pure).

    status is "ok", "violation", or "unverifiable".
    """
    result = {"id": beat["id"], "start": beat["start"],
              "anchor_word": beat["anchor_word"]}
    if not beat["anchor_word"]:
        result["status"] = "unverifiable"
        result["reason"] = "row carries no anchor word (legacy 0.x table)"
        return result

    occurrences = find_anchor_occurrences(words, beat["anchor_word"])
    if not occurrences:
        result["status"] = "violation"
        result["reason"] = (f'anchor word "{beat["anchor_word"]}" does not '
                            "appear in the transcript at all")
        return result

    mapped = [(w, orig_to_clean(mapping, w["start"])) for w in occurrences]
    kept = [(w, c) for w, c in mapped if c is not None]
    if not kept:
        result["status"] = "violation"
        result["reason"] = (f'every occurrence of "{beat["anchor_word"]}" '
                            "falls in a span the cut removed; this graphic "
                            "rides on words the viewer never hears")
        result["source_times"] = [round(w["start"], 2) for w, _ in mapped]
        return result

    word, clean = min(kept, key=lambda wc: abs(wc[1] - beat["start"]))
    drift = clean - beat["start"]
    result["derived_clean"] = round(clean, 3)
    result["source_time"] = round(word["start"], 3)
    result["drift"] = round(drift, 3)
    result["occurrences"] = len(occurrences)

    if abs(drift) > tolerance:
        result["status"] = "violation"
        result["reason"] = (
            f'beat starts at {beat["start"]:.2f}s but the nearest '
            f'"{beat["anchor_word"]}" lands at {clean:.2f}s on the clean '
            f"timeline ({drift:+.2f}s off, tolerance {tolerance}s). Derive "
            "the time by remapping the anchor's transcript timestamp through "
            "the EDL instead of estimating it.")
        return result

    if beat["anchor_ts"] is not None and \
            abs(beat["anchor_ts"] - clean) > tolerance:
        result["status"] = "violation"
        result["reason"] = (
            f'anchor ts column says {beat["anchor_ts"]:.2f}s but the anchor '
            f"lands at {clean:.2f}s on the clean timeline. Anchor times are "
            "measured against the EDITED timeline (PIPELINE.md).")
        return result

    result["status"] = "ok"
    return result


def build_report(beats, words, mapping, tolerance=DEFAULT_TOLERANCE_S):
    """Verify every beat and assemble the verdict (pure)."""
    results = [verify_beat(b, words, mapping, tolerance) for b in beats]
    violations = [r for r in results if r["status"] == "violation"]
    unverifiable = [r for r in results if r["status"] == "unverifiable"]
    return {
        "ok": not violations,
        "beats": len(results),
        "checked": len(results) - len(unverifiable),
        "tolerance": tolerance,
        "violations": violations,
        "unverifiable": unverifiable,
        "results": results,
    }


def _load(path, label):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"verify_anchors: cannot read {label} {path}: {e}",
              file=sys.stderr)
        return None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("beats", help="path to beats/beats.md")
    p.add_argument("--edl", required=True, help="path to cut/edl.json")
    p.add_argument("--words", required=True,
                   help="path to transcript/words.json")
    p.add_argument("-o", "--output", default=None,
                   help="optional path for the full report JSON")
    p.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE_S,
                   help=f"seconds a beat may sit from its anchor (default "
                        f"{DEFAULT_TOLERANCE_S})")
    args = p.parse_args(argv)

    try:
        table = Path(args.beats).read_text(encoding="utf-8")
    except OSError as e:
        print(f"verify_anchors: cannot read beat table {args.beats}: {e}",
              file=sys.stderr)
        return 2
    edl = _load(args.edl, "edl")
    if edl is None:
        return 2
    transcript = _load(args.words, "transcript")
    if transcript is None:
        return 2
    if not edl.get("segments"):
        print("verify_anchors: edl has no segments", file=sys.stderr)
        return 2
    if "words" not in transcript:
        print("verify_anchors: transcript has no 'words' key", file=sys.stderr)
        return 2

    beats, skipped = parse_beats(table)
    for reason in skipped:
        print(f"beat row skipped: {reason}", file=sys.stderr)
    if not beats:
        print("verify_anchors: no beat rows found in the table",
              file=sys.stderr)
        return 2

    report = build_report(beats, transcript["words"], build_map(edl),
                          args.tolerance)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")

    print(json.dumps({k: report[k] for k in
                      ("ok", "beats", "checked", "tolerance")}, indent=2))

    for r in report["unverifiable"]:
        print(f"note: beat {r['id']} unverifiable: {r['reason']}",
              file=sys.stderr)

    if report["ok"]:
        return 0

    print(f"\nANCHOR PLACEMENT FAILED: {len(report['violations'])} beat(s) do "
          "not land on their anchor words. Do NOT render graphics against "
          "this table.", file=sys.stderr)
    for r in report["violations"]:
        print(f"  {r['id']}: {r['reason']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
