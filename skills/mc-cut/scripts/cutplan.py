#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Derive a mechanical cut candidate list from a word-level transcript (phase 3).

Usage:
    uv run {skill-root}/scripts/cutplan.py {projects-path}/<slug>/transcript/words.json \
        --audio-map {projects-path}/<slug>/cut/audio-map.json \
        -o {projects-path}/<slug>/cut/candidates.json

The two-source rule (binding; the defect that shipped a corrupt cut):
    The TRANSCRIPT is the authority on CONTENT: which words were said, in
    what order, so a detector can recognize a filler, a stutter, a retake.
    The AUDIO is the authority on TIMING: where silence is, and therefore
    where a cut is safe. Every candidate's TEXT comes from words.json; every
    candidate's EDGES are snapped into an audio-verified silence.

    Never time a cut off transcript timestamps. parakeet absorbs a pause into
    the preceding word's end, so word gaps read about 0.0 across real dead
    air and word ends reach past the sound. Both failure modes shipped on
    2026-07-24: the silence detector found 12 silences in a take with over 5
    minutes of dead air (the audio had 402 totalling 309s), and a stutter
    candidate whose end came from an absorbed word end clipped the repeat's
    onset into an audible "n-now". See analyze_audio.py.

Contract:
    input   Scribe word-level transcript JSON (from transcribe.py) with shape
            {"media": str, "duration": float, "text": str,
             "words": [{"word", "start", "end", "confidence", "i",
                        "gap_before", "gap_after"}, ...]}
    output  candidates.json: every mechanical cut candidate the detectors below
            find, each with timestamps, the surrounding words, a human reason,
            and a severity. Shape:
            {"media", "duration",
             "thresholds": {"min_silence", "retake_window", "retake_run",
                            "snap_ms"},
             "silence_source": "audio",
             "counts": {"silence", "filler", "stutter", "retake", "blooper",
                        "marker"},
             "trimmable_silence_seconds": float,
             "unsnapped": int,
             "candidates": [ {"type", ["cls"], "start", "end", "dur",
                              "text", "reason", "severity", "snapped"}, ... ]}
            Candidates are sorted by start time; times carry 2 decimals; "cls"
            (hard|soft) appears on filler candidates only. "snapped" is false
            when an edge could not reach an audio silence within --snap-ms,
            meaning that candidate's edges still rest on transcript
            timestamps and need an ear before they are cut.
    note    this script finds CANDIDATES only; taste calls (keep or cut) happen
            in mc-cut's plan, which the creator approves at gate 2. Cutting rules
            live in this skill's SKILL.md (the "Cutting rules" section).

Every candidate's span is THE PART TO REMOVE, uniformly across types.

