#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Tests for normalize_source.py: the crop geometry, and the one guarantee
the whole script rests on, that a spatial correction moves nothing in time."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "normalize_source.py"
spec = importlib.util.spec_from_file_location("normalize_source", SCRIPT)
ns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ns)

import composite_core as core  # noqa: E402

FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


class TestParsers(unittest.TestCase):
    def test_parse_crop(self):
        self.assertEqual(ns.parse_crop("3360:1880:240:140"),
                         (240, 140, 3360, 1880))

    def test_parse_crop_rejects_wrong_arity(self):
        with self.assertRaises(ValueError):
            ns.parse_crop("100:200:300")

    def test_parse_crop_rejects_non_integers(self):
        with self.assertRaises(ValueError):
            ns.parse_crop("a:b:c:d")

    def test_parse_crop_rejects_non_positive_size(self):
        with self.assertRaises(ValueError):
            ns.parse_crop("0:100:0:0")

    def test_parse_size(self):
        self.assertEqual(ns.parse_size("3840x2160"), (3840, 2160))

    def test_parse_size_is_case_insensitive(self):
        self.assertEqual(ns.parse_size("1920X1080"), (1920, 1080))

    def test_parse_size_rejects_garbage(self):
        with self.assertRaises(ValueError):
            ns.parse_size("1920")

    def test_parse_aspect_ratio_form(self):
        self.assertAlmostEqual(ns.parse_aspect("16:9"), 16 / 9)

    def test_parse_aspect_decimal_form(self):
        self.assertAlmostEqual(ns.parse_aspect("1.5"), 1.5)

    def test_parse_aspect_rejects_zero_denominator(self):
        with self.assertRaises(ValueError):
            ns.parse_aspect("16:0")


class TestShiftCrop(unittest.TestCase):
    def test_shifts_right_and_down(self):
        self.assertEqual(ns.shift_crop((100, 100, 200, 100), 50, 20, 1000, 500),
                         (150, 120, 200, 100))

    def test_shifts_left_with_a_negative_offset(self):
        # The real defect: the subject sat about 5 percent left of centre.
        self.assertEqual(ns.shift_crop((100, 0, 200, 100), -60, 0, 1000, 500),
                         (40, 0, 200, 100))

    def test_clamps_at_the_left_edge_rather_than_failing(self):
        self.assertEqual(ns.shift_crop((10, 10, 200, 100), -500, -500,
                                       1000, 500), (0, 0, 200, 100))

    def test_clamps_at_the_right_edge(self):
        x, _, w, _ = ns.shift_crop((700, 0, 200, 100), 500, 0, 1000, 500)
        self.assertEqual(x + w, 1000)

    def test_zero_offset_is_a_no_op(self):
        rect = (100, 50, 200, 100)
        self.assertEqual(ns.shift_crop(rect, 0, 0, 1000, 500), rect)


class TestFitAspect(unittest.TestCase):
    def test_already_correct_aspect_is_unchanged_in_size(self):
        _, _, w, h = ns.fit_aspect((0, 0, 1920, 1080), 16 / 9)
        self.assertAlmostEqual(w / h, 16 / 9, places=2)

    def test_too_wide_rect_is_narrowed(self):
        _, _, w, h = ns.fit_aspect((0, 0, 2000, 1000), 16 / 9)
        self.assertAlmostEqual(w / h, 16 / 9, places=2)
        self.assertLessEqual(w, 2000)
        self.assertLessEqual(h, 1000)

    def test_too_tall_rect_is_shortened(self):
        _, _, w, h = ns.fit_aspect((0, 0, 1600, 1200), 16 / 9)
        self.assertAlmostEqual(w / h, 16 / 9, places=2)
        self.assertLessEqual(h, 1200)

    def test_fit_only_ever_shrinks(self):
        # Growing could pull the baked-in border back into frame, which is
        # the whole thing being removed.
        for rect in [(0, 0, 2000, 1000), (0, 0, 1600, 1200),
                     (10, 10, 999, 501)]:
            _, _, w, h = ns.fit_aspect(rect, 16 / 9)
            self.assertLessEqual(w, rect[2])
            self.assertLessEqual(h, rect[3])

    def test_fit_keeps_the_centre(self):
        x, y, w, h = ns.fit_aspect((100, 100, 2000, 1000), 16 / 9)
        self.assertAlmostEqual(x + w / 2, 100 + 1000, delta=2)
        self.assertAlmostEqual(y + h / 2, 100 + 500, delta=2)

    def test_dimensions_are_even(self):
        _, _, w, h = ns.fit_aspect((0, 0, 1999, 1001), 16 / 9)
        self.assertEqual(w % 2, 0)
        self.assertEqual(h % 2, 0)


