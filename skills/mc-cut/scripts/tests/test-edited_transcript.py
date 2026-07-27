#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Tests for edited_transcript.py: the reconstruction the content-editorial
pass reads, and its dual timecodes."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "edited_transcript.py"
spec = importlib.util.spec_from_file_location("edited_transcript", SCRIPT)
et = importlib.util.module_from_spec(spec)
spec.loader.exec_module(et)


def words(spans):
    return [{"word": t, "start": s, "end": e, "confidence": 1.0, "i": i,
             "gap_before": 0.0, "gap_after": 0.0}
            for i, (t, s, e) in enumerate(spans)]


# Keeps source 0-10 and 20-30; 10-20 is cut away.
EDL = {"source": "raw/cam.mp4", "segments": [
    {"source": "raw/cam.mp4", "start": 0.0, "end": 10.0},
    {"source": "raw/cam.mp4", "start": 20.0, "end": 30.0},
]}
MAPPING = et.build_map(EDL)


class TestBuildMap(unittest.TestCase):
    def test_offsets_accumulate(self):
        self.assertEqual([s["offset"] for s in MAPPING], [0.0, 10.0])

    def test_clean_duration_is_the_kept_total(self):
        self.assertEqual(et.clean_duration(MAPPING), 20.0)


class TestKeepWords(unittest.TestCase):
    def test_word_in_a_kept_span_survives(self):
        kept = et.keep_words(words([("hello", 1.0, 1.5)]), MAPPING)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["clean_start"], 1.0)
        self.assertEqual(kept[0]["src_start"], 1.0)

    def test_word_in_a_removed_span_is_dropped(self):
        self.assertEqual(et.keep_words(words([("gone", 14.0, 14.5)]),
                                       MAPPING), [])

    def test_clean_time_is_shifted_for_later_segments(self):
        # Source 25.0 sits 5s into the second kept span, which starts at 10.
        kept = et.keep_words(words([("later", 25.0, 25.5)]), MAPPING)
        self.assertEqual(kept[0]["clean_start"], 15.0)
        self.assertEqual(kept[0]["src_start"], 25.0)

    def test_both_timecodes_are_always_present(self):
        kept = et.keep_words(words([("a", 1.0, 1.5), ("b", 25.0, 25.5)]),
                             MAPPING)
        for w in kept:
            for field in ("clean_start", "clean_end", "src_start", "src_end"):
                self.assertIn(field, w)

    def test_word_straddling_a_boundary_is_kept_once(self):
        # Midpoint 9.75 is inside the first kept span.
        kept = et.keep_words(words([("edge", 9.5, 10.0)]), MAPPING)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["segment"], 0)

    def test_word_mostly_outside_is_dropped(self):
        # Midpoint 10.5 falls in the removed span.
        self.assertEqual(et.keep_words(words([("edge", 9.8, 11.2)]),
                                       MAPPING), [])

    def test_no_word_is_emitted_twice(self):
        kept = et.keep_words(words([("a", 9.9, 10.1)]), MAPPING)
        self.assertLessEqual(len(kept), 1)

    def test_clean_times_stay_inside_the_timeline(self):
        kept = et.keep_words(words([("edge", 9.5, 10.4)]), MAPPING)
        total = et.clean_duration(MAPPING)
        for w in kept:
            self.assertGreaterEqual(w["clean_start"], 0.0)
            self.assertLessEqual(w["clean_end"], total + 1e-6)

    def test_reading_order_is_preserved(self):
        kept = et.keep_words(words([
            ("one", 1.0, 1.4), ("cut", 15.0, 15.4), ("two", 25.0, 25.4)]),
            MAPPING)
        self.assertEqual([w["word"] for w in kept], ["one", "two"])

    def test_source_filter_selects_one_source(self):
        edl = {"segments": [
            {"source": "a.mp4", "start": 0.0, "end": 10.0},
            {"source": "b.mp4", "start": 0.0, "end": 10.0}]}
        m = et.build_map(edl)
        kept = et.keep_words(words([("x", 1.0, 1.4)]), m, source="b.mp4")
        self.assertEqual(kept[0]["segment"], 1)


