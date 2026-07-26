#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Tests for cutplan.py: the cut-candidate finder must catch every planted
defect class, gate soft fillers to sentence starts, and emit the pinned schema
shape (cls on fillers only, candidates sorted by start)."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "cutplan.py"
_spec = importlib.util.spec_from_file_location("cutplan", SCRIPT)
cutplan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cutplan)
cutplan_parse = cutplan.parse_voice_cadence


def word(w, start, end, i, gap_before=0.0, gap_after=0.0, conf=1.0):
    return {"word": w, "start": start, "end": end, "confidence": conf,
            "i": i, "gap_before": gap_before, "gap_after": gap_after}


def seq(pairs, wgap=0.0):
    """Build words from (text, dur) pairs laid end to end, honoring an optional
    leading gap per word via a 3-tuple (text, dur, gap_before)."""
    words = []
    t = 0.0
    for idx, item in enumerate(pairs):
        if len(item) == 3:
            text, dur, gap = item
        else:
            text, dur = item
            gap = 0.0
        t = round(t + gap, 2)
        words.append(word(text, round(t, 2), round(t + dur, 2), idx,
                          gap_before=gap))
        t = round(t + dur, 2)
    return words


def silence_from_words(words, duration):
    """The audio map a perfect detector would produce for a synthetic take.

    Silence is everything not covered by a word span. In these fixtures the
    words are laid out deliberately, so their gaps ARE the real silence and
    this stands in for analyze_audio.py without needing ffmpeg or a media
    file. Real transcripts must never derive silence this way, which is the
    whole point of the audio map (see cutplan.py's two-source rule).
    """
    intervals = []
    cursor = 0.0
    for w in words:
        if w["start"] - cursor > 1e-6:
            intervals.append({"start": round(cursor, 3),
                              "end": round(w["start"], 3),
                              "dur": round(w["start"] - cursor, 3)})
        cursor = max(cursor, w["end"])
    if duration - cursor > 1e-6:
        intervals.append({"start": round(cursor, 3),
                          "end": round(duration, 3),
                          "dur": round(duration - cursor, 3)})
    return intervals


def run(words, duration=None, extra=None, expect=0, silence=None,
        with_audio_map=True):
    if duration is None:
        duration = words[-1]["end"] if words else 0.0
    data = {"media": "m.mp4", "duration": duration, "text": "", "words": words}
    if silence is None:
        silence = silence_from_words(words, duration)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "words.json"
        out = Path(tmp) / "candidates.json"
        amap = Path(tmp) / "audio-map.json"
        src.write_text(json.dumps(data))
        amap.write_text(json.dumps({
            "media": "m.mp4", "duration": duration,
            "noise_db": -30.0, "min_silence": 0.3,
            "silent_seconds": sum(s["dur"] for s in silence),
            "speech_seconds": duration - sum(s["dur"] for s in silence),
            "counts": {"silence": len(silence), "speech": 0},
            "silence": silence, "speech": [],
        }))
        argv = [sys.executable, str(SCRIPT), str(src), "-o", str(out)]
        if with_audio_map:
            argv += ["--audio-map", str(amap)]
        argv += list(extra or [])
        r = subprocess.run(argv, capture_output=True, text=True)
        assert r.returncode == expect, f"rc={r.returncode} stderr={r.stderr}"
        result = json.loads(out.read_text()) if r.returncode == 0 else None
        return result, r


def by_type(result, t):
    return [c for c in result["candidates"] if c["type"] == t]


