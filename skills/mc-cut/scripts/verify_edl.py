#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""EDL gate: prove no cut lands inside a word before anything renders.

Usage:
    uv run {skill-root}/scripts/verify_edl.py {projects-path}/<slug>/cut/edl.json \
        --audio-map {projects-path}/<slug>/cut/audio-map.json \
        --words {projects-path}/<slug>/transcript/words.json \
        [--tolerance 0.0] [-o {projects-path}/<slug>/cut/edl-check.json]

Why this exists:
    mc-cut's cutting rules have always said "never cut inside a word" and its
    checklist has always claimed "edl times checked against word timestamps
    AND resting in audio silences". Nothing enforced either one. cutplan.py
    snaps CANDIDATES into silence, but the EDL is written by hand at step 6
    and rewritten at step 7a, and until this script nothing ever read it back.

    So the stage's own deliverable was the one artifact with no gate on it,
    while its siblings all got one: preflight asserts on source QC,
    verify_transcript asserts on transcript completeness, verify_anchors
    asserts on beat placement. This is mc-cut's twin of verify_anchors.py.
    A check the pipeline claims to perform must be a script that exits
    non-zero (AGENTS.md); this is that script for the cut itself.

Why silence is the authority and word spans are only context:
    The obvious implementation is "fail any boundary that falls inside a word
    span". That is WRONG here, and shipping it would fail correct cuts.
    parakeet absorbs a pause into the preceding word's end, so the word
    "about." can be timestamped 32.16 -> 34.64: a single "word" covering 2.5
    seconds because it swallowed the silence after it. A cut correctly placed
    in that silence sits inside the word's timestamp span while sitting in
    real, audible silence.

    So the check follows the two-source rule the module already commits to.
    The AUDIO decides: a boundary resting inside an audio-verified silence
    CANNOT clip a word, whatever the transcript timestamps say. The word span
    is reported only as extra detail on a boundary that ALREADY failed the
    audio test, where "and it is mid-word" tells the creator how bad the miss
    is. A boundary is never failed on word overlap alone.

What is exempt, and why:
    - The head of the source (start 0.0) and its tail (end == source_duration)
      are not cuts. No material was removed there, so there is nothing to
      clip.
    - A boundary shared by two segments that are contiguous in the same source
      (prev.end == next.start) is not a cut either: the timeline is continuous
      across it and nothing was removed.
    Segments are NOT required to be in source order. Step 5 explicitly picks
    best takes and orders segments, so a reordered EDL is correct by design
    and this script must not fail it.

Checks, per segment:
    1. Structure: start < end, both inside [0, source_duration], source set.
    2. Provenance: quote and reason are both non-empty (the EDL's own contract
       is that every segment records what was said and why it was kept).
    3. Boundaries: every non-exempt boundary rests inside an audio-verified
       silence, within --tolerance. Failures report the distance to the
       nearest silence and whether the boundary is mid-word.

Contract:
    input     cut/edl.json, one or more audio-map.json, one or more
              words.json. With a single map (or single transcript) it applies
              to every segment; with several they are matched to each
              segment's `source`.
    output    optional -o report JSON: {"ok", "segments", "boundaries",
              "violations": [...], "exempt": [...]}
    summary   json.dumps on stdout either way.

Exit codes: 0 every segment verified, 1 one or more violations (do NOT
render, do not export a timeline, do not present this cut), 2 usage error.

STATUS: implemented (pure logic covered by scripts/tests/test-verify_edl.py).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # noqa: E402
import analyze_audio as audio  # noqa: E402

# How far a boundary may sit from a silence and still pass. Zero by default:
# cutplan snaps edges INTO silence, so a boundary that is merely near one was
# not derived the way the pipeline derives them. Raise it only to triage an
# inherited EDL.
DEFAULT_TOLERANCE_S = 0.0
# Float slop when comparing times against duration and against each other.
EPS = 1e-6


def r3(x):
    return round(float(x), 3)


def word_at(words, t):
    """The word whose span strictly contains t, or None (pure).

    Context only. See the module docstring: a pause-absorbed word end reaches
    past the sound, so this answer alone never fails a boundary.
    """
    for w in words:
        if float(w["start"]) < t < float(w["end"]):
            return w
    return None