class TestParagraphs(unittest.TestCase):
    def test_pause_opens_a_new_paragraph(self):
        kept = et.keep_words(words([
            ("a", 1.0, 1.4), ("b", 1.4, 1.8), ("c", 4.0, 4.4)]), MAPPING)
        self.assertEqual(len(et.paragraphs(kept)), 2)

    def test_continuous_speech_is_one_paragraph(self):
        kept = et.keep_words(words([
            ("a", 1.0, 1.4), ("b", 1.4, 1.8), ("c", 1.8, 2.2)]), MAPPING)
        self.assertEqual(len(et.paragraphs(kept)), 1)

    def test_segment_change_opens_a_new_paragraph(self):
        # A seam is exactly where the pass needs to check the join reads,
        # so it must not be buried mid-paragraph.
        kept = et.keep_words(words([("a", 9.0, 9.4), ("b", 20.0, 20.4)]),
                             MAPPING)
        self.assertEqual(len(et.paragraphs(kept)), 2)

    def test_empty_input_is_no_paragraphs(self):
        self.assertEqual(et.paragraphs([]), [])


class TestRenderMarkdown(unittest.TestCase):
    def test_output_carries_both_timecodes(self):
        kept = et.keep_words(words([("later", 25.0, 25.5)]), MAPPING)
        md = et.render_markdown(kept, MAPPING)
        self.assertIn("0:15.00", md)      # clean
        self.assertIn("src 0:25.00", md)  # source

    def test_output_states_the_runtime(self):
        kept = et.keep_words(words([("a", 1.0, 1.4)]), MAPPING)
        self.assertIn("0:20.00", et.render_markdown(kept, MAPPING))

    def test_output_warns_against_hand_conversion(self):
        kept = et.keep_words(words([("a", 1.0, 1.4)]), MAPPING)
        self.assertIn("Never convert between them by hand",
                      et.render_markdown(kept, MAPPING))

    def test_words_appear_in_order(self):
        kept = et.keep_words(words([
            ("one", 1.0, 1.4), ("two", 1.4, 1.8)]), MAPPING)
        md = et.render_markdown(kept, MAPPING)
        self.assertLess(md.index("one"), md.index("two"))


class TestCli(unittest.TestCase):
    def _run(self, word_spans, extra=None):
        tmp = tempfile.TemporaryDirectory()
        d = Path(tmp.name)
        (d / "words.json").write_text(json.dumps(
            {"duration": 30.0, "words": words(word_spans)}))
        (d / "edl.json").write_text(json.dumps(EDL))
        r = subprocess.run(
            [sys.executable, str(SCRIPT), str(d / "words.json"),
             "--edl", str(d / "edl.json"), "-o", str(d / "edited.md"),
             "-j", str(d / "edited.json"), *(extra or [])],
            capture_output=True, text=True)
        return r, d, tmp

    def test_writes_both_outputs(self):
        r, d, tmp = self._run([("a", 1.0, 1.4), ("b", 25.0, 25.4)])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((d / "edited.md").is_file())
        self.assertTrue((d / "edited.json").is_file())
        tmp.cleanup()

    def test_summary_counts_kept_and_dropped(self):
        r, _, tmp = self._run([("a", 1.0, 1.4), ("gone", 15.0, 15.4)])
        summary = json.loads(r.stdout)
        self.assertEqual(summary["words_kept"], 1)
        self.assertEqual(summary["words_dropped"], 1)
        tmp.cleanup()

    def test_json_output_carries_dual_timecodes(self):
        r, d, tmp = self._run([("b", 25.0, 25.4)])
        data = json.loads((d / "edited.json").read_text())
        w = data["words"][0]
        self.assertEqual(w["clean_start"], 15.0)
        self.assertEqual(w["src_start"], 25.0)
        self.assertEqual(data["clean_duration"], 20.0)
        tmp.cleanup()

    def test_missing_input_is_a_usage_error(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "/nope/words.json",
             "--edl", "/nope/edl.json", "-o", "/tmp/out.md"],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_help_exits_zero(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("--edl", r.stdout)


if __name__ == "__main__":
    unittest.main()