class TestSilence(unittest.TestCase):
    """A silence candidate's span is THE PART TO REMOVE, not the whole
    silence: interior gaps are tightened down to keep_ms of breathing room,
    head and tail are trimmed to keep_ms off the first and last word."""

    def test_leading_mid_trailing(self):
        words = seq([("Hello,", 0.4, 1.0), ("world.", 0.4, 1.5)])
        result, _ = run(words, duration=round(words[-1]["end"] + 0.9, 2))
        sil = by_type(result, "silence")
        self.assertEqual(len(sil), 3)  # leading, mid, trailing
        self.assertEqual(sil[0]["start"], 0.0)   # head trims from 0
        self.assertEqual(sil[-1]["end"], result["duration"])  # tail to dur

    def test_head_trim_leaves_keep_ms_before_the_first_word(self):
        words = seq([("Hello,", 0.4, 1.0)])
        result, _ = run(words, duration=2.0)
        head = by_type(result, "silence")[0]
        self.assertEqual(head["start"], 0.0)
        self.assertAlmostEqual(head["end"], 0.8, places=2)  # 1.0 - 0.2

    def test_tail_trim_leaves_keep_ms_after_the_last_word(self):
        words = seq([("Hello.", 0.4, 0.1)])
        result, _ = run(words, duration=3.0)
        tail = by_type(result, "silence")[-1]
        self.assertAlmostEqual(tail["start"], 0.7, places=2)  # 0.5 + 0.2
        self.assertEqual(tail["end"], 3.0)

    def test_interior_gap_is_tightened_not_removed(self):
        # A 2.0s interior silence keeps 200ms, split evenly, so 1.8s goes.
        words = seq([("a", 0.3), ("b", 0.3, 2.0)])
        result, _ = run(words, duration=3.0)
        mid = [c for c in by_type(result, "silence")
               if c["silence_start"] == 0.3][0]
        self.assertAlmostEqual(mid["dur"], 1.8, places=2)
        self.assertAlmostEqual(mid["start"], 0.4, places=2)
        self.assertAlmostEqual(mid["end"], 2.2, places=2)
        self.assertEqual(mid["keep_ms"], 200)

    def test_tightened_edges_sit_inside_the_silence(self):
        words = seq([("a", 0.3), ("b", 0.3, 2.0)])
        result, _ = run(words, duration=3.0)
        mid = [c for c in by_type(result, "silence")
               if c["silence_start"] == 0.3][0]
        self.assertGreater(mid["start"], mid["silence_start"])
        self.assertLess(mid["end"], mid["silence_end"])

    def test_keep_ms_is_configurable(self):
        words = seq([("a", 0.3), ("b", 0.3, 2.0)])
        tight, _ = run(words, duration=3.0, extra=["--keep-ms", "0"])
        loose, _ = run(words, duration=3.0, extra=["--keep-ms", "600"])
        t = [c for c in by_type(tight, "silence")
             if c["silence_start"] == 0.3][0]
        l = [c for c in by_type(loose, "silence")
             if c["silence_start"] == 0.3][0]
        self.assertAlmostEqual(t["dur"], 2.0, places=2)
        self.assertAlmostEqual(l["dur"], 1.4, places=2)

    def test_severity_threshold(self):
        words = seq([("a", 0.3), ("b", 0.3, 1.0), ("c", 0.3, 2.5)])
        result, _ = run(words, duration=4.5)
        sev = {round(c["silence_end"] - c["silence_start"], 2): c["severity"]
               for c in by_type(result, "silence")}
        self.assertEqual(sev[1.0], "med")
        self.assertEqual(sev[2.5], "high")

    def test_micro_beats_below_threshold_are_left_alone(self):
        # 0.2s of silence is the speaker's rhythm, not dead air (the median
        # silence on the real reference take was 0.19s). Cutting these is
        # what makes an edit sound machine-gunned.
        words = seq([("a", 0.3), ("b", 0.3, 0.2)])
        result, _ = run(words, duration=round(words[-1]["end"] + 0.2, 2))
        interior = [c for c in by_type(result, "silence")
                    if c["silence_start"] > 0.01]
        self.assertEqual(interior, [])

    def test_min_silence_default_is_the_tightening_floor(self):
        words = seq([("a", 0.3), ("b", 0.3, 0.5)])
        result, _ = run(words, duration=round(words[-1]["end"] + 0.1, 2))
        interior = [c for c in by_type(result, "silence")
                    if 0.01 < c["silence_start"]]
        self.assertEqual(len(interior), 1)  # 0.5s is above the 0.45 floor

    def test_trimmable_seconds_are_totalled(self):
        words = seq([("a", 0.3), ("b", 0.3, 2.0)])
        result, _ = run(words, duration=3.0)
        self.assertAlmostEqual(
            result["trimmable_silence_seconds"],
            sum(c["dur"] for c in by_type(result, "silence")), places=2)


class TestFiller(unittest.TestCase):
    def test_hard_filler(self):
        words = seq([("So", 0.3), ("uh", 0.3), ("yes.", 0.3)])
        result, _ = run(words)
        hard = [c for c in by_type(result, "filler") if c["cls"] == "hard"]
        self.assertEqual(len(hard), 1)
        self.assertEqual(hard[0]["text"], "uh")
        self.assertEqual(hard[0]["severity"], "high")

    def test_consecutive_hard_merge(self):
        words = seq([("Um", 0.3), ("uh", 0.3), ("hmm.", 0.3), ("go.", 0.3)])
        result, _ = run(words)
        hard = [c for c in by_type(result, "filler") if c["cls"] == "hard"]
        self.assertEqual(len(hard), 1)
        self.assertEqual(hard[0]["start"], words[0]["start"])
        self.assertEqual(hard[0]["end"], words[2]["end"])
        self.assertIn("run", hard[0]["reason"])

    def test_soft_at_sentence_start(self):
        # "Basically" opens the clip -> flagged; mid-sentence use is not.
        words = seq([("Basically", 0.3), ("that", 0.3), ("is", 0.3),
                     ("it.", 0.3)])
        result, _ = run(words)
        soft = [c for c in by_type(result, "filler") if c["cls"] == "soft"]
        self.assertEqual([c["text"] for c in soft], ["Basically"])

    def test_soft_gated_after_period(self):
        # mid-sentence (no period, no gap) is NOT flagged
        words = seq([("I", 0.3), ("think", 0.3), ("basically", 0.3)])
        result, _ = run(words)
        self.assertEqual([c for c in by_type(result, "filler")
                          if c["cls"] == "soft"], [])

    def test_soft_gated_by_gap(self):
        # a soft filler after a >=0.5 gap counts as a sentence start
        words = seq([("wait", 0.3), ("basically", 0.3, 0.6), ("yes", 0.3)])
        result, _ = run(words)
        soft = [c for c in by_type(result, "filler") if c["cls"] == "soft"]
        self.assertEqual([c["text"] for c in soft], ["basically"])


