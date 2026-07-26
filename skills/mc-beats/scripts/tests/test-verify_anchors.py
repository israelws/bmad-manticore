#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Tests for verify_anchors.py: a beat whose time was estimated rather than
derived from its anchor word must fail the gate."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "verify_anchors.py"
spec = importlib.util.spec_from_file_location("verify_anchors", SCRIPT)
va = importlib.util.module_from_spec(spec)
spec.loader.exec_module(va)


def words(pairs):
    """Word dicts from (text, start) pairs, each 0.4s long."""
    return [{"word": t, "start": s, "end": round(s + 0.4, 2),
             "confidence": 1.0, "i": i, "gap_before": 0.0, "gap_after": 0.0}
            for i, (t, s) in enumerate(pairs)]


EDL = {"source": "raw/cam.mp4", "segments": [
    # Keeps 0-10 and 20-30 of the source; 10-20 is cut away.
    {"source": "raw/cam.mp4", "start": 0.0, "end": 10.0},
    {"source": "raw/cam.mp4", "start": 20.0, "end": 30.0},
]}
MAPPING = va.build_map(EDL)


def table(rows, header="| id | start | dur | end | anchor word | anchor ts | "
                      "spoken phrase | type |"):
    sep = "|" + "|".join(["---"] * (header.count("|") - 1)) + "|"
    return "\n".join([header, sep, *rows]) + "\n"


class TestBuildMap(unittest.TestCase):
    def test_offsets_accumulate_kept_durations(self):
        self.assertEqual([s["offset"] for s in MAPPING], [0.0, 10.0])

    def test_empty_edl_is_an_empty_map(self):
        self.assertEqual(va.build_map({"segments": []}), [])


class TestOrigToClean(unittest.TestCase):
    def test_time_in_the_first_segment(self):
        self.assertAlmostEqual(va.orig_to_clean(MAPPING, 4.0), 4.0)

    def test_time_in_a_later_segment_is_shifted(self):
        # Source 25.0 sits 5s into the second kept span, which starts at 10.
        self.assertAlmostEqual(va.orig_to_clean(MAPPING, 25.0), 15.0)

    def test_time_in_a_removed_span_is_none(self):
        # Deliberately does NOT snap: "this anchor was cut away" is the
        # answer the gate needs, not a nearby guess.
        self.assertIsNone(va.orig_to_clean(MAPPING, 15.0))

    def test_segment_boundaries_are_inclusive(self):
        self.assertIsNotNone(va.orig_to_clean(MAPPING, 0.0))
        self.assertIsNotNone(va.orig_to_clean(MAPPING, 10.0))

    def test_source_filter_is_honoured(self):
        self.assertIsNone(va.orig_to_clean(MAPPING, 4.0, source="raw/b.mp4"))


class TestParseBeats(unittest.TestCase):
    def test_reads_id_start_and_anchor_columns(self):
        rows, skipped = va.parse_beats(table([
            "| b01 | 4.0 | 2.0 | 6.0 | markdown | 4.0 | the markdown is | "
            "diagram |"]))
        self.assertEqual(skipped, [])
        self.assertEqual(rows[0]["id"], "b01")
        self.assertEqual(rows[0]["start"], 4.0)
        self.assertEqual(rows[0]["anchor_word"], "markdown")
        self.assertEqual(rows[0]["anchor_ts"], 4.0)

    def test_column_order_does_not_matter(self):
        rows, _ = va.parse_beats(table(
            ["| 4.0 | b01 | markdown |"],
            header="| start | id | anchor word |"))
        self.assertEqual(rows[0]["id"], "b01")
        self.assertEqual(rows[0]["anchor_word"], "markdown")

    def test_missing_anchor_column_parses_as_empty(self):
        rows, _ = va.parse_beats(table(["| b01 | 4.0 |"],
                                       header="| id | start |"))
        self.assertEqual(rows[0]["anchor_word"], "")

    def test_separator_row_is_not_a_beat(self):
        rows, _ = va.parse_beats(table([
            "| b01 | 4.0 | 2.0 | 6.0 | markdown | 4.0 | x | diagram |"]))
        self.assertEqual(len(rows), 1)

    def test_non_numeric_start_is_skipped_loudly(self):
        rows, skipped = va.parse_beats(table([
            "| b01 | soon | 2.0 | 6.0 | markdown | 4.0 | x | diagram |"]))
        self.assertEqual(rows, [])
        self.assertEqual(len(skipped), 1)

    def test_null_anchor_ts_reads_as_absent(self):
        rows, _ = va.parse_beats(table([
            "| b01 | 4.0 | 2.0 | 6.0 | markdown | null | x | diagram |"]))
        self.assertIsNone(rows[0]["anchor_ts"])