Detectors (all pure stdlib):
    silence   dead-air tightening from the AUDIO map. Interior silences
              >= min-silence (default 0.30s) are trimmed to keep-ms (default
              200ms) of breathing room, split evenly so both edges land
              inside silence; leading and trailing silence trims to keep-ms
              off the first and last word. Silences BELOW min-silence are
              untouched: those micro-beats are the speaker's rhythm, and
              flattening them is what makes a cut sound machine-gunned.
              severity med if the silence is < 2.0s, high if >= 2.0s. Carries
              silence_start/silence_end/keep_ms alongside the trim span.
    filler    hard fillers (um uh hmm er ah mm; severity high) matched word-
              boundary, case-insensitive, punctuation-stripped; consecutive hard
              fillers merge into one candidate spanning the run. soft fillers
              (severity low, cadence-sensitive, DEFAULT IS TO KEEP) flagged
              only at a sentence start (prev word ends ./!/? or gap_before >=
              0.5). The soft list is deliberately tiny and the creator's
              voice bible extends or overrides it via --voice-bible; see
              SOFT_SINGLE's comment for why blanket soft-filler cutting is a
              bug, not a feature.
    stutter   immediate normalized word repetition ("weird weird"); candidate
              covers the first occurrence. severity med.
    retake    (a) spoken cues (case-insensitive): "take N", "try that again",
              "whoops", "let me start over", "start over", "scratch that";
              (b) verbatim repeats: a run of >= retake-run (default 3) consecutive
              normalized words that reappears within the next retake-window
              (default 16) words -- the EARLIER occurrence is the candidate.
              severity high.
              (c) SECTION re-reads (cls "section"): a run of >= section-run
              (default 8) words recurring within section-window-s (default
              45s). The candidate spans the first attempt's start to the
              restart's start, so the abandoned take AND its reset pause both
              go. The locality window is in SECONDS on purpose: that is what
              distinguishes a redo from a deliberate callback minutes later,
              and word-distance cannot express it.
    blooper   expletives and reset phrases the creator would never ship
              ("Oh fuck.", "scratch that", "sorry"). severity high with cls
              "reset" when the take STOPPED next to it (a silence of
              reset-silence seconds or more within reset-look seconds; a
              near-certain flub), med with cls "ambiguous" in continuous
              speech (possibly scripted, e.g. "that damn term") so an ear
              settles it. Measured separation on real footage: 0.77s of
              silence beside the scripted line, 7.65s beside the blooper.
              --blooper-cues overrides the vocabulary.
    marker    interview-mode cue: any marker phrase (default "question from
              the interviewer") in the normalized word stream; marks a segment
              boundary (the creator read an interviewer question aloud on
              camera). severity med. --marker-cues overrides the list
              (comma-separated, so several phrases can be active at once);
              projects recorded against the older "question from claude"
              convention pass --marker-cues "question from claude".

CLI:
    positional  words.json
    -o/--output candidates.json (required)
    --audio-map PATH        audio-map.json (REQUIRED; no gap fallback exists)
    --snap-ms INT           (default 250) candidate edge snap budget
    --min-silence FLOAT     (default 0.30) tightening floor
    --keep-ms INT           (default 200) breathing room kept per silence
    --retake-window INT     (default 16)
    --retake-run INT        (default 3)
    --section-run INT       (default 8) words that make a section re-read
    --section-window-s FLT  (default 45.0) redo-versus-callback locality
    --voice-bible PATH      creator's cadence keep/cut lists
    --blooper-cues STR      comma-separated blooper vocabulary override
    --marker-cues STR       comma-separated override (default "question from
                            the interviewer"; the legacy phrase "question from
                            claude" is a supported alternative)
    exit 0 ok, 1 failure, 2 usage error. A JSON summary (counts + output path)
    is printed to stdout.
"""

import argparse
import json
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # noqa: E402
import analyze_audio as audio  # noqa: E402

# How far a candidate edge may move to reach an audio-verified silence.
DEFAULT_SNAP_MS = 250
# Breathing room left in a tightened interior silence. 200ms reads as a beat;
# zero reads as machine-gunned.
DEFAULT_KEEP_MS = 200
# Section-redo matcher: a long word run inside a seconds-wide locality
# window. See _find_section_redo for why the window is time, not words.
DEFAULT_SECTION_RUN = 8
DEFAULT_SECTION_WINDOW_S = 45.0
# Blooper context: a genuine flub is next to a long STOP, not a breath. See
# _near_reset for the measured separation (0.77s scripted vs 7.65s blooper).
DEFAULT_RESET_SILENCE_S = 2.0
DEFAULT_RESET_LOOK_S = 1.5
# Interior silences shorter than this are the speaker's rhythm, not dead air.
#
# Measured on the real 20.5 minute take from 2026-07-24 (929 silences at or
# above 0.1s, 383s of silence total). How much trimmable dead air each
# candidate floor reaches:
#
#   floor   silences hit   trimmable   share of all trimmable dead air
#   0.20    452            230.6s      100.0%
#   0.30    400            228.5s       99.1%
#   0.45    248            199.9s       86.7%
#   0.70     92            148.0s       64.2%
#
# 0.30 is the knee. It catches 99% of the dead air while sitting clear of
# that speaker's natural rhythm (their MEDIAN silence is 0.19s, which is
# inter-phrase cadence, not dead air). The 0.45 this shipped with left about
# 29 seconds of slack in a 20 minute video, which is exactly the "loose"
# quality the first cut was criticized for. Going below 0.30 gains under a
# percent and starts eating the speaker's rhythm.
#
# This is a PACING knob and it is per-creator: a slower, more deliberate
# delivery wants it higher, which is why the studio config exposes it through
# [cut] cutplan-flags.
DEFAULT_MIN_SILENCE = 0.30

HARD_FILLERS = {"um", "uh", "hmm", "er", "ah", "mm"}
# Soft fillers are CADENCE-SENSITIVE and the default list is deliberately
# short. It used to include "so", "right", "okay", "well" and "anyway", which
# meant the mechanical pass flagged all 19 of one creator's sentence-initial
# "So"s on a single take. Their voice bible names "so" as their natural
# connective glue; blanket-cutting it destroys the speaker's cadence and
# produces a technically-clean, tonally-dead read.
#
# A speaker's connective words are TASTE, and taste lives in files. The
# per-creator list comes from the voice bible via --voice-bible (see
# parse_voice_cadence); this default is only the small set that is hard to
# defend as anyone's deliberate rhythm.
SOFT_SINGLE = {"basically", "actually", "literally"}
SOFT_PHRASES = [["you", "know"], ["i", "mean"]]
# Expletives and reset phrases: a genuine blooper the creator would never
# ship. Detected separately from retakes because the ACTION differs (a
# blooper is always cut; a retake is a choice between takes) and because the
# vocabulary is per-creator. --blooper-cues overrides.
BLOOPER_WORDS = {"fuck", "shit", "damn", "crap", "ugh", "oops", "oof",
                 "bollocks", "bugger"}
BLOOPER_PHRASES = [
    ["let", "me", "redo", "that"],
    ["let", "me", "try", "again"],
    ["scratch", "that"],
    ["start", "over"],
    ["sorry"],
]
NUMBER_WORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight",
                "nine", "ten"}
# spoken retake cues, checked longest-first at each position ("take N" handled
# separately because its second token is a number, not a literal)
CUE_PHRASES = [
    ["let", "me", "start", "over"],
    ["try", "that", "again"],
    ["scratch", "that"],
    ["start", "over"],
    ["whoops"],
]

_STRIP = string.punctuation


def norm(word):
    """Lowercase and strip surrounding punctuation; keep internal apostrophes."""
    return word.strip(_STRIP).lower()


def fmt(x):
    """Round to 2 decimals and render without trailing zeros, for reasons."""
    return str(round(x, 2))


def r2(x):
    return round(x, 2)


def _cand(ctype, start, end, text, reason, severity, cls=None):
    c = {"type": ctype}
    if cls is not None:
        c["cls"] = cls
    c["start"] = r2(start)
    c["end"] = r2(end)
    c["dur"] = r2(end - start)
    c["text"] = text
    c["reason"] = reason
    c["severity"] = severity
    return c


def _word_at(words, t, side):
    """The word just before ('prev') or just after ('next') time t (pure).
    Used only to LABEL a silence candidate, never to time it."""
    if side == "prev":
        best = None
        for w in words:
            if w["end"] <= t + 0.01:
                best = w
            else:
                break
        return best
    for w in words:
        if w["start"] >= t - 0.01:
            return w
    return None


def detect_silence(words, duration, min_silence, silence_intervals,
                   keep_ms=DEFAULT_KEEP_MS):
    """Dead-air tightening candidates from the AUDIO silence map.

    silence_intervals is the (start, end) list out of analyze_audio.py. The
    transcript is used only to name the neighbouring words in the reason
    string, so a reader of cutplan.md knows where a trim sits.

    This used to compute `cur["start"] - prev["end"]` over transcript
    timestamps. That was the defect that shipped a bad cut on 2026-07-24:
    parakeet absorbs a pause into the preceding word's end, so those gaps
    read about 0.0 across real dead air. On a take with over 5 minutes of
    dead air the gap method found 12 silences; the audio found 402 totalling
    309 seconds. Do not put word gaps back here.

    A candidate's span is THE PART TO REMOVE, not the whole silence, which
    matches what every other detector here emits and makes the candidate
    list uniformly "spans you might cut".

    Tightening, not flattening (the single biggest quality lever on a
    talking-head read): an interior silence at or above min_silence is
    trimmed down to keep_ms of breathing room rather than removed outright,
    with the kept beat split evenly on both sides so both cut edges sit
    inside silence by construction. Silences BELOW min_silence are left
    completely alone: those micro-beats are the speaker's rhythm, and
    removing them is what makes an edit sound machine-gunned. Leading and
    trailing silence is different, there is nothing to breathe between, so
    the head and tail trim all the way to keep_ms off the first and last
    word.
    """
    out = []
    keep = keep_ms / 1000.0
    for start, end in silence_intervals:
        dur = end - start
        if dur < min_silence:
            continue
        sev = "high" if dur >= 2.0 else "med"
        head = start <= 0.01
        tail = end >= duration - 0.01
        if head:
            cut_start, cut_end = start, max(start, end - keep)
            nxt = _word_at(words, end, "next")
            where = f' before "{nxt["word"]}"' if nxt else " at the head"
        elif tail:
            cut_start, cut_end = min(end, start + keep), end
            prv = _word_at(words, start, "prev")
            where = f' after "{prv["word"]}"' if prv else " at the tail"
        else:
            if dur <= keep:
                continue
            pad = keep / 2.0
            cut_start, cut_end = start + pad, end - pad
            nxt = _word_at(words, end, "next")
            where = f' before "{nxt["word"]}"' if nxt else ""
        removed = cut_end - cut_start
        if removed <= 0.01:
            continue
        c = _cand("silence", cut_start, cut_end, "",
                  f"{fmt(r2(dur))}s silence{where}, tighten to "
                  f"{fmt(r2(dur - removed))}s "
                  f"(remove {fmt(r2(removed))}s)", sev)
        c["silence_start"] = r2(start)
        c["silence_end"] = r2(end)
        c["keep_ms"] = keep_ms
        out.append(c)
    return out


def snap_candidates(cands, silence_intervals, max_shift):
    """Move every candidate edge into an audio-verified silence (pure).

    A cut landing inside real silence CANNOT clip a word, which turns the
    "never cut inside a word" rule from an assertion about timestamps into a
    structural guarantee. Edges that cannot reach a silence within max_shift
    are left alone and marked `snapped: false`, so the gate sees which
    candidates still carry timestamp risk instead of the script pretending
    they are safe.

    This is also the fix for the audible "n-now" artifact in the first real
    cut: a stutter candidate's end came from a pause-absorbed word end, so it
    reached into the repeat's onset and clipped it. Snapping puts the edge in
    the silence between the two takes.

    Snapping is DIRECTIONAL: a start may only move earlier and an end only
    later, so a candidate can widen into surrounding silence (always safe for
    a span being removed) but can never invert or collapse onto itself.
    """
    for c in cands:
        if c["type"] == "silence":
            c["snapped"] = True
            continue
        start = audio.nearest_silence(silence_intervals, c["start"], max_shift,
                                      direction="back")
        end = audio.nearest_silence(silence_intervals, c["end"], max_shift,
                                    direction="forward")
        c["snapped"] = start is not None and end is not None
        if start is not None:
            c["start"] = r2(start)
        if end is not None:
            c["end"] = r2(end)
        if c["end"] < c["start"]:
            c["end"] = c["start"]
        c["dur"] = r2(c["end"] - c["start"])
    return cands


def _is_sentence_start(words, i):
    if i == 0:
        return True
    prev = words[i - 1]["word"]
    if any(prev.endswith(p) for p in ".!?"):
        return True
    gap = words[i]["start"] - words[i - 1]["end"]
    return gap >= 0.5


def detect_fillers(words, nwords, soft_single=None, soft_phrases=None,
                   hard_fillers=None):
    """Hard fillers always, soft (cadence-sensitive) fillers conservatively.

    soft_single/soft_phrases come from the voice bible when one is supplied,
    so a creator's connective glue is never flagged. See SOFT_SINGLE's
    comment for why the default list is short."""
    hard_fillers = HARD_FILLERS if hard_fillers is None else hard_fillers
    soft_single = SOFT_SINGLE if soft_single is None else soft_single
    soft_phrases = SOFT_PHRASES if soft_phrases is None else soft_phrases
    out = []
    n = len(words)
    i = 0
    while i < n:
        if nwords[i] in hard_fillers:
            j = i
            while j + 1 < n and nwords[j + 1] in hard_fillers:
                j += 1
            text = " ".join(w["word"] for w in words[i:j + 1])
            if j > i:
                reason = f'hard filler run "{text}"'
            else:
                reason = f'hard filler "{text}"'
            out.append(_cand("filler", words[i]["start"], words[j]["end"],
                             text, reason, "high", cls="hard"))
            i = j + 1
            continue
        # soft fillers: only at a sentence start
        if _is_sentence_start(words, i):
            matched = None
            for phrase in soft_phrases:
                L = len(phrase)
                if nwords[i:i + L] == phrase:
                    matched = (L, " ".join(phrase))
                    break
            if matched is None and nwords[i] in soft_single:
                matched = (1, nwords[i])
            if matched is not None:
                L, canon = matched
                text = " ".join(w["word"] for w in words[i:i + L])
                out.append(_cand("filler", words[i]["start"],
                                 words[i + L - 1]["end"], text,
                                 f'soft filler "{text}" (cadence-sensitive, '
                                 "default is to KEEP)", "low", cls="soft"))
                i += L
                continue
        i += 1
    return out


def detect_stutter(words, nwords):
    out = []
    for i in range(len(words) - 1):
        a, b = nwords[i], nwords[i + 1]
        if a and a == b:
            out.append(_cand("stutter", words[i]["start"], words[i]["end"],
                             words[i]["word"],
                             f'stutter "{words[i]["word"]} {words[i + 1]["word"]}"',
                             "med"))
    return out


def _match_cue(nwords, i):
    """Return (length, canonical cue) if a spoken retake cue starts at i."""
    if nwords[i] == "take" and i + 1 < len(nwords):
        nxt = nwords[i + 1]
        if nxt in NUMBER_WORDS or nxt.isdigit():
            return 2, f"take {nxt}"
    for phrase in CUE_PHRASES:
        L = len(phrase)
        if nwords[i:i + L] == phrase:
            return L, " ".join(phrase)
    return 0, None


def _find_verbatim(nwords, run_min, window):
    """Runs of >= run_min normalized words that recur (non-overlapping) within
    `window` words. Yields (start_i, end_i) of the EARLIER occurrence."""
    n = len(nwords)
    out = []
    i = 0
    while i < n:
        best_m = 0
        jmax = min(n - 1, i + window)
        for j in range(i + 1, jmax + 1):
            m = 0
            while (i + m < j and j + m < n and nwords[i + m]
                   and nwords[i + m] == nwords[j + m]):
                m += 1
            if m >= run_min and m > best_m:
                best_m = m
        if best_m >= run_min:
            out.append((i, i + best_m - 1))
            i += best_m
        else:
            i += 1
    return out


def detect_retakes(words, nwords, run_min, window):
    out = []
    n = len(words)
    # (a) spoken cues
    i = 0
    while i < n:
        L, canon = _match_cue(nwords, i)
        if L:
            text = " ".join(w["word"] for w in words[i:i + L])
            out.append(_cand("retake", words[i]["start"], words[i + L - 1]["end"],
                             text, f'retake cue "{canon}"', "high"))
            i += L
        else:
            i += 1
    # (b) verbatim repeats
    for a, b in _find_verbatim(nwords, run_min, window):
        text = " ".join(w["word"] for w in words[a:b + 1])
        out.append(_cand("retake", words[a]["start"], words[b]["end"], text,
                         f'repeated phrase "{text}"', "high"))
    return out


def _find_section_redo(words, nwords, run_min, window_s):
    """Section-scale re-reads: (abandoned_start_i, restart_i, run) (pure).

    The mechanical short-range matcher (_find_verbatim) looks 16 WORDS ahead
    for a 3-word repeat, which catches adjacent stumbles and nothing larger.
    On the real take it undersized a memory-paragraph redo from about 34s to
    about 11s and missed the reset entirely: the creator restarted a whole
    section, and the abandoned attempt shipped.

    So this matcher is deliberately the opposite shape: a LONG run (many
    words, so it cannot fire on coincidence) inside a locality window
    measured in SECONDS rather than words. The seconds constraint is what
    separates a redo from a callback. A creator re-reading a paragraph
    restarts within a few tens of seconds; a deliberate callback to an
    earlier line lands minutes later and must NOT be treated as a retake.
    Word-distance cannot express that difference because the abandoned take
    plus the reset pause is itself a variable number of words.

    The candidate span runs from the FIRST attempt's start to the RESTART's
    start, so it swallows the abandoned take and the reset pause together,
    which is the whole point: trimming only the repeated words leaves the
    stall in the middle.
    """
    n = len(nwords)
    out = []
    i = 0
    while i < n:
        best = None
        j = i + 1
        while j < n and words[j]["start"] - words[i]["start"] <= window_s:
            m = 0
            while (i + m < j and j + m < n and nwords[i + m]
                   and nwords[i + m] == nwords[j + m]):
                m += 1
            if m >= run_min and (best is None or m > best[1]):
                best = (j, m)
            j += 1
        if best is not None:
            out.append((i, best[0], best[1]))
            i = best[0]
        else:
            i += 1
    return out


def detect_section_redos(words, nwords, run_min, window_s):
    out = []
    for a, restart, run in _find_section_redo(words, nwords, run_min,
                                              window_s):
        text = " ".join(w["word"] for w in words[a:a + run])
        span = words[restart]["start"] - words[a]["start"]
        c = _cand("retake", words[a]["start"], words[restart]["start"], text,
                  f'section re-read: {run} words repeated after '
                  f'{fmt(r2(span))}s, keep the later take and cut the '
                  f'abandoned one ("{text[:60]}...")', "high")
        c["cls"] = "section"
        out.append(c)
    return out


def _near_reset(words, i, silence_intervals, look_s=DEFAULT_RESET_LOOK_S,
                reset_min=DEFAULT_RESET_SILENCE_S):
    """True when the take STOPPED next to word i (pure).

    The signal that separates a genuine blooper from scripted usage. Someone
    who swears inside a scripted line keeps talking; someone who fluffs a
    take stops dead, and that stop is long and audible.

    Measured on the real 2026-07-24 take, which contains one of each:
        "that damn term"  (scripted)  largest adjacent silence 0.77s
        "Oh fuck."        (blooper)   followed by 7.65s of silence
    So the discriminator is not "is there a pause nearby", which is true of
    almost any word in natural speech, but "is there a LONG stop". An
    earlier version of this asked only for 0.5s within 3s and duly marked
    the scripted line as almost certainly a flub.

    Proximity is measured span-to-span with overlap counting as adjacent,
    because parakeet absorbs a pause into the preceding word's end: the
    blooper's word span literally overlaps the silence that follows it, and
    an edge-to-edge comparison misses exactly the case that matters.
    """
    w = words[i]
    for start, end in silence_intervals:
        if end - start < reset_min:
            continue
        distance = max(start - w["end"], w["start"] - end)
        if distance <= look_s:
            return True
    return False


def detect_bloopers(words, nwords, silence_intervals, blooper_words,
                    blooper_phrases, look_s=DEFAULT_RESET_LOOK_S):
    """Expletives and reset phrases as their own candidate type.

    The real take contained an explicit "Oh fuck." at 13:59 that the
    mechanical pass left in; it would have shipped. The retake detector never
    saw it because CUE_PHRASES has no expletives, and the filler detector
    never saw it because it is not a filler.

    Severity encodes the scripted-versus-genuine judgment rather than
    guessing it away: a marker next to a long pause is a near-certain blooper
    (high), one in continuous speech might be deliberate (med, flagged for an
    ear). Nothing here is auto-cut; these are gate-2 candidates like
    everything else.
    """
    out = []
    n = len(words)
    i = 0
    while i < n:
        matched = None
        for phrase in blooper_phrases:
            L = len(phrase)
            if nwords[i:i + L] == phrase:
                matched = (L, " ".join(phrase))
                break
        if matched is None and nwords[i] in blooper_words:
            matched = (1, nwords[i])
        if matched is None:
            i += 1
            continue
        L, canon = matched
        text = " ".join(w["word"] for w in words[i:i + L])
        reset = _near_reset(words, i, silence_intervals, look_s)
        if reset:
            reason = f'blooper "{text}" next to a pause; almost certainly a flub'
            sev = "high"
        else:
            reason = (f'"{text}" in continuous speech; may be scripted usage, '
                      "confirm by ear before cutting")
            sev = "med"
        c = _cand("blooper", words[i]["start"], words[i + L - 1]["end"], text,
                  reason, sev)
        c["cls"] = "reset" if reset else "ambiguous"
        out.append(c)
        i += L
    return out


def parse_voice_cadence(text):
    """Read keep/cut word lists out of a voice bible's cadence block (pure).

    The voice bible is the creator's taste file, so their connective words
    belong there and not in this script's constants. The block is a fenced
    markdown code block tagged `cadence`:

        ```cadence
        keep: so, here's the thing, which means, look
        cut: um, uh, hmm, basically
        ```

    keep wins over cut on conflict: preserving a speaker's rhythm is the
    safer failure, since a kept filler is a small blemish and a cut cadence
    word changes how they sound. Returns (keep_set, cut_set) of normalized
    phrases; a file with no cadence block yields two empty sets, which leaves
    the conservative defaults in place.
    """
    keep, cut = set(), set()
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            tag = stripped[3:].strip().lower()
            if in_block:
                in_block = False
            elif tag == "cadence":
                in_block = True
            continue
        if not in_block or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        target = {"keep": keep, "cut": cut}.get(key.strip().lower())
        if target is None:
            continue
        for item in value.split(","):
            phrase = " ".join(norm(w) for w in item.split())
            if phrase:
                target.add(phrase)
    return keep, cut - keep


def detect_markers(words, nwords, cues):
    out = []
    n = len(words)
    for cue in cues:
        toks = cue.split()
        L = len(toks)
        if L == 0:
            continue
        i = 0
        while i <= n - L:
            if nwords[i:i + L] == toks:
                text = " ".join(w["word"] for w in words[i:i + L])
                out.append(_cand("marker", words[i]["start"],
                                 words[i + L - 1]["end"], text,
                                 f'interview marker "{cue}"', "med"))
                i += L
            else:
                i += 1
    return out


CANDIDATE_TYPES = ("silence", "filler", "stutter", "retake", "blooper",
                   "marker")


def build(data, min_silence, retake_window, retake_run, marker_cues,
          silence_intervals, snap_ms=DEFAULT_SNAP_MS,
          keep_ms=DEFAULT_KEEP_MS, section_run=DEFAULT_SECTION_RUN,
          section_window_s=DEFAULT_SECTION_WINDOW_S,
          voice_keep=(), voice_cut=(),
          blooper_words=None, blooper_phrases=None):
    words = data["words"]
    duration = data["duration"]
    nwords = [norm(w["word"]) for w in words]

    # Voice bible overlay: keep wins over cut, and a kept word is removed
    # from every filler list including the hard ones (a creator who says
    # "hmm" deliberately gets to keep it).
    keep = set(voice_keep)
    hard = {w for w in HARD_FILLERS if w not in keep}
    soft_single = ({w for w in SOFT_SINGLE if w not in keep}
                   | {c for c in voice_cut if " " not in c and c not in keep})
    soft_phrases = [p for p in SOFT_PHRASES if " ".join(p) not in keep]
    soft_phrases += [c.split() for c in voice_cut
                     if " " in c and c not in keep]

    cands = []
    cands += detect_silence(words, duration, min_silence, silence_intervals,
                            keep_ms=keep_ms)
    cands += detect_fillers(words, nwords, soft_single=soft_single,
                            soft_phrases=soft_phrases, hard_fillers=hard)
    cands += detect_stutter(words, nwords)
    cands += detect_retakes(words, nwords, retake_run, retake_window)
    cands += detect_section_redos(words, nwords, section_run, section_window_s)
    cands += detect_bloopers(
        words, nwords, silence_intervals,
        BLOOPER_WORDS if blooper_words is None else blooper_words,
        BLOOPER_PHRASES if blooper_phrases is None else blooper_phrases)
    cands += detect_markers(words, nwords, marker_cues)

    snap_candidates(cands, silence_intervals, snap_ms / 1000.0)
    cands.sort(key=lambda c: (c["start"], c["end"], c["type"]))

    counts = {t: 0 for t in CANDIDATE_TYPES}
    for c in cands:
        counts[c["type"]] += 1

    trimmable = sum(c["dur"] for c in cands if c["type"] == "silence")
    return {
        "media": data.get("media", ""),
        "duration": duration,
        "thresholds": {
            "min_silence": min_silence,
            "retake_window": retake_window,
            "retake_run": retake_run,
            "snap_ms": snap_ms,
            "keep_ms": keep_ms,
            "section_run": section_run,
            "section_window_s": section_window_s,
        },
        "silence_source": "audio",
        "voice_bible_applied": bool(voice_keep or voice_cut),
        "counts": counts,
        "trimmable_silence_seconds": r2(trimmable),
        "unsnapped": sum(1 for c in cands if not c.get("snapped")),
        "candidates": cands,
    }


# Arguments the SKILL owns and a configured flags string must never reach.
# The skill appends [cut] cutplan-flags AFTER these, and argparse lets a later
# occurrence win, so without this the studio config could redirect the output
# or, far worse, point --audio-map somewhere else and quietly break the
# two-source rule the whole stage rests on. The config comment states the
# boundary; this enforces it.
PROTECTED_FLAGS = ("-o", "--output", "--audio-map", "--voice-bible")


def protected_conflicts(argv):
    """Protected flags supplied more than once (pure)."""
    counts = {}
    for token in argv:
        name = str(token).split("=", 1)[0]
        if name in PROTECTED_FLAGS:
            counts[name] = counts.get(name, 0) + 1
    conflicts = {f for f, n in counts.items() if n > 1}
    # -o and --output are the same destination under two spellings.
    if counts.get("-o", 0) + counts.get("--output", 0) > 1:
        conflicts.update({"-o", "--output"} & set(counts))
    return sorted(conflicts)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    conflicts = protected_conflicts(argv)
    if conflicts:
        print("cutplan: " + ", ".join(conflicts) + " supplied more than once. "
              "These are passed by the skill and must not be overridden from "
              "cutplan-flags: redirecting the output or the audio map from a "
              "config file breaks the two-source rule silently.",
              file=sys.stderr)
        return 2

    p = argparse.ArgumentParser(description="Find mechanical cut candidates in a "
                                            "word-level transcript.")
    p.add_argument("words", help="path to words.json (from transcribe.py)")
    p.add_argument("-o", "--output", required=True, help="path to candidates.json")
    p.add_argument("--min-silence", type=float, default=DEFAULT_MIN_SILENCE,
                   help=f"shortest interior silence to tighten (default "
                        f"{DEFAULT_MIN_SILENCE}; below this is cadence, not "
                        "dead air)")
    p.add_argument("--keep-ms", type=int, default=DEFAULT_KEEP_MS,
                   help=f"breathing room left in a tightened silence "
                        f"(default {DEFAULT_KEEP_MS})")
    p.add_argument("--retake-window", type=int, default=16)
    p.add_argument("--retake-run", type=int, default=3)
    p.add_argument("--section-run", type=int, default=DEFAULT_SECTION_RUN,
                   help=f"words that must repeat to count as a section "
                        f"re-read (default {DEFAULT_SECTION_RUN})")
    p.add_argument("--section-window-s", type=float,
                   default=DEFAULT_SECTION_WINDOW_S,
                   help=f"seconds within which a repeat is a redo rather "
                        f"than a callback (default {DEFAULT_SECTION_WINDOW_S})")
    p.add_argument("--voice-bible", default=None,
                   help="path to the creator's voice bible; its ```cadence "
                        "block's keep:/cut: lists override the built-in "
                        "soft-filler defaults")
    p.add_argument("--blooper-cues", default=None,
                   help="comma-separated override for the blooper vocabulary "
                        "(expletives and reset phrases)")
    p.add_argument("--marker-cues", default="question from the interviewer",
                   help='comma-separated marker phrases (legacy alternative: '
                        '"question from claude")')
    p.add_argument("--audio-map", required=True,
                   help="path to cut/audio-map.json from analyze_audio.py; "
                        "REQUIRED, silence comes from the audio and there is "
                        "no transcript-gap fallback (see detect_silence)")
    p.add_argument("--snap-ms", type=int, default=DEFAULT_SNAP_MS,
                   help=f"how far a candidate edge may move to land inside an "
                        f"audio silence (default {DEFAULT_SNAP_MS})")
    args = p.parse_args(argv)

    try:
        with open(args.words, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"cutplan: cannot read {args.words}: {e}", file=sys.stderr)
        return 1
    if "words" not in data or "duration" not in data:
        print("cutplan: input missing required 'words'/'duration' keys",
              file=sys.stderr)
        return 1

    try:
        with open(args.audio_map, encoding="utf-8") as f:
            audio_map = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"cutplan: cannot read audio map {args.audio_map}: {e}. "
              "Generate it first with analyze_audio.py; silence must come "
              "from the audio, not from transcript gaps.", file=sys.stderr)
        return 1
    if "silence" not in audio_map:
        print("cutplan: audio map has no 'silence' key; regenerate it with "
              "analyze_audio.py", file=sys.stderr)
        return 1
    silence_intervals = audio.to_pairs(audio_map["silence"])

    marker_cues = [norm_phrase for c in args.marker_cues.split(",")
                   if (norm_phrase := " ".join(norm(w) for w in c.split()))]

    voice_keep, voice_cut = set(), set()
    if args.voice_bible:
        try:
            voice_keep, voice_cut = parse_voice_cadence(
                Path(args.voice_bible).read_text(encoding="utf-8"))
        except OSError as e:
            print(f"cutplan: cannot read voice bible {args.voice_bible}: {e}",
                  file=sys.stderr)
            return 1
        if not voice_keep and not voice_cut:
            print(f"cutplan: no ```cadence block found in "
                  f"{args.voice_bible}; using the conservative built-in "
                  "soft-filler defaults. See the voice bible spec.",
                  file=sys.stderr)

    blooper_words, blooper_phrases = None, None
    if args.blooper_cues is not None:
        cues = [phrase for c in args.blooper_cues.split(",")
                if (phrase := " ".join(norm(w) for w in c.split()))]
        blooper_words = {c for c in cues if " " not in c}
        blooper_phrases = [c.split() for c in cues if " " in c]

    result = build(data, args.min_silence, args.retake_window,
                   args.retake_run, marker_cues, silence_intervals,
                   snap_ms=args.snap_ms, keep_ms=args.keep_ms,
                   section_run=args.section_run,
                   section_window_s=args.section_window_s,
                   voice_keep=voice_keep, voice_cut=voice_cut,
                   blooper_words=blooper_words,
                   blooper_phrases=blooper_phrases)

    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except OSError as e:
        print(f"cutplan: cannot write {args.output}: {e}", file=sys.stderr)
        return 1

    print(json.dumps({"ok": True, "output": args.output,
                      "silence_source": "audio",
                      "voice_bible_applied": result["voice_bible_applied"],
                      "counts": result["counts"],
                      "trimmable_silence_seconds":
                          result["trimmable_silence_seconds"],
                      "unsnapped": result["unsnapped"]}))
    if result["unsnapped"]:
        print(f"note: {result['unsnapped']} candidate(s) could not reach an "
              f"audio silence within {args.snap_ms}ms and carry "
              '"snapped": false. Their edges still rest on transcript '
              "timestamps; check them by ear before cutting.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