class TestCadenceWordsAreNotFillers(unittest.TestCase):
    """The regression that made a creator's edit sound dead.

    The mechanical pass flagged all 19 sentence-initial "So"s on a real take.
    The voice bible names "so" as that speaker's natural connective glue.
    Cutting them is technically clean and tonally wrong, so the default list
    no longer contains cadence words at all."""

    def test_sentence_initial_so_is_not_flagged(self):
        words = seq([("So", 0.3), ("here", 0.3), ("we", 0.3), ("are.", 0.3)])
        result, _ = run(words)
        self.assertEqual([c for c in by_type(result, "filler")
                          if c["cls"] == "soft"], [])

    def test_other_cadence_words_are_not_flagged(self):
        for w in ("Right", "Okay", "Well", "Anyway", "Now", "Look"):
            words = seq([(w, 0.3), ("here", 0.3), ("we", 0.3), ("go.", 0.3)])
            result, _ = run(words)
            soft = [c for c in by_type(result, "filler")
                    if c["cls"] == "soft"]
            self.assertEqual(soft, [], f"{w} should not be a soft filler")

    def test_hard_fillers_are_still_cut(self):
        words = seq([("So", 0.3), ("uh", 0.3), ("here.", 0.3)])
        result, _ = run(words)
        hard = [c for c in by_type(result, "filler") if c["cls"] == "hard"]
        self.assertEqual([c["text"] for c in hard], ["uh"])

    def test_soft_candidates_say_the_default_is_to_keep(self):
        words = seq([("Basically", 0.3), ("yes.", 0.3)])
        result, _ = run(words)
        soft = [c for c in by_type(result, "filler") if c["cls"] == "soft"][0]
        self.assertIn("KEEP", soft["reason"])


class TestVoiceBible(unittest.TestCase):
    """Per-creator cadence lives in the creator's file, not in this script."""

    def _bible(self, tmp, body):
        p = Path(tmp) / "voice-bible.md"
        p.write_text(body)
        return p

    def test_cut_list_adds_a_soft_filler(self):
        with tempfile.TemporaryDirectory() as tmp:
            bible = self._bible(tmp, "# Voice\n\n```cadence\ncut: honestly\n```\n")
            words = seq([("Honestly", 0.3), ("yes.", 0.3)])
            result, _ = run(words, extra=["--voice-bible", str(bible)])
            soft = [c for c in by_type(result, "filler")
                    if c["cls"] == "soft"]
            self.assertEqual([c["text"] for c in soft], ["Honestly"])
            self.assertTrue(result["voice_bible_applied"])

    def test_keep_list_protects_a_default_soft_filler(self):
        with tempfile.TemporaryDirectory() as tmp:
            bible = self._bible(tmp, "```cadence\nkeep: basically\n```\n")
            words = seq([("Basically", 0.3), ("yes.", 0.3)])
            result, _ = run(words, extra=["--voice-bible", str(bible)])
            self.assertEqual([c for c in by_type(result, "filler")
                              if c["cls"] == "soft"], [])

    def test_keep_list_protects_even_a_hard_filler(self):
        with tempfile.TemporaryDirectory() as tmp:
            bible = self._bible(tmp, "```cadence\nkeep: hmm\n```\n")
            words = seq([("Hmm", 0.3), ("yes.", 0.3)])
            result, _ = run(words, extra=["--voice-bible", str(bible)])
            self.assertEqual(by_type(result, "filler"), [])

    def test_keep_wins_over_cut_on_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            bible = self._bible(
                tmp, "```cadence\nkeep: honestly\ncut: honestly\n```\n")
            words = seq([("Honestly", 0.3), ("yes.", 0.3)])
            result, _ = run(words, extra=["--voice-bible", str(bible)])
            self.assertEqual([c for c in by_type(result, "filler")
                              if c["cls"] == "soft"], [])

    def test_multi_word_cut_phrase(self):
        with tempfile.TemporaryDirectory() as tmp:
            bible = self._bible(tmp, "```cadence\ncut: kind of\n```\n")
            words = seq([("Kind", 0.3), ("of", 0.3), ("yes.", 0.3)])
            result, _ = run(words, extra=["--voice-bible", str(bible)])
            soft = [c for c in by_type(result, "filler")
                    if c["cls"] == "soft"]
            self.assertEqual([c["text"] for c in soft], ["Kind of"])

    def test_bible_without_a_cadence_block_warns_and_uses_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            bible = self._bible(tmp, "# Voice\n\nNo machine-readable block.\n")
            words = seq([("Basically", 0.3), ("yes.", 0.3)])
            result, r = run(words, extra=["--voice-bible", str(bible)])
            self.assertIn("no ```cadence block", r.stderr)
            self.assertFalse(result["voice_bible_applied"])
            self.assertEqual(len([c for c in by_type(result, "filler")
                                  if c["cls"] == "soft"]), 1)

    def test_missing_bible_fails_loudly(self):
        _, r = run(seq([("hi.", 0.3)]), expect=1,
                   extra=["--voice-bible", "/nope/voice-bible.md"])
        self.assertIn("cannot read voice bible", r.stderr)

    def test_parser_ignores_non_cadence_fences(self):
        keep, cut = cutplan_parse("```python\nkeep: so\n```\n")
        self.assertEqual((keep, cut), (set(), set()))

    def test_parser_reads_a_cadence_fence(self):
        keep, cut = cutplan_parse(
            "```cadence\nkeep: so, here's the thing\ncut: um\n```\n")
        self.assertEqual(keep, {"so", "here's the thing"})
        self.assertEqual(cut, {"um"})