class TestFindAnchorOccurrences(unittest.TestCase):
    W = words([("The", 1.0), ("markdown", 2.0), ("is", 3.0),
               ("the", 4.0), ("markdown", 5.0)])

    def test_finds_every_occurrence(self):
        self.assertEqual(
            [w["start"] for w in va.find_anchor_occurrences(self.W, "markdown")],
            [2.0, 5.0])

    def test_match_is_case_and_punctuation_insensitive(self):
        w = words([("Markdown,", 2.0)])
        self.assertEqual(len(va.find_anchor_occurrences(w, "markdown")), 1)

    def test_multi_word_anchor_matches_a_run(self):
        found = va.find_anchor_occurrences(self.W, "markdown is")
        self.assertEqual([w["start"] for w in found], [2.0])

    def test_absent_word_finds_nothing(self):
        self.assertEqual(va.find_anchor_occurrences(self.W, "nonsense"), [])

    def test_empty_anchor_finds_nothing(self):
        self.assertEqual(va.find_anchor_occurrences(self.W, ""), [])


class TestVerifyBeat(unittest.TestCase):
    W = words([("The", 1.0), ("markdown", 4.0), ("is", 5.0),
               ("code", 25.0), ("cut", 15.0)])

    def beat(self, **kw):
        base = {"id": "b01", "start": 4.0, "anchor_word": "markdown",
                "anchor_ts": None, "phrase": ""}
        base.update(kw)
        return base

    def test_correctly_derived_beat_passes(self):
        r = va.verify_beat(self.beat(), self.W, MAPPING)
        self.assertEqual(r["status"], "ok")
        self.assertAlmostEqual(r["derived_clean"], 4.0)

    def test_beat_in_a_later_segment_uses_the_remapped_time(self):
        # "code" is at source 25.0, which is clean 15.0.
        r = va.verify_beat(self.beat(anchor_word="code", start=15.0),
                           self.W, MAPPING)
        self.assertEqual(r["status"], "ok")
        self.assertAlmostEqual(r["derived_clean"], 15.0)

    def test_estimated_beat_time_fails(self):
        # The B1 class: the time was guessed, not derived. Source 25.0 maps
        # to clean 15.0, but the planner wrote the SOURCE time into the table.
        r = va.verify_beat(self.beat(anchor_word="code", start=25.0),
                           self.W, MAPPING)
        self.assertEqual(r["status"], "violation")
        self.assertIn("remapping", r["reason"])

    def test_small_drift_inside_tolerance_passes(self):
        r = va.verify_beat(self.beat(start=4.3), self.W, MAPPING)
        self.assertEqual(r["status"], "ok")

    def test_drift_beyond_tolerance_fails(self):
        r = va.verify_beat(self.beat(start=5.2), self.W, MAPPING)
        self.assertEqual(r["status"], "violation")

    def test_tolerance_is_configurable(self):
        self.assertEqual(
            va.verify_beat(self.beat(start=5.2), self.W, MAPPING,
                           tolerance=2.0)["status"], "ok")

    def test_anchor_absent_from_the_transcript_fails(self):
        r = va.verify_beat(self.beat(anchor_word="unicorn"), self.W, MAPPING)
        self.assertEqual(r["status"], "violation")
        self.assertIn("does not appear", r["reason"])

    def test_anchor_in_a_removed_span_fails(self):
        # "cut" sits at source 15.0, inside the span the EDL removed.
        r = va.verify_beat(self.beat(anchor_word="cut", start=5.0),
                           self.W, MAPPING)
        self.assertEqual(r["status"], "violation")
        self.assertIn("never hears", r["reason"])

    def test_nearest_occurrence_is_used(self):
        w = words([("go", 1.0), ("go", 8.0)])
        r = va.verify_beat(self.beat(anchor_word="go", start=8.0), w, MAPPING)
        self.assertEqual(r["status"], "ok")
        self.assertAlmostEqual(r["derived_clean"], 8.0)
        self.assertEqual(r["occurrences"], 2)

    def test_no_anchor_word_is_unverifiable_not_a_failure(self):
        # PIPELINE.md's tolerance rule for legacy 0.x beat tables.
        r = va.verify_beat(self.beat(anchor_word=""), self.W, MAPPING)
        self.assertEqual(r["status"], "unverifiable")

    def test_anchor_ts_disagreeing_with_the_derived_time_fails(self):
        r = va.verify_beat(self.beat(anchor_ts=25.0), self.W, MAPPING)
        self.assertEqual(r["status"], "violation")
        self.assertIn("EDITED timeline", r["reason"])

    def test_anchor_ts_agreeing_passes(self):
        r = va.verify_beat(self.beat(anchor_ts=4.0), self.W, MAPPING)
        self.assertEqual(r["status"], "ok")

    def test_drift_sign_is_reported(self):
        r = va.verify_beat(self.beat(start=3.0), self.W, MAPPING)
        self.assertAlmostEqual(r["drift"], 1.0)


