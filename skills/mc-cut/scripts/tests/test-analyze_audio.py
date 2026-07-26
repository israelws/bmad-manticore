#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Tests for analyze_audio.py: the silencedetect parser and the interval
algebra every cut-timing decision now rests on.

The ffmpeg invocation itself is not unit-tested (it needs a media file); the
parsing of its output and all the interval math are pure and covered here."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "analyze_audio.py"
spec = importlib.util.spec_from_file_location("analyze_audio", SCRIPT)
aa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aa)


def line(kind, t, dur=None):
    if kind == "start":
        return f"[silencedetect @ 0x7f8] silence_start: {t}"
    return (f"[silencedetect @ 0x7f8] silence_end: {t} | "
            f"silence_duration: {dur}")


class TestParseSilencedetect(unittest.TestCase):
    def test_paired_lines_become_intervals(self):
        text = "\n".join([line("start", 1.5), line("end", 3.0, 1.5),
                          line("start", 10.0), line("end", 12.25, 2.25)])
        self.assertEqual(aa.parse_silencedetect(text, 20.0),
                         [(1.5, 3.0), (10.0, 12.25)])

    def test_unclosed_final_silence_is_closed_at_duration(self):
        # A file that ends in silence gets a start with no matching end.
        text = "\n".join([line("start", 1.0), line("end", 2.0, 1.0),
                          line("start", 18.5)])
        self.assertEqual(aa.parse_silencedetect(text, 20.0),
                         [(1.0, 2.0), (18.5, 20.0)])

    def test_noise_lines_are_ignored(self):
        text = "\n".join(["ffmpeg version 7.1", "  Stream #0:0 Video: h264",
                          line("start", 1.0), line("end", 2.0, 1.0),
                          "frame= 100 fps=50"])
        self.assertEqual(aa.parse_silencedetect(text, 5.0), [(1.0, 2.0)])

    def test_empty_output_is_no_silence(self):
        self.assertEqual(aa.parse_silencedetect("", 10.0), [])

    def test_intervals_are_clamped_into_the_media(self):
        text = "\n".join([line("start", -0.5), line("end", 2.0, 2.5),
                          line("start", 9.0), line("end", 25.0, 16.0)])
        self.assertEqual(aa.parse_silencedetect(text, 10.0),
                         [(0.0, 2.0), (9.0, 10.0)])

    def test_zero_length_intervals_are_dropped(self):
        text = "\n".join([line("start", 3.0), line("end", 3.0, 0.0)])
        self.assertEqual(aa.parse_silencedetect(text, 10.0), [])

    def test_overlapping_intervals_merge(self):
        text = "\n".join([line("start", 1.0), line("end", 3.0, 2.0),
                          line("start", 2.5), line("end", 4.0, 1.5)])
        self.assertEqual(aa.parse_silencedetect(text, 10.0), [(1.0, 4.0)])

    def test_result_is_sorted(self):
        text = "\n".join([line("start", 8.0), line("end", 9.0, 1.0),
                          line("start", 1.0), line("end", 2.0, 1.0)])
        self.assertEqual(aa.parse_silencedetect(text, 10.0),
                         [(1.0, 2.0), (8.0, 9.0)])


class TestComplement(unittest.TestCase):
    def test_gaps_between_intervals(self):
        self.assertEqual(aa.complement([(1.0, 2.0), (5.0, 6.0)], 10.0),
                         [(0.0, 1.0), (2.0, 5.0), (6.0, 10.0)])

    def test_no_intervals_is_the_whole_span(self):
        self.assertEqual(aa.complement([], 10.0), [(0.0, 10.0)])

    def test_full_coverage_is_empty(self):
        self.assertEqual(aa.complement([(0.0, 10.0)], 10.0), [])

    def test_leading_and_trailing_coverage_leaves_only_the_middle(self):
        self.assertEqual(aa.complement([(0.0, 1.0), (9.0, 10.0)], 10.0),
                         [(1.0, 9.0)])

    def test_complement_is_an_involution_on_clean_input(self):
        silence = [(1.0, 2.0), (5.0, 6.0)]
        speech = aa.complement(silence, 10.0)
        self.assertEqual(aa.complement(speech, 10.0), silence)

    def test_silence_and_speech_partition_the_duration(self):
        silence = [(1.0, 2.0), (5.0, 6.5)]
        speech = aa.complement(silence, 10.0)
        self.assertAlmostEqual(aa.total(silence) + aa.total(speech), 10.0)