def natural_edges(segments, duration):
    """Boundary times that are not cuts (pure).

    The source head and tail, plus any boundary where two segments run
    contiguously in the same source so nothing was removed between them.
    """
    # Malformed segments are reported by verify_segment, so this pass must
    # tolerate them rather than raising: a gate that crashes on bad input
    # tells the creator nothing about what is wrong.
    exempt = set()
    for seg in segments:
        source, start, end = _edges(seg)
        if start is None or end is None:
            continue
        if abs(start) <= EPS:
            exempt.add((source, r3(start)))
        if duration is not None and abs(end - duration) <= EPS:
            exempt.add((source, r3(end)))
    for a, b in zip(segments, segments[1:]):
        a_source, _, a_end = _edges(a)
        b_source, b_start, _ = _edges(b)
        if a_source != b_source or a_end is None or b_start is None:
            continue
        if abs(a_end - b_start) <= EPS:
            exempt.add((a_source, r3(a_end)))
    return exempt


def _edges(seg):
    """(source, start, end) with non-numeric times as None (pure)."""
    if not isinstance(seg, dict):
        return None, None, None
    try:
        return seg.get("source"), float(seg["start"]), float(seg["end"])
    except (KeyError, TypeError, ValueError):
        return seg.get("source"), None, None


def check_boundary(t, silence, words, tolerance=DEFAULT_TOLERANCE_S):
    """Verify one boundary time against the audio (pure).

    Returns None when the boundary is safe, or a dict describing the miss.
    """
    if audio.enclosing(silence, t) is not None:
        return None
    landing = audio.nearest_silence(silence, t, max_shift=float("inf"))
    distance = None if landing is None else abs(landing - t)
    if distance is not None and distance <= tolerance + EPS:
        return None
    detail = {"time": r3(t)}
    if distance is not None:
        detail["nearest_silence"] = r3(landing)
        detail["distance"] = r3(distance)
    w = word_at(words, t)
    if w is not None:
        detail["inside_word"] = str(w["word"])
        detail["word_span"] = [r3(w["start"]), r3(w["end"])]
    return detail


def verify_segment(index, seg, silence, words, duration, exempt,
                   tolerance=DEFAULT_TOLERANCE_S):
    """Verify one EDL segment. Returns a list of violation dicts (pure)."""
    out = []
    sid = seg.get("id", index)
    source = seg.get("source")
    if not source:
        out.append({"segment": sid, "kind": "structure",
                    "reason": "segment has no source"})
        return out
    try:
        start = float(seg["start"])
        end = float(seg["end"])
    except (KeyError, TypeError, ValueError):
        out.append({"segment": sid, "kind": "structure",
                    "reason": "segment start/end missing or not a number"})
        return out

    if end - start <= EPS:
        out.append({"segment": sid, "kind": "structure", "time": r3(start),
                    "reason": f"segment start {start:.3f} is not before end "
                              f"{end:.3f}"})
        return out
    if start < -EPS:
        out.append({"segment": sid, "kind": "structure", "time": r3(start),
                    "reason": f"segment starts before zero ({start:.3f})"})
    if duration is not None and end > duration + EPS:
        out.append({"segment": sid, "kind": "structure", "time": r3(end),
                    "reason": f"segment ends at {end:.3f}, past the source "
                              f"duration {duration:.3f}"})

    for field in ("quote", "reason"):
        value = seg.get(field)
        if value is None or not str(value).strip():
            out.append({"segment": sid, "kind": "provenance",
                        "reason": f"segment has no {field}; every EDL segment "
                                  "records the words it carries and why"})

    for edge, t in (("start", start), ("end", end)):
        if (source, r3(t)) in exempt:
            continue
        miss = check_boundary(t, silence, words, tolerance)
        if miss is None:
            continue
        detail = dict(miss)
        detail["segment"] = sid
        detail["kind"] = "boundary"
        detail["edge"] = edge
        where = ""
        if "distance" in detail:
            where = (f"; nearest silence is {detail['distance']:.3f}s away at "
                     f"{detail['nearest_silence']:.3f}")
        else:
            where = "; this source has no detected silence at all"
        word = ""
        if "inside_word" in detail:
            word = (f', and it lands inside the word "{detail["inside_word"]}"'
                    f" ({detail['word_span'][0]:.3f}-"
                    f"{detail['word_span'][1]:.3f})")
        detail["reason"] = (
            f"segment {edge} {t:.3f} does not rest in an audio-verified "
            f"silence{where}{word}. Snap it with snap_spans.py instead of "
            "placing it by hand.")
        out.append(detail)
    return out