class TestStutter(unittest.TestCase):
    def test_immediate_repeat(self):
        words = seq([("the", 0.3), ("the", 0.3), ("cat.", 0.3)])
        result, _ = run(words)
        st = by_type(result, "stutter")
        self.assertEqual(len(st), 1)
        self.assertEqual(st[0]["start"], words[0]["start"])
        self.assertEqual(st[0]["end"], words[0]["end"])  # first occurrence

    def test_punctuation_normalized(self):
        words = seq([("you.", 0.3), ("You", 0.3), ("win.", 0.3)])
        result, _ = run(words)
        self.assertEqual(len(by_type(result, "stutter")), 1)


class TestRetake(unittest.TestCase):
    def test_spoken_cue_take_n(self):
        words = seq([("hi.", 0.3), ("Take", 0.3), ("three,", 0.3), ("go.", 0.3)])
        result, _ = run(words)
        rt = by_type(result, "retake")
        self.assertEqual(len(rt), 1)
        self.assertIn("take three", rt[0]["reason"])

    def test_spoken_cue_phrase(self):
        words = seq([("try", 0.3), ("that", 0.3), ("again.", 0.3)])
        result, _ = run(words)
        self.assertEqual(len(by_type(result, "retake")), 1)

    def test_take_not_followed_by_number(self):
        words = seq([("take", 0.3), ("your", 0.3), ("time.", 0.3)])
        result, _ = run(words)
        self.assertEqual(by_type(result, "retake"), [])

    def test_verbatim_repeat_picks_earlier(self):
        words = seq([("get", 0.3), ("rid", 0.3), ("of", 0.3), ("it.", 0.3),
                     ("get", 0.3), ("rid", 0.3), ("of", 0.3), ("that.", 0.3)])
        result, _ = run(words)
        rt = by_type(result, "retake")
        self.assertEqual(len(rt), 1)
        self.assertEqual(rt[0]["start"], words[0]["start"])  # earlier occurrence
        self.assertEqual(rt[0]["end"], words[2]["end"])

    def test_short_repeat_below_run_ignored(self):
        words = seq([("go", 0.3), ("now.", 0.3), ("go", 0.3), ("now.", 0.3)])
        result, _ = run(words)
        # only a 2-word repeat, below retake-run 3
        self.assertEqual(by_type(result, "retake"), [])


class TestMarker(unittest.TestCase):
    def test_marker_phrase_spans_words(self):
        words = seq([("hi.", 0.3), ("question", 0.3), ("from", 0.3),
                     ("the", 0.3), ("interviewer", 0.3), ("next.", 0.3)])
        result, _ = run(words)
        mk = by_type(result, "marker")
        self.assertEqual(len(mk), 1)
        self.assertEqual(mk[0]["start"], words[1]["start"])
        self.assertEqual(mk[0]["end"], words[4]["end"])
        self.assertEqual(mk[0]["severity"], "med")

    def test_default_has_no_marker(self):
        words = seq([("just", 0.3), ("talking.", 0.3)])
        result, _ = run(words)
        self.assertEqual(by_type(result, "marker"), [])

    def test_legacy_phrase_not_matched_by_default(self):
        words = seq([("question", 0.3), ("from", 0.3), ("claude", 0.3)])
        result, _ = run(words)
        self.assertEqual(by_type(result, "marker"), [])

    def test_legacy_phrase_works_via_flag(self):
        words = seq([("question", 0.3), ("from", 0.3), ("claude", 0.3)])
        result, _ = run(words, extra=["--marker-cues", "question from claude"])
        self.assertEqual(len(by_type(result, "marker")), 1)

    def test_custom_marker_cues(self):
        words = seq([("ask", 0.3), ("the", 0.3), ("panel.", 0.3)])
        result, _ = run(words, extra=["--marker-cues", "ask the panel"])
        self.assertEqual(len(by_type(result, "marker")), 1)


