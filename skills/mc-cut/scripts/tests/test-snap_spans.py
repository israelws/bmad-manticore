#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Tests for snap_spans.py, the step 7a snapping mechanic.

The load-bearing property is that snapping is DIRECTIONAL. An unconstrained
"nearest silence" can pull a span's end backwards past its own start and
annihilate it, which is a real bug that was caught once already in
cutplan.py's candidate path. This is the same guarantee for approved spans."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "snap_spans.py"
spec = importlib.util.spec_from_file_location("snap_spans", SCRIPT)
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)


def audio_map(silence, duration=10.0, media="m.mp4"):
    return {"media": media, "duration": duration,
            "silence": [{"start": s, "end": e, "dur": e - s}
                        for s, e in silence]}


def run_cli(spans, amap, extra=None, expect=None):
    with tempfile.TemporaryDirectory() as tmp:
        s = Path(tmp) / "spans.json"
        a = Path(tmp) / "audio-map.json"
        o = Path(tmp) / "snapped.json"
        s.write_text(json.dumps(spans))
        a.write_text(json.dumps(amap))
        r = subprocess.run(
            [sys.executable, str(SCRIPT), str(s), "--audio-map", str(a),
             "-o", str(o), *(extra or [])],
            capture_output=True, text=True)
        if expect is not None:
            assert r.returncode == expect, f"rc={r.returncode} {r.stderr}"
        out = json.loads(o.read_text()) if o.is_file() else None
        return out, r


class TestDirectional(unittest.TestCase):

    def test_start_moves_earlier_and_end_moves_later(self):
        silence = [(0.0, 0.5), (2.0, 3.0)]
        out = ss.snap_span({"start": 1.0, "end": 1.2}, silence, 1.0)
        self.assertTrue(out["snapped"])
        self.assertAlmostEqual(out["start"], 0.5)
        self.assertAlmostEqual(out["end"], 2.0)

    def test_an_end_is_never_pulled_back_past_its_own_start(self):
        # The collapse bug. Unconstrained, end 1.2 would snap BACK to 0.5
        # (0.7s away) rather than forward to 2.0 (0.8s away), landing the span
        # on 0.5-0.5 and deleting it.
        silence = [(0.0, 0.5), (2.0, 3.0)]
        out = ss.snap_span({"start": 1.0, "end": 1.2}, silence, 1.0)
        self.assertGreater(out["end"], out["start"])
        self.assertAlmostEqual(out["end"], 2.0)

    def test_a_span_only_ever_widens(self):
        silence = [(0.0, 0.5), (2.0, 3.0)]
        out = ss.snap_span({"start": 1.0, "end": 1.2}, silence, 1.0)
        self.assertLessEqual(out["start"], 1.0)
        self.assertGreaterEqual(out["end"], 1.2)

    def test_edges_already_in_silence_do_not_move(self):
        silence = [(1.0, 2.0), (5.0, 6.0)]
        out = ss.snap_span({"start": 1.5, "end": 5.5}, silence, 1.0)
        self.assertAlmostEqual(out["start"], 1.5)
        self.assertAlmostEqual(out["end"], 5.5)
        self.assertEqual(out["shift"], {"start": 0.0, "end": 0.0})


class TestUnsnapped(unittest.TestCase):

    def test_an_edge_out_of_reach_leaves_the_span_unsnapped(self):
        silence = [(0.0, 0.1)]
        out = ss.snap_span({"start": 5.0, "end": 6.0}, silence, 0.25)
        self.assertFalse(out["snapped"])

    def test_unsnapped_spans_keep_their_original_times(self):
        silence = [(0.0, 0.1)]
        out = ss.snap_span({"start": 5.0, "end": 6.0}, silence, 0.25)
        self.assertAlmostEqual(out["start"], 5.0)
        self.assertAlmostEqual(out["end"], 6.0)

    def test_the_unreachable_edges_are_named(self):
        silence = [(4.9, 5.05)]
        out = ss.snap_span({"start": 5.0, "end": 9.0}, silence, 0.25)
        self.assertEqual(out["unsnapped_edges"], ["end"])

    def test_report_counts_snapped_and_unsnapped(self):
        silence = [(0.0, 0.5), (2.0, 3.0)]
        spans = ss.snap_all([{"start": 1.0, "end": 1.2},
                             {"start": 7.0, "end": 8.0}], silence, 1.0)
        report = ss.build_report(spans)
        self.assertFalse(report["ok"])
        self.assertEqual(report["spans"], 2)
        self.assertEqual(report["snapped"], 1)
        self.assertEqual(len(report["unsnapped"]), 1)


class TestPassthrough(unittest.TestCase):

    def test_extra_keys_survive_the_round_trip(self):
        silence = [(0.0, 0.5), (2.0, 3.0)]
        span = {"start": 1.0, "end": 1.2, "id": "c7", "quote": "the thing",
                "reason": "editorial: cut the aside"}
        out = ss.snap_span(span, silence, 1.0)
        self.assertEqual(out["id"], "c7")
        self.assertEqual(out["quote"], "the thing")
        self.assertEqual(out["reason"], "editorial: cut the aside")

    def test_the_input_span_is_not_mutated(self):
        silence = [(0.0, 0.5), (2.0, 3.0)]
        span = {"start": 1.0, "end": 1.2}
        ss.snap_span(span, silence, 1.0)
        self.assertEqual(span, {"start": 1.0, "end": 1.2})

    def test_duration_is_recomputed_from_the_snapped_edges(self):
        silence = [(0.0, 0.5), (2.0, 3.0)]
        out = ss.snap_span({"start": 1.0, "end": 1.2}, silence, 1.0)
        self.assertAlmostEqual(out["dur"], 1.5)


class TestParsing(unittest.TestCase):

    def test_a_bare_list_is_accepted(self):
        self.assertEqual(ss.parse_spans([{"start": 0, "end": 1}]),
                         [{"start": 0, "end": 1}])

    def test_an_object_with_a_spans_key_is_accepted(self):
        self.assertEqual(ss.parse_spans({"spans": [{"start": 0, "end": 1}]}),
                         [{"start": 0, "end": 1}])

    def test_anything_else_is_rejected(self):
        self.assertIsNone(ss.parse_spans({"nope": 1}))


class TestCLI(unittest.TestCase):

    def test_all_snapped_exits_zero(self):
        amap = audio_map([(0.0, 0.5), (2.0, 3.0)])
        out, r = run_cli([{"start": 1.0, "end": 1.2}], amap,
                         ["--snap-ms", "1000"], expect=0)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0]["snapped"])

    def test_an_unsnapped_span_exits_one_and_says_to_check_by_ear(self):
        amap = audio_map([(0.0, 0.1)])
        out, r = run_cli([{"start": 5.0, "end": 6.0}], amap, expect=1)
        self.assertFalse(out[0]["snapped"])
        self.assertIn("by ear", r.stderr)

    def test_a_span_missing_end_is_a_usage_error(self):
        amap = audio_map([(0.0, 0.5)])
        run_cli([{"start": 1.0}], amap, expect=2)

    def test_an_audio_map_without_silence_is_a_usage_error(self):
        run_cli([{"start": 1.0, "end": 1.2}], {"media": "m.mp4"}, expect=2)

    def test_help_works(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("--snap-ms", r.stdout)


if __name__ == "__main__":
    unittest.main()
