#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Tests for verify_edl.py, the EDL gate.

The headline case is the one that would break a naive implementation: a cut
correctly placed in verified silence that ALSO sits inside a pause-absorbed
word span must PASS. Failing it would reject correct cuts on exactly the
footage the two-source rule exists for."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "verify_edl.py"
spec = importlib.util.spec_from_file_location("verify_edl", SCRIPT)
ve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ve)

DURATION = 20.0
# Silence islands. Everything else is speech.
SILENCE = [(0.0, 1.0), (5.0, 6.0), (10.0, 11.0), (19.0, 20.0)]


def words_from(spans):
    return [{"word": t, "start": s, "end": e} for t, s, e in spans]


def audio_map(duration=DURATION, silence=None, media="m.mp4"):
    pairs = list(SILENCE if silence is None else silence)
    speech, cursor = [], 0.0
    for s, e in pairs:
        if s > cursor:
            speech.append((cursor, s))
        cursor = max(cursor, e)
    if duration > cursor:
        speech.append((cursor, duration))
    return {
        "media": media, "duration": duration,
        "silence": [{"start": s, "end": e, "dur": e - s} for s, e in pairs],
        "speech": [{"start": s, "end": e, "dur": e - s} for s, e in speech],
    }


def seg(start, end, source="m.mp4", quote="words", reason="keep"):
    return {"source": source, "start": start, "end": end,
            "quote": quote, "reason": reason}


def edl(segments, duration=DURATION, source="m.mp4"):
    return {"source": source, "source_duration": duration, "fade_ms": 30,
            "pad_ms": 60, "segments": segments}


def report_for(segments, words=None, duration=DURATION, tolerance=0.0,
               amap=None):
    payload = edl(segments, duration)
    maps = {None: ve.audio.to_pairs((amap or audio_map())["silence"])}
    transcripts = {None: words or []}
    return ve.build_report(payload, maps, transcripts, tolerance)


def run_cli(payload, amap, words, extra=None, expect=None):
    with tempfile.TemporaryDirectory() as tmp:
        e = Path(tmp) / "edl.json"
        a = Path(tmp) / "audio-map.json"
        w = Path(tmp) / "words.json"
        o = Path(tmp) / "edl-check.json"
        e.write_text(json.dumps(payload))
        a.write_text(json.dumps(amap))
        w.write_text(json.dumps(words))
        r = subprocess.run(
            [sys.executable, str(SCRIPT), str(e), "--audio-map", str(a),
             "--words", str(w), "-o", str(o), *(extra or [])],
            capture_output=True, text=True)
        if expect is not None:
            assert r.returncode == expect, f"rc={r.returncode} {r.stderr}"
        report = json.loads(o.read_text()) if o.is_file() else None
        return report, r


class TestPauseAbsorption(unittest.TestCase):
    """The reason word spans are context and never a verdict."""

    def test_boundary_in_silence_passes_even_inside_an_absorbed_word(self):
        # "about." swallowed the pause after it: the word's timestamp span
        # reaches from 4.5 all the way to 5.8, straight through the silence
        # at 5.0-6.0. This is the real 2026-07-24 shape.
        words = words_from([("about.", 4.5, 5.8), ("next", 6.1, 6.5)])
        r = report_for([seg(0.0, 5.5), seg(10.5, DURATION)], words)
        self.assertTrue(r["ok"], r["violations"])

    def test_word_overlap_alone_is_never_a_violation(self):
        words = words_from([("about.", 4.5, 5.8)])
        r = report_for([seg(0.0, 5.5), seg(10.5, DURATION)], words)
        self.assertEqual([v for v in r["violations"]
                          if "inside_word" in v], [])

    def test_word_overlap_is_reported_as_detail_on_a_failing_boundary(self):
        # 7.5 is in speech AND mid-word: the boundary fails on the audio, and
        # the word tells the creator how bad the miss is.
        words = words_from([("hello", 7.2, 7.9)])
        r = report_for([seg(0.0, 7.5), seg(10.5, DURATION)], words)
        boundary = [v for v in r["violations"] if v["kind"] == "boundary"]
        self.assertEqual(len(boundary), 1)
        self.assertEqual(boundary[0]["inside_word"], "hello")
        self.assertIn("inside the word", boundary[0]["reason"])


class TestBoundaries(unittest.TestCase):

    def test_boundaries_resting_in_silence_pass(self):
        r = report_for([seg(0.0, 5.5), seg(10.5, DURATION)])
        self.assertTrue(r["ok"], r["violations"])

    def test_boundary_in_speech_fails(self):
        r = report_for([seg(0.0, 5.5), seg(12.0, DURATION)])
        self.assertFalse(r["ok"])
        self.assertEqual(r["violations"][0]["kind"], "boundary")
        self.assertEqual(r["violations"][0]["edge"], "start")

    def test_failure_reports_distance_to_the_nearest_silence(self):
        r = report_for([seg(0.0, 5.5), seg(12.0, DURATION)])
        v = r["violations"][0]
        self.assertAlmostEqual(v["nearest_silence"], 11.0)
        self.assertAlmostEqual(v["distance"], 1.0)

    def test_tolerance_can_admit_a_near_miss(self):
        r = report_for([seg(0.0, 5.5), seg(11.2, DURATION)], tolerance=0.5)
        self.assertTrue(r["ok"], r["violations"])

    def test_zero_tolerance_is_the_default_and_rejects_the_near_miss(self):
        r = report_for([seg(0.0, 5.5), seg(11.2, DURATION)])
        self.assertFalse(r["ok"])

    def test_a_source_with_no_silence_at_all_is_named_as_such(self):
        amap = audio_map(silence=[])
        r = report_for([seg(2.0, 8.0)], amap=amap)
        self.assertFalse(r["ok"])
        self.assertIn("no detected silence", r["violations"][0]["reason"])