class TestBuildReport(unittest.TestCase):
    W = words([("The", 1.0), ("markdown", 4.0), ("code", 25.0)])

    def test_all_good_beats_report_ok(self):
        beats = [{"id": "b01", "start": 4.0, "anchor_word": "markdown",
                  "anchor_ts": None, "phrase": ""}]
        r = va.build_report(beats, self.W, MAPPING)
        self.assertTrue(r["ok"])
        self.assertEqual(r["checked"], 1)

    def test_one_bad_beat_fails_the_whole_report(self):
        beats = [{"id": "b01", "start": 4.0, "anchor_word": "markdown",
                  "anchor_ts": None, "phrase": ""},
                 {"id": "b02", "start": 25.0, "anchor_word": "code",
                  "anchor_ts": None, "phrase": ""}]
        r = va.build_report(beats, self.W, MAPPING)
        self.assertFalse(r["ok"])
        self.assertEqual([v["id"] for v in r["violations"]], ["b02"])

    def test_unverifiable_rows_do_not_fail_the_report(self):
        beats = [{"id": "b01", "start": 4.0, "anchor_word": "",
                  "anchor_ts": None, "phrase": ""}]
        r = va.build_report(beats, self.W, MAPPING)
        self.assertTrue(r["ok"])
        self.assertEqual(r["checked"], 0)
        self.assertEqual(len(r["unverifiable"]), 1)


class TestCli(unittest.TestCase):
    def _run(self, rows, extra=None):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "beats.md").write_text(table(rows))
            (d / "edl.json").write_text(json.dumps(EDL))
            (d / "words.json").write_text(json.dumps({"words": words([
                ("The", 1.0), ("markdown", 4.0), ("code", 25.0)])}))
            return subprocess.run(
                [sys.executable, str(SCRIPT), str(d / "beats.md"),
                 "--edl", str(d / "edl.json"),
                 "--words", str(d / "words.json"), *(extra or [])],
                capture_output=True, text=True)

    def test_good_table_exits_zero(self):
        r = self._run(["| b01 | 4.0 | 2.0 | 6.0 | markdown | 4.0 | x | d |"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["ok"])

    def test_mistimed_beat_exits_one_and_names_the_row(self):
        r = self._run(["| b07 | 25.0 | 2.0 | 27.0 | code | 25.0 | x | d |"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("ANCHOR PLACEMENT FAILED", r.stderr)
        self.assertIn("b07", r.stderr)

    def test_failure_warns_against_rendering(self):
        r = self._run(["| b07 | 25.0 | 2.0 | 27.0 | code | 25.0 | x | d |"])
        self.assertIn("Do NOT render graphics", r.stderr)

    def test_empty_table_is_a_usage_error(self):
        r = self._run([])
        self.assertEqual(r.returncode, 2)

    def test_missing_edl_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "beats.md").write_text(table(
                ["| b01 | 4.0 | 2.0 | 6.0 | markdown | 4.0 | x | d |"]))
            (d / "words.json").write_text(json.dumps({"words": []}))
            r = subprocess.run(
                [sys.executable, str(SCRIPT), str(d / "beats.md"),
                 "--edl", str(d / "nope.json"),
                 "--words", str(d / "words.json")],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)

    def test_help_exits_zero(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("--tolerance", r.stdout)


if __name__ == "__main__":
    unittest.main()