class TestSchema(unittest.TestCase):
    def test_cls_only_on_fillers(self):
        words = seq([("So", 0.3), ("uh", 0.3), ("the", 0.3), ("the", 0.3)])
        result, _ = run(words)
        for c in result["candidates"]:
            if c["type"] == "filler":
                self.assertIn("cls", c)
            else:
                self.assertNotIn("cls", c)

    def test_sorted_by_start(self):
        words = seq([("So", 0.3), ("uh", 0.3, 1.0), ("the", 0.3), ("the", 0.3)])
        result, _ = run(words)
        starts = [c["start"] for c in result["candidates"]]
        self.assertEqual(starts, sorted(starts))

    def test_counts_has_all_types(self):
        result, _ = run(seq([("hi.", 0.3)]))
        self.assertEqual(set(result["counts"]),
                         {"silence", "filler", "stutter", "retake", "blooper",
                          "marker"})

    def test_thresholds_reflect_flags(self):
        result, _ = run(seq([("hi.", 0.3)]),
                        extra=["--min-silence", "1.5", "--retake-run", "4",
                               "--retake-window", "20"])
        self.assertEqual(result["thresholds"],
                         {"min_silence": 1.5, "retake_window": 20,
                          "retake_run": 4, "snap_ms": 250, "keep_ms": 200,
                          "section_run": 8, "section_window_s": 45.0})


class TestSectionRedo(unittest.TestCase):
    """A whole re-read section, not just the repeated words.

    The short-range matcher looks 16 WORDS ahead for a 3-word repeat, which
    undersized a real section redo from about 34s to about 11s and left the
    abandoned take in the video."""

    def _para(self, prefix, start, word_dur=0.3, n=10):
        return [(f"{prefix}{i}" if i else "memory", word_dur)
                for i in range(n)]

    def _redo_words(self, restart_gap):
        # Ten words, a pause, then the same ten words again.
        text = ["memory", "systems", "are", "still", "the", "hard", "part",
                "of", "this", "work"]
        pairs = [(w, 0.3) for w in text]
        pairs += [(text[0], 0.3, restart_gap)]
        pairs += [(w, 0.3) for w in text[1:]]
        return seq(pairs)

    def test_full_abandoned_span_is_the_candidate(self):
        words = self._redo_words(2.0)
        result, _ = run(words, duration=round(words[-1]["end"] + 0.5, 2))
        sec = [c for c in by_type(result, "retake")
               if c.get("cls") == "section"]
        self.assertEqual(len(sec), 1)
        # From the first attempt's start to the restart's start, so the
        # abandoned take AND the reset pause both go.
        self.assertAlmostEqual(sec[0]["start"], words[0]["start"], places=1)
        self.assertAlmostEqual(sec[0]["end"], words[10]["start"], places=1)

    def test_span_includes_the_reset_pause(self):
        words = self._redo_words(2.0)
        result, _ = run(words, duration=round(words[-1]["end"] + 0.5, 2))
        sec = [c for c in by_type(result, "retake")
               if c.get("cls") == "section"][0]
        # 10 words x 0.3s of abandoned take plus the 2.0s reset.
        self.assertGreater(sec["dur"], 4.5)

    def test_distant_repeat_is_a_callback_not_a_redo(self):
        # The same ten words 90s later is a deliberate callback. The locality
        # window is what tells them apart, and it must be in SECONDS.
        words = self._redo_words(90.0)
        result, _ = run(words, duration=round(words[-1]["end"] + 0.5, 2))
        self.assertEqual([c for c in by_type(result, "retake")
                          if c.get("cls") == "section"], [])

    def test_section_window_is_configurable(self):
        words = self._redo_words(90.0)
        dur = round(words[-1]["end"] + 0.5, 2)
        wide, _ = run(words, duration=dur,
                      extra=["--section-window-s", "200"])
        self.assertEqual(len([c for c in by_type(wide, "retake")
                              if c.get("cls") == "section"]), 1)

    def test_short_repeat_does_not_trip_the_section_matcher(self):
        words = seq([("the", 0.3), ("cat", 0.3), ("sat", 0.3),
                     ("the", 0.3, 1.0), ("cat", 0.3), ("sat", 0.3)])
        result, _ = run(words, duration=round(words[-1]["end"] + 0.5, 2))
        self.assertEqual([c for c in by_type(result, "retake")
                          if c.get("cls") == "section"], [])

    def test_section_run_is_configurable(self):
        words = seq([("the", 0.3), ("cat", 0.3), ("sat", 0.3),
                     ("the", 0.3, 1.0), ("cat", 0.3), ("sat", 0.3)])
        dur = round(words[-1]["end"] + 0.5, 2)
        result, _ = run(words, duration=dur, extra=["--section-run", "3"])
        self.assertEqual(len([c for c in by_type(result, "retake")
                              if c.get("cls") == "section"]), 1)