class TestOverlapSeconds(unittest.TestCase):
    def test_fully_inside(self):
        self.assertAlmostEqual(
            aa.overlap_seconds([(0.0, 10.0)], 2.0, 5.0), 3.0)

    def test_partial_at_each_end(self):
        self.assertAlmostEqual(
            aa.overlap_seconds([(1.0, 3.0), (8.0, 12.0)], 2.0, 9.0), 2.0)

    def test_disjoint_is_zero(self):
        self.assertAlmostEqual(
            aa.overlap_seconds([(0.0, 1.0)], 5.0, 6.0), 0.0)

    def test_empty_span_is_zero(self):
        self.assertAlmostEqual(
            aa.overlap_seconds([(0.0, 10.0)], 5.0, 5.0), 0.0)

    def test_inverted_span_is_zero(self):
        self.assertAlmostEqual(
            aa.overlap_seconds([(0.0, 10.0)], 6.0, 5.0), 0.0)


class TestSilentFraction(unittest.TestCase):
    def test_all_silent(self):
        self.assertAlmostEqual(
            aa.silent_fraction([(0.0, 10.0)], 1.0, 5.0), 1.0)

    def test_none_silent(self):
        self.assertAlmostEqual(
            aa.silent_fraction([(20.0, 30.0)], 1.0, 5.0), 0.0)

    def test_half_silent(self):
        self.assertAlmostEqual(
            aa.silent_fraction([(0.0, 3.0)], 1.0, 5.0), 0.5)

    def test_zero_span_reads_as_silent(self):
        self.assertAlmostEqual(aa.silent_fraction([], 5.0, 5.0), 1.0)


class TestEnclosing(unittest.TestCase):
    def test_inside(self):
        self.assertEqual(aa.enclosing([(1.0, 3.0)], 2.0), (1.0, 3.0))

    def test_boundaries_are_inclusive(self):
        self.assertEqual(aa.enclosing([(1.0, 3.0)], 1.0), (1.0, 3.0))
        self.assertEqual(aa.enclosing([(1.0, 3.0)], 3.0), (1.0, 3.0))

    def test_outside_is_none(self):
        self.assertIsNone(aa.enclosing([(1.0, 3.0)], 5.0))

    def test_between_intervals_is_none(self):
        self.assertIsNone(aa.enclosing([(1.0, 2.0), (5.0, 6.0)], 3.0))


class TestNearestSilence(unittest.TestCase):
    SIL = [(0.0, 1.0), (5.0, 6.0), (9.0, 10.0)]

    def test_point_already_in_silence_is_unchanged(self):
        self.assertEqual(aa.nearest_silence(self.SIL, 5.5, 0.5), 5.5)

    def test_snaps_to_the_nearest_edge(self):
        self.assertAlmostEqual(aa.nearest_silence(self.SIL, 4.8, 0.5), 5.0)
        self.assertAlmostEqual(aa.nearest_silence(self.SIL, 6.2, 0.5), 6.0)

    def test_out_of_budget_returns_none(self):
        self.assertIsNone(aa.nearest_silence(self.SIL, 3.0, 0.5))

    def test_budget_boundary_is_inclusive(self):
        self.assertAlmostEqual(aa.nearest_silence(self.SIL, 4.5, 0.5), 5.0)

    def test_direction_back_never_moves_forward(self):
        # 6.2 is nearer to 6.0 (back) than to 9.0 (forward).
        self.assertAlmostEqual(
            aa.nearest_silence(self.SIL, 6.2, 0.5, direction="back"), 6.0)
        self.assertIsNone(
            aa.nearest_silence(self.SIL, 6.2, 0.5, direction="forward"))

    def test_direction_forward_never_moves_back(self):
        self.assertAlmostEqual(
            aa.nearest_silence(self.SIL, 4.8, 0.5, direction="forward"), 5.0)
        self.assertIsNone(
            aa.nearest_silence(self.SIL, 4.8, 0.5, direction="back"))

    def test_directional_snapping_cannot_invert_a_span(self):
        # The regression behind the collapsed-candidate bug: an end at 0.9
        # with silence both behind (0.0 to 1.0... ) and ahead. Unconstrained
        # "nearest" could pull an end backwards past its own start; forward
        # snapping cannot.
        sil = [(0.0, 0.5), (1.5, 2.0)]
        start = aa.nearest_silence(sil, 0.5, 0.8, direction="back")
        end = aa.nearest_silence(sil, 0.9, 0.8, direction="forward")
        self.assertEqual(start, 0.5)
        self.assertAlmostEqual(end, 1.5)
        self.assertGreater(end, start)