class TestClampRect(unittest.TestCase):
    def test_oversized_rect_is_clamped_to_the_frame(self):
        self.assertEqual(ns.clamp_rect((0, 0, 5000, 5000), 1920, 1080),
                         (0, 0, 1920, 1080))

    def test_origin_is_pulled_back_inside(self):
        x, y, w, h = ns.clamp_rect((1900, 1000, 200, 200), 1920, 1080)
        self.assertLessEqual(x + w, 1920)
        self.assertLessEqual(y + h, 1080)

    def test_all_values_are_even(self):
        for v in ns.clamp_rect((3, 5, 101, 203), 1920, 1080):
            self.assertEqual(v % 2, 0)


class TestBuildNormalizeCommand(unittest.TestCase):
    def test_crop_filter_is_in_wh_xy_order(self):
        cmd = ns.build_normalize_command("in.mp4", "out.mp4",
                                         (240, 140, 3360, 1880), "30/1",
                                         encoder="libx264")
        vf = cmd[cmd.index("-vf") + 1]
        self.assertIn("crop=3360:1880:240:140", vf)

    def test_audio_is_copied_never_re_encoded(self):
        cmd = ns.build_normalize_command("in.mp4", "out.mp4", (0, 0, 100, 100),
                                         "30/1", encoder="libx264")
        self.assertIn("-c:a", cmd)
        self.assertEqual(cmd[cmd.index("-c:a") + 1], "copy")

    def test_frame_rate_is_forced_so_the_master_stays_cfr(self):
        cmd = ns.build_normalize_command("in.mp4", "out.mp4", (0, 0, 100, 100),
                                         "30000/1001", encoder="libx264")
        self.assertIn("fps=30000/1001", cmd[cmd.index("-vf") + 1])

    def test_output_size_adds_a_scale_after_the_crop(self):
        cmd = ns.build_normalize_command("in.mp4", "out.mp4",
                                         (0, 0, 3360, 1880), "30/1",
                                         output_size=(3840, 2160),
                                         encoder="libx264")
        vf = cmd[cmd.index("-vf") + 1]
        self.assertLess(vf.index("crop="), vf.index("scale="))

    def test_no_output_size_means_no_scale(self):
        cmd = ns.build_normalize_command("in.mp4", "out.mp4", (0, 0, 100, 100),
                                         "30/1", encoder="libx264")
        self.assertNotIn("scale=", cmd[cmd.index("-vf") + 1])

    def test_no_trim_or_seek_flags_anywhere(self):
        # The guarantee, at the command level: nothing here can move time.
        cmd = ns.build_normalize_command("in.mp4", "out.mp4", (0, 0, 100, 100),
                                         "30/1", encoder="libx264")
        for flag in ("-ss", "-t", "-to", "-itsoffset"):
            self.assertNotIn(flag, cmd)