class TestBlooper(unittest.TestCase):
    """The "Oh fuck." at 13:59 that the mechanical pass left in, and would
    have shipped."""

    def test_expletive_next_to_a_pause_is_a_high_severity_blooper(self):
        words = seq([("Oh", 0.3), ("fuck.", 0.3), ("Let", 0.3, 2.0),
                     ("me", 0.3), ("go.", 0.3)])
        silence = [{"start": 0.6, "end": 2.6, "dur": 2.0}]
        result, _ = run(words, duration=round(words[-1]["end"] + 0.5, 2),
                        silence=silence)
        bl = by_type(result, "blooper")
        self.assertEqual([c["text"] for c in bl], ["fuck."])
        self.assertEqual(bl[0]["severity"], "high")
        self.assertEqual(bl[0]["cls"], "reset")

    def test_expletive_in_continuous_speech_is_flagged_for_an_ear(self):
        # "that damn term" is scripted usage, not a flub.
        words = seq([("that", 0.3), ("damn", 0.3), ("term", 0.3),
                     ("again.", 0.3)])
        result, _ = run(words, duration=round(words[-1]["end"] + 0.1, 2),
                        silence=[])
        bl = by_type(result, "blooper")
        self.assertEqual(len(bl), 1)
        self.assertEqual(bl[0]["severity"], "med")
        self.assertEqual(bl[0]["cls"], "ambiguous")
        self.assertIn("confirm by ear", bl[0]["reason"])

    def test_reset_phrase_is_a_blooper(self):
        words = seq([("Scratch", 0.3), ("that.", 0.3), ("Again.", 0.3)])
        result, _ = run(words, duration=round(words[-1]["end"] + 0.1, 2),
                        silence=[])
        self.assertEqual([c["text"] for c in by_type(result, "blooper")],
                         ["Scratch that."])

    def test_clean_speech_has_no_bloopers(self):
        words = seq([("This", 0.3), ("is", 0.3), ("fine.", 0.3)])
        result, _ = run(words)
        self.assertEqual(by_type(result, "blooper"), [])

    def test_blooper_vocabulary_is_overridable(self):
        words = seq([("That", 0.3), ("blast.", 0.3)])
        dur = round(words[-1]["end"] + 0.1, 2)
        default, _ = run(words, duration=dur, silence=[])
        custom, _ = run(words, duration=dur, silence=[],
                        extra=["--blooper-cues", "blast"])
        self.assertEqual(by_type(default, "blooper"), [])
        self.assertEqual([c["text"] for c in by_type(custom, "blooper")],
                         ["blast."])

    def test_silence_source_is_recorded_as_audio(self):
        result, _ = run(seq([("hi.", 0.3)]))
        self.assertEqual(result["silence_source"], "audio")