class TestRecordRoundTrip(unittest.TestCase):
    def test_as_records_then_to_pairs_is_identity(self):
        pairs = [(1.0, 2.5), (5.25, 6.0)]
        self.assertEqual(aa.to_pairs(aa.as_records(pairs)), pairs)

    def test_records_carry_dur(self):
        rec = aa.as_records([(1.0, 2.5)])[0]
        self.assertEqual(rec["dur"], 1.5)

    def test_total_sums_lengths(self):
        self.assertAlmostEqual(aa.total([(0.0, 1.0), (5.0, 7.5)]), 3.5)


class TestBuild(unittest.TestCase):
    def test_payload_shape_and_partition(self):
        payload = aa.build("m.mp4", 10.0, [(1.0, 2.0), (5.0, 6.0)], -30.0, 0.3)
        self.assertEqual(payload["counts"]["silence"], 2)
        self.assertEqual(payload["silent_seconds"], 2.0)
        self.assertEqual(payload["speech_seconds"], 8.0)
        self.assertAlmostEqual(
            payload["silent_seconds"] + payload["speech_seconds"], 10.0)
        self.assertEqual(payload["noise_db"], -30.0)
        self.assertEqual(payload["map_granularity"], 0.3)

    def test_no_silence_means_all_speech(self):
        payload = aa.build("m.mp4", 10.0, [], -30.0, 0.3)
        self.assertEqual(payload["silent_seconds"], 0.0)
        self.assertEqual(payload["speech_seconds"], 10.0)
        self.assertEqual(payload["counts"]["speech"], 1)


class TestRealTakeShape(unittest.TestCase):
    """The measured shape of the take that broke the pipeline: about 402
    silence intervals totalling about 309s in a 1230s take. The gap-based
    detector it replaced found 12."""

    def _synthetic_take(self):
        # 402 silences averaging 0.77s spread through a 20.5 minute take.
        text = []
        t = 0.5
        for _ in range(402):
            end = t + 0.769
            text.append(line("start", round(t, 3)))
            text.append(line("end", round(end, 3), 0.769))
            t = end + 2.29
        return "\n".join(text)

    def test_parses_hundreds_of_intervals(self):
        pairs = aa.parse_silencedetect(self._synthetic_take(), 1230.0)
        self.assertEqual(len(pairs), 402)

    def test_totals_are_in_the_measured_range(self):
        pairs = aa.parse_silencedetect(self._synthetic_take(), 1230.0)
        payload = aa.build("m.mp4", 1230.0, pairs, -30.0, 0.3)
        self.assertGreater(payload["silent_seconds"], 240.0)
        self.assertGreater(payload["counts"]["silence"], 300)


class TestCli(unittest.TestCase):
    def test_missing_media_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(
                [sys.executable, str(SCRIPT), str(Path(tmp) / "nope.mp4"),
                 "-o", str(Path(tmp) / "map.json")],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)
            self.assertIn("media not found", r.stderr)

    def test_non_positive_map_granularity_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "m.mp4"
            media.write_bytes(b"not really media")
            r = subprocess.run(
                [sys.executable, str(SCRIPT), str(media), "-o",
                 str(Path(tmp) / "map.json"), "--map-granularity", "0"],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)

    def test_help_exits_zero(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("--noise", r.stdout)


if __name__ == "__main__":
    unittest.main()