class TestCliUsage(unittest.TestCase):
    def _run(self, argv):
        return subprocess.run([sys.executable, str(SCRIPT), *argv],
                              capture_output=True, text=True)

    def test_missing_media_is_usage_error(self):
        r = self._run(["/nope/take.mp4", "-o", "/tmp/out.mp4", "--auto"])
        self.assertEqual(r.returncode, 2)

    def test_help_exits_zero(self):
        r = self._run(["--help"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("--auto", r.stdout)


@unittest.skipUnless(FFMPEG, "ffmpeg/ffprobe not installed")
class TestNormalizeEndToEnd(unittest.TestCase):
    """Issue G's second half: correcting a baked-in border, and proving the
    correction left every timecode alone."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.src = cls.dir / "bordered.mp4"
        # 320x180 with content shrunk to 240x134 inside a black frame, plus
        # audio, so the copy-through path is exercised.
        r = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-t", "3", "-i",
             "testsrc2=size=320x180:rate=30", "-f", "lavfi", "-t", "3",
             "-i", "sine=frequency=440:sample_rate=48000", "-shortest",
             "-vf", "scale=240:134,pad=320:180:40:23:black",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
             "-pix_fmt", "yuv420p", "-c:a", "aac", str(cls.src)],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _run(self, argv):
        return subprocess.run([sys.executable, str(SCRIPT), *argv],
                              capture_output=True, text=True)

    def test_explicit_crop_produces_a_corrected_master(self):
        out = self.dir / "fixed-explicit.mp4"
        r = self._run([str(self.src), "-o", str(out),
                       "--crop", "240:134:40:23"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(out.is_file())
        self.assertEqual(core.probe_dims(out), (240, 134))

    def test_auto_detects_and_removes_the_border(self):
        out = self.dir / "fixed-auto.mp4"
        r = self._run([str(self.src), "-o", str(out), "--auto"])
        self.assertEqual(r.returncode, 0, r.stderr)
        w, h = core.probe_dims(out)
        self.assertLess(w, 320)
        self.assertLess(h, 180)

    def test_duration_is_preserved(self):
        """The guarantee that lets the existing EDL survive."""
        out = self.dir / "fixed-dur.mp4"
        r = self._run([str(self.src), "-o", str(out),
                       "--crop", "240:134:40:23"])
        self.assertEqual(r.returncode, 0, r.stderr)
        summary = json.loads(r.stdout)
        self.assertTrue(summary["timecodes_preserved"])
        self.assertAlmostEqual(summary["output_duration"],
                               summary["source_duration"], delta=0.1)

    def test_audio_survives(self):
        out = self.dir / "fixed-audio.mp4"
        self._run([str(self.src), "-o", str(out), "--crop", "240:134:40:23"])
        self.assertTrue(core.probe_has_audio(out))

    def test_output_size_restores_the_delivery_resolution(self):
        out = self.dir / "fixed-scaled.mp4"
        r = self._run([str(self.src), "-o", str(out),
                       "--crop", "240:134:40:23", "--output-size", "320x180"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(core.probe_dims(out), (320, 180))

    def test_recentre_offset_moves_the_window(self):
        left = self.dir / "fixed-left.mp4"
        right = self.dir / "fixed-right.mp4"
        self._run([str(self.src), "-o", str(left), "--crop", "200:112:60:34",
                   "--offset-x", "-20"])
        self._run([str(self.src), "-o", str(right), "--crop", "200:112:60:34",
                   "--offset-x", "20"])
        a = json.loads(self._run([str(self.src), "-o", str(left),
                                  "--crop", "200:112:60:34",
                                  "--offset-x", "-20"]).stdout)
        b = json.loads(self._run([str(self.src), "-o", str(right),
                                  "--crop", "200:112:60:34",
                                  "--offset-x", "20"]).stdout)
        self.assertNotEqual(a["crop"], b["crop"])

    def test_target_aspect_is_honoured(self):
        out = self.dir / "fixed-aspect.mp4"
        r = self._run([str(self.src), "-o", str(out),
                       "--crop", "240:134:40:23", "--target-aspect", "16:9"])
        self.assertEqual(r.returncode, 0, r.stderr)
        w, h = core.probe_dims(out)
        self.assertAlmostEqual(w / h, 16 / 9, places=1)

    def test_clean_source_with_auto_reports_nothing_to_do(self):
        clean = self.dir / "clean.mp4"
        r = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-t", "2", "-i",
             "testsrc2=size=320x180:rate=30", "-c:v", "libx264",
             "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p",
             str(clean)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        r = self._run([str(clean), "-o", str(self.dir / "noop.mp4"), "--auto"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("no border ring detected", r.stderr)

    def test_summary_tells_the_caller_not_to_re_cut(self):
        out = self.dir / "fixed-msg.mp4"
        r = self._run([str(self.src), "-o", str(out),
                       "--crop", "240:134:40:23"])
        self.assertIn("Do NOT re-transcribe or re-cut", r.stderr)

    def test_crop_and_auto_are_mutually_exclusive(self):
        r = self._run([str(self.src), "-o", str(self.dir / "x.mp4"),
                       "--crop", "240:134:40:23", "--auto"])
        self.assertEqual(r.returncode, 2)

    def test_one_of_crop_or_auto_is_required(self):
        r = self._run([str(self.src), "-o", str(self.dir / "x.mp4")])
        self.assertEqual(r.returncode, 2)

    def test_no_temp_file_survives(self):
        out = self.dir / "fixed-clean-temp.mp4"
        self._run([str(self.src), "-o", str(out), "--crop", "240:134:40:23"])
        leftovers = [p for p in self.dir.iterdir() if ".normalizing" in p.name]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