def build_report(edl, maps, transcripts, tolerance=DEFAULT_TOLERANCE_S):
    """Verify every segment and assemble the verdict (pure).

    maps and transcripts are {source_key: value} indexes; a single entry
    keyed None applies to every segment.
    """
    segments = edl["segments"]
    duration = edl.get("source_duration")
    duration = None if duration is None else float(duration)
    exempt = natural_edges(segments, duration)

    violations = []
    boundaries = 0
    for i, seg in enumerate(segments):
        source = seg.get("source")
        silence = _pick(maps, source)
        words = _pick(transcripts, source)
        if silence is None:
            violations.append({
                "segment": seg.get("id", i), "kind": "structure",
                "reason": f"no audio map covers source {source!r}; run "
                          "analyze_audio.py on it"})
            continue
        for edge in ("start", "end"):
            if (source, r3(seg.get(edge, 0))) not in exempt:
                boundaries += 1
        violations.extend(verify_segment(i, seg, silence, words or [],
                                         duration, exempt, tolerance))

    return {
        "ok": not violations,
        "segments": len(segments),
        "boundaries": boundaries,
        "exempt": sorted({r3(t) for _, t in exempt}),
        "tolerance": tolerance,
        "violations": violations,
    }


def _pick(index, source):
    """Look a source up in a {key: value} index (pure).

    A lone entry keyed None applies to everything, which is the single-source
    project. Otherwise match the resolved path, then the basename.
    """
    if None in index:
        return index[None]
    if source in index:
        return index[source]
    try:
        resolved = str(Path(source).resolve())
    except (TypeError, OSError):
        resolved = None
    if resolved and resolved in index:
        return index[resolved]
    base = Path(source).name if source else None
    return index.get(base)


def _load(path, label):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"verify_edl: cannot read {label} {path}: {e}", file=sys.stderr)
        return None


def _index(payloads, extract, single):
    """Index loaded payloads by their media path, or by None when there is one."""
    if len(payloads) == 1 and single:
        return {None: extract(payloads[0])}
    out = {}
    for p in payloads:
        media = p.get("media") or p.get("source")
        value = extract(p)
        if media:
            out[str(media)] = value
            try:
                out[str(Path(media).resolve())] = value
            except (TypeError, OSError):
                pass
            out[Path(str(media)).name] = value
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("edl", help="path to cut/edl.json")
    p.add_argument("--audio-map", required=True, action="append",
                   help="path to cut/audio-map.json from analyze_audio.py; "
                        "repeat once per source on a multi-source project")
    p.add_argument("--words", required=True, action="append",
                   help="path to transcript/words.json; repeat once per "
                        "source on a multi-source project")
    p.add_argument("-o", "--output", default=None,
                   help="optional path for the full report JSON")
    p.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE_S,
                   help=f"seconds a boundary may sit outside a silence "
                        f"(default {DEFAULT_TOLERANCE_S}; raise only to "
                        "triage an inherited EDL)")
    args = p.parse_args(argv)

    edl = _load(args.edl, "edl")
    if edl is None:
        return 2
    if not edl.get("segments"):
        print("verify_edl: edl has no segments", file=sys.stderr)
        return 2

    raw_maps = [_load(m, "audio map") for m in args.audio_map]
    if any(m is None for m in raw_maps):
        return 2
    for m, path in zip(raw_maps, args.audio_map):
        if "silence" not in m:
            print(f"verify_edl: audio map {path} has no 'silence' key; "
                  "regenerate it with analyze_audio.py", file=sys.stderr)
            return 2
    raw_words = [_load(w, "transcript") for w in args.words]
    if any(w is None for w in raw_words):
        return 2
    for w, path in zip(raw_words, args.words):
        if "words" not in w:
            print(f"verify_edl: transcript {path} has no 'words' key",
                  file=sys.stderr)
            return 2

    maps = _index(raw_maps, lambda m: audio.to_pairs(m["silence"]),
                  single=len(raw_maps) == 1)
    transcripts = _index(raw_words, lambda w: w["words"],
                         single=len(raw_words) == 1)

    report = build_report(edl, maps, transcripts, args.tolerance)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")

    print(json.dumps({k: report[k] for k in
                      ("ok", "segments", "boundaries", "tolerance")}, indent=2))

    if report["ok"]:
        return 0

    print(f"\nEDL VERIFICATION FAILED: {len(report['violations'])} problem(s). "
          "Do NOT render, export a timeline, or present this cut.",
          file=sys.stderr)
    for v in report["violations"]:
        print(f"  segment {v['segment']} [{v['kind']}]: {v['reason']}",
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