class TestAudioMapIsMandatory(unittest.TestCase):
    """The no-silent-fallback guarantee. Silence must come from the audio;
    a missing or malformed map has to stop the stage, never quietly degrade
    back to transcript gaps (the 2026-07-24 defect)."""

    def _amap(self, tmp, payload):
        p = Path(tmp) / "audio-map.json"
        p.write_text(json.dumps(payload))
        return p

    def test_omitting_the_audio_map_is_a_usage_error(self):
        _, r = run(seq([("hi.", 0.3)]), expect=2, with_audio_map=False)
        self.assertIn("--audio-map", r.stderr)

    def test_unreadable_audio_map_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "words.json"
            src.write_text(json.dumps({"media": "m.mp4", "duration": 1.0,
                                       "text": "", "words": []}))
            r = subprocess.run(
                [sys.executable, str(SCRIPT), str(src), "-o",
                 str(Path(tmp) / "out.json"), "--audio-map",
                 str(Path(tmp) / "nope.json")],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("analyze_audio.py", r.stderr)

    def test_audio_map_without_silence_key_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "words.json"
            src.write_text(json.dumps({"media": "m.mp4", "duration": 1.0,
                                       "text": "", "words": []}))
            amap = self._amap(tmp, {"duration": 1.0})
            r = subprocess.run(
                [sys.executable, str(SCRIPT), str(src), "-o",
                 str(Path(tmp) / "out.json"), "--audio-map", str(amap)],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("silence", r.stderr)


class TestSilenceComesFromAudioNotGaps(unittest.TestCase):
    """The core regression. Transcript timestamps absorb pauses, so the same
    words must yield silence candidates driven by the AUDIO map, whatever the
    word timestamps happen to say."""

    def test_pause_absorbed_word_end_still_yields_a_silence_candidate(self):
        # The real shape of the bug: "about." is timestamped 32.16 -> 34.64,
        # a 2.5s "word" that swallowed the pause after it. The gap to the
        # next word reads 0.0, but the audio is silent from 32.4 to 34.6.
        words = [word("about.", 32.16, 34.64, 0),
                 word("One", 34.64, 34.9, 1)]
        silence = [{"start": 32.4, "end": 34.6, "dur": 2.2}]
        result, _ = run(words, duration=35.0, silence=silence)
        sil = by_type(result, "silence")
        self.assertEqual(len(sil), 1)
        # The full silence is 32.4 to 34.6; the candidate is the part to
        # REMOVE, tightened to 200ms of breathing room split evenly.
        self.assertEqual(sil[0]["silence_start"], 32.4)
        self.assertEqual(sil[0]["silence_end"], 34.6)
        self.assertAlmostEqual(sil[0]["start"], 32.5, places=2)
        self.assertAlmostEqual(sil[0]["end"], 34.5, places=2)
        self.assertEqual(sil[0]["severity"], "high")
        # The transcript said the gap here was 0.0 (34.64 - 34.64). The
        # audio said 2.2s. The audio wins, which is the whole fix.
        self.assertEqual(words[1]["start"] - words[0]["end"], 0.0)

    def test_zero_gap_words_over_silent_audio_are_still_found(self):
        # Words laid end to end (every transcript gap 0.0) over audio that is
        # actually silent in the middle. The old gap detector found nothing.
        words = seq([("a", 0.3), ("b", 0.3), ("c", 0.3)])
        silence = [{"start": 0.3, "end": 0.6, "dur": 0.3},
                   {"start": 0.6, "end": 2.4, "dur": 1.8}]
        result, _ = run(words, duration=3.0, silence=silence)
        self.assertGreaterEqual(len(by_type(result, "silence")), 1)

    def test_no_audio_silence_means_no_silence_candidates(self):
        words = seq([("a", 0.3), ("b", 0.3, 5.0)])
        result, _ = run(words, duration=10.0, silence=[])
        self.assertEqual(by_type(result, "silence"), [])


class TestEdgeSnapping(unittest.TestCase):
    """Candidate edges move into audio-verified silence, which is what makes
    'never cut inside a word' structural rather than aspirational."""

    def test_edges_snap_into_neighbouring_silence(self):
        # A hard filler whose transcript end overruns into the next word by
        # 60ms; real silence sits at 1.0 to 1.5.
        words = [word("uh", 0.5, 1.06, 0), word("okay.", 1.5, 1.9, 1)]
        silence = [{"start": 0.0, "end": 0.5, "dur": 0.5},
                   {"start": 1.0, "end": 1.5, "dur": 0.5}]
        result, _ = run(words, duration=2.5, silence=silence)
        fil = by_type(result, "filler")[0]
        self.assertTrue(fil["snapped"])
        self.assertGreaterEqual(fil["end"], 1.0)
        self.assertLessEqual(fil["end"], 1.5)

    def test_unsnappable_edges_are_flagged_not_faked(self):
        # No silence anywhere near the candidate: the edge stays put and the
        # candidate is marked so the gate knows it carries timestamp risk.
        words = [word("uh", 5.0, 5.4, 0), word("okay.", 5.4, 5.8, 1)]
        result, _ = run(words, duration=6.0, silence=[])
        fil = by_type(result, "filler")[0]
        self.assertFalse(fil["snapped"])
        self.assertEqual(fil["start"], 5.0)
        self.assertEqual(result["unsnapped"], len(
            [c for c in result["candidates"] if not c["snapped"]]))

    def test_unsnapped_count_is_reported_on_stderr(self):
        words = [word("uh", 5.0, 5.4, 0), word("okay.", 5.4, 5.8, 1)]
        _, r = run(words, duration=6.0, silence=[])
        self.assertIn("could not reach an audio silence", r.stderr)

    def test_stutter_edge_lands_in_the_silence_between_takes(self):
        # The "n-now" artifact: the first "now" is timestamped through the
        # pause (0.5 -> 1.15) so cutting to its end clipped the repeat's
        # onset at 1.2. Snapping puts the edge inside the 1.0 to 1.2 silence.
        words = [word("now,", 0.5, 1.15, 0), word("now", 1.2, 1.5, 1)]
        silence = [{"start": 0.0, "end": 0.5, "dur": 0.5},
                   {"start": 1.0, "end": 1.2, "dur": 0.2}]
        result, _ = run(words, duration=2.0, silence=silence)
        stut = by_type(result, "stutter")[0]
        self.assertTrue(stut["snapped"])
        self.assertLessEqual(stut["end"], 1.2)
        self.assertGreaterEqual(stut["end"], 1.0)

    def test_silence_candidates_are_never_moved(self):
        words = seq([("a", 0.3), ("b", 0.3, 1.0)])
        result, _ = run(words)
        for c in by_type(result, "silence"):
            self.assertTrue(c["snapped"])

    def test_snap_budget_is_configurable(self):
        # Start sits on the edge of the leading silence (always snappable);
        # the end is 0.6s from the next silence, so only the loose budget
        # reaches it. Both edges must snap for the candidate to count.
        words = [word("uh", 0.5, 0.9, 0), word("okay.", 2.0, 2.4, 1)]
        silence = [{"start": 0.0, "end": 0.5, "dur": 0.5},
                   {"start": 1.5, "end": 2.0, "dur": 0.5}]
        tight, _ = run(words, duration=3.0, silence=silence,
                       extra=["--snap-ms", "50"])
        loose, _ = run(words, duration=3.0, silence=silence,
                       extra=["--snap-ms", "800"])
        self.assertFalse(by_type(tight, "filler")[0]["snapped"])
        self.assertTrue(by_type(loose, "filler")[0]["snapped"])
        self.assertEqual(by_type(loose, "filler")[0]["end"], 1.5)


class TestExitCodes(unittest.TestCase):
    def test_missing_input_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            amap = Path(tmp) / "audio-map.json"
            amap.write_text(json.dumps({"duration": 1.0, "silence": []}))
            r = subprocess.run([sys.executable, str(SCRIPT),
                                str(Path(tmp) / "nope.json"), "-o",
                                str(Path(tmp) / "out.json"),
                                "--audio-map", str(amap)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)

    def test_usage_error(self):
        r = subprocess.run([sys.executable, str(SCRIPT)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_bad_json_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "bad.json"
            src.write_text("{not json")
            amap = Path(tmp) / "audio-map.json"
            amap.write_text(json.dumps({"duration": 1.0, "silence": []}))
            r = subprocess.run([sys.executable, str(SCRIPT), str(src), "-o",
                                str(Path(tmp) / "out.json"),
                                "--audio-map", str(amap)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)


class TestProtectedFlags(unittest.TestCase):
    """cutplan_flags is appended AFTER the skill's own arguments, and argparse
    lets the later one win. Without this, an override file could point
    --audio-map elsewhere and break the two-source rule with no visible sign."""

    def test_a_single_occurrence_is_fine(self):
        self.assertEqual(cutplan.protected_conflicts(
            ["w.json", "-o", "out.json", "--audio-map", "a.json"]), [])

    def test_a_duplicated_audio_map_is_a_conflict(self):
        self.assertEqual(cutplan.protected_conflicts(
            ["--audio-map", "a.json", "--audio-map", "evil.json"]),
            ["--audio-map"])

    def test_a_duplicated_output_is_a_conflict(self):
        self.assertEqual(cutplan.protected_conflicts(
            ["-o", "out.json", "-o", "elsewhere.json"]), ["-o"])

    def test_the_two_spellings_of_output_collide(self):
        self.assertEqual(cutplan.protected_conflicts(
            ["-o", "out.json", "--output", "elsewhere.json"]),
            ["--output", "-o"])

    def test_equals_form_is_caught(self):
        self.assertEqual(cutplan.protected_conflicts(
            ["--audio-map", "a.json", "--audio-map=evil.json"]),
            ["--audio-map"])

    def test_a_duplicated_voice_bible_is_a_conflict(self):
        self.assertEqual(cutplan.protected_conflicts(
            ["--voice-bible", "v.md", "--voice-bible", "other.md"]),
            ["--voice-bible"])

    def test_unprotected_flags_may_repeat(self):
        self.assertEqual(cutplan.protected_conflicts(
            ["--min-silence", "0.3", "--min-silence", "0.5"]), [])

    def test_the_cli_refuses_a_redirected_audio_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            words = Path(tmp) / "w.json"
            words.write_text(json.dumps({"words": []}))
            amap = Path(tmp) / "audio-map.json"
            amap.write_text(json.dumps({"duration": 1.0, "silence": []}))
            r = subprocess.run(
                [sys.executable, str(SCRIPT), str(words),
                 "-o", str(Path(tmp) / "out.json"),
                 "--audio-map", str(amap),
                 "--audio-map", str(Path(tmp) / "evil.json")],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)
            self.assertIn("two-source rule", r.stderr)


if __name__ == "__main__":
    unittest.main()