class TestExemptions(unittest.TestCase):
    """Boundaries that are not cuts. Nothing was removed, so nothing can clip."""

    def test_source_head_and_tail_are_not_cuts(self):
        # 0.0 sits in silence here anyway, so use a map with no silence at the
        # edges to prove the exemption is doing the work.
        amap = audio_map(silence=[(5.0, 6.0)])
        r = report_for([seg(0.0, 5.5), seg(5.5, DURATION)], amap=amap)
        self.assertTrue(r["ok"], r["violations"])

    def test_contiguous_segments_share_a_boundary_that_is_not_a_cut(self):
        amap = audio_map(silence=[])
        r = report_for([seg(0.0, 7.0), seg(7.0, DURATION)], amap=amap)
        self.assertTrue(r["ok"], r["violations"])

    def test_a_real_cut_between_two_segments_is_still_checked(self):
        amap = audio_map(silence=[])
        r = report_for([seg(0.0, 7.0), seg(9.0, DURATION)], amap=amap)
        self.assertFalse(r["ok"])


class TestReordering(unittest.TestCase):
    """Step 5 picks best takes and orders segments. A reordered EDL is correct."""

    def test_segments_out_of_source_order_are_not_a_violation(self):
        r = report_for([seg(10.5, DURATION), seg(0.0, 5.5)])
        self.assertTrue(r["ok"], r["violations"])


class TestStructure(unittest.TestCase):

    def test_zero_length_segment_fails(self):
        r = report_for([seg(5.5, 5.5)])
        self.assertFalse(r["ok"])
        self.assertEqual(r["violations"][0]["kind"], "structure")

    def test_inverted_segment_fails(self):
        r = report_for([seg(10.5, 5.5)])
        self.assertFalse(r["ok"])
        self.assertIn("not before", r["violations"][0]["reason"])

    def test_segment_past_the_source_duration_fails(self):
        r = report_for([seg(0.0, 25.0)])
        self.assertFalse(r["ok"])
        self.assertTrue(any("past the source duration" in v["reason"]
                            for v in r["violations"]))

    def test_segment_without_a_source_fails(self):
        bad = {"start": 0.0, "end": 5.5, "quote": "q", "reason": "r"}
        r = report_for([bad])
        self.assertFalse(r["ok"])
        self.assertIn("no source", r["violations"][0]["reason"])


class TestProvenance(unittest.TestCase):
    """Every EDL segment records the words it carries and why."""

    def test_missing_quote_fails(self):
        r = report_for([seg(0.0, 5.5, quote=""), seg(10.5, DURATION)])
        self.assertFalse(r["ok"])
        self.assertTrue(any(v["kind"] == "provenance" for v in r["violations"]))

    def test_missing_reason_fails(self):
        r = report_for([seg(0.0, 5.5, reason="   "), seg(10.5, DURATION)])
        self.assertFalse(r["ok"])

    def test_provenance_and_boundary_failures_are_reported_together(self):
        r = report_for([seg(0.0, 5.5), seg(12.0, DURATION, quote="")])
        kinds = {v["kind"] for v in r["violations"]}
        self.assertEqual(kinds, {"boundary", "provenance"})


class TestMultiSource(unittest.TestCase):

    def test_maps_are_matched_to_each_segment_source(self):
        a = audio_map(media="a.mp4", silence=[(5.0, 6.0)])
        b = audio_map(media="b.mp4", silence=[(12.0, 13.0)])
        maps = {"a.mp4": ve.audio.to_pairs(a["silence"]),
                "b.mp4": ve.audio.to_pairs(b["silence"])}
        payload = edl([seg(0.0, 5.5, source="a.mp4"),
                       seg(12.5, DURATION, source="b.mp4")])
        r = ve.build_report(payload, maps, {None: []}, 0.0)
        self.assertTrue(r["ok"], r["violations"])

    def test_a_segment_whose_source_has_no_map_is_named(self):
        maps = {"a.mp4": ve.audio.to_pairs(audio_map()["silence"])}
        payload = edl([seg(0.0, 5.5, source="b.mp4")])
        r = ve.build_report(payload, maps, {None: []}, 0.0)
        self.assertFalse(r["ok"])
        self.assertIn("no audio map covers", r["violations"][0]["reason"])


class TestCLI(unittest.TestCase):

    def test_clean_edl_exits_zero(self):
        payload = edl([seg(0.0, 5.5), seg(10.5, DURATION)])
        report, r = run_cli(payload, audio_map(), {"words": []}, expect=0)
        self.assertTrue(report["ok"])

    def test_bad_edl_exits_one_and_names_the_segment(self):
        payload = edl([seg(0.0, 5.5), seg(12.0, DURATION)])
        report, r = run_cli(payload, audio_map(), {"words": []}, expect=1)
        self.assertFalse(report["ok"])
        self.assertIn("EDL VERIFICATION FAILED", r.stderr)
        self.assertIn("does not rest in an audio-verified silence", r.stderr)

    def test_an_edl_with_no_segments_is_a_usage_error(self):
        run_cli(edl([]), audio_map(), {"words": []}, expect=2)

    def test_an_audio_map_without_silence_is_a_usage_error(self):
        payload = edl([seg(0.0, 5.5)])
        run_cli(payload, {"media": "m.mp4", "duration": 20.0},
                {"words": []}, expect=2)

    def test_the_words_file_must_carry_a_words_key(self):
        payload = edl([seg(0.0, 5.5)])
        run_cli(payload, audio_map(), {"tokens": []}, expect=2)

    def test_help_works(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("--audio-map", r.stdout)


if __name__ == "__main__":
    unittest.main()
