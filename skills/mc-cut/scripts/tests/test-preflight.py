#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Tests for preflight.py: the pure parts (rate parsing, VFR detection,
standard-rate selection, remux command construction including the hardware
encoder ladder and vaapi wiring) plus CLI exit codes and a probe/QC
integration pass over a fixture synthesized with an ffmpeg test source
(skipped when ffmpeg is not installed). No hardware encoders are probed."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("preflight",
                                              SCRIPTS / "preflight.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


class TestParseRate(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(mod.parse_rate("30000/1001"), Fraction(30000, 1001))
        self.assertEqual(mod.parse_rate("30"), Fraction(30))
        self.assertIsNone(mod.parse_rate("0/0"))
        self.assertIsNone(mod.parse_rate(""))
        self.assertIsNone(mod.parse_rate(None))
        self.assertIsNone(mod.parse_rate("garbage"))


class TestIsVfr(unittest.TestCase):
    def test_cfr_matches(self):
        self.assertFalse(mod.is_vfr("30/1", "30/1"))
        self.assertFalse(mod.is_vfr("30000/1001", "30000/1001"))
        # tiny measurement wobble under 0.5% is still CFR
        self.assertFalse(mod.is_vfr("30/1", "2999/100"))

    def test_vfr_disagreement(self):
        self.assertTrue(mod.is_vfr("60/1", "47/1"))
        self.assertTrue(mod.is_vfr("1000/1", "30/1"))  # webcam-style nominal

    def test_unknown_rates_count_as_vfr(self):
        self.assertTrue(mod.is_vfr("0/0", "30/1"))
        self.assertTrue(mod.is_vfr("30/1", None))


class TestNearestStandardRate(unittest.TestCase):
    def test_common_rates(self):
        self.assertEqual(mod.nearest_standard_rate("2997/100"), "30000/1001")
        self.assertEqual(mod.nearest_standard_rate("30/1"), "30/1")
        self.assertEqual(mod.nearest_standard_rate("47/1"), "50/1")
        self.assertEqual(mod.nearest_standard_rate("24/1"), "24/1")
        self.assertEqual(mod.nearest_standard_rate(None), "30/1")


class TestRemuxCommand(unittest.TestCase):
    def test_software_encode(self):
        cmd = mod.remux_command("in.mov", "out.mp4", "30/1", "libx264")
        joined = " ".join(cmd)
        self.assertIn("-vf fps=30/1", joined)
        self.assertIn("-crf 18", joined)
        self.assertIn("-c:a copy", joined)
        self.assertEqual(cmd[-1], "out.mp4")

    def test_hardware_encode_bitrate_follows_source_height(self):
        cmd = mod.remux_command("in.mov", "out.mp4", "30000/1001",
                                "h264_videotoolbox", height=1080)
        joined = " ".join(cmd)
        self.assertIn("h264_videotoolbox", joined)
        self.assertIn("-b:v 24000k", joined)  # 2x the 1080 delivery tier
        self.assertNotIn("-crf", joined)
        cmd_4k = mod.remux_command("in.mov", "out.mp4", "30/1",
                                   "h264_videotoolbox", height=2160)
        self.assertIn("-b:v 80000k", " ".join(cmd_4k))

    def test_hardware_encode_unknown_height_uses_1080_tier(self):
        cmd = mod.remux_command("in.mov", "out.mp4", "30/1",
                                "h264_videotoolbox")
        self.assertIn("-b:v 24000k", " ".join(cmd))

    def test_ladder_hardware_encoders_take_master_bitrate(self):
        for enc in ("h264_nvenc", "h264_qsv", "h264_amf"):
            cmd = mod.remux_command("in.mov", "out.mp4", "30/1", enc,
                                    height=1080)
            joined = " ".join(cmd)
            self.assertIn(f"-c:v {enc}", joined)
            self.assertIn("-b:v 24000k", joined)
            self.assertNotIn("-crf", joined)
            self.assertNotIn("-allow_sw", joined)
            self.assertNotIn("hwupload", joined)

    def test_vaapi_gets_device_init_and_hwupload(self):
        cmd = mod.remux_command("in.mov", "out.mp4", "30/1", "h264_vaapi",
                                height=1080)
        joined = " ".join(cmd)
        self.assertIn("-init_hw_device vaapi=va", joined)
        self.assertIn("-filter_hw_device va", joined)
        self.assertIn("-vf fps=30/1,format=nv12,hwupload", joined)
        self.assertIn("-b:v 24000k", joined)
        self.assertNotIn("-crf", joined)
        # vaapi receives hardware frames; -pix_fmt must not be forced
        self.assertNotIn("-pix_fmt", joined)
        # device init comes before the input
        self.assertLess(cmd.index("-init_hw_device"), cmd.index("-i"))

    def test_software_encoders_keep_pix_fmt(self):
        cmd = mod.remux_command("in.mov", "out.mp4", "30/1", "libx264")
        self.assertIn("-pix_fmt yuv420p", " ".join(cmd))
        self.assertNotIn("-init_hw_device", cmd)


class TestMasterEstimate(unittest.TestCase):
    def test_master_bitrate(self):
        self.assertEqual(mod.master_bitrate_for(1080), 24000)
        self.assertEqual(mod.master_bitrate_for(2160), 80000)
        self.assertEqual(mod.master_bitrate_for(None), 24000)

    def test_estimate_from_duration(self):
        # 93 minutes of 1080p at the 24000 kbps master rate is about 16.7 GB
        est = mod.estimate_master_bytes(93 * 60, 1080, 1)
        self.assertEqual(est, int(93 * 60 * 24000 * 1000 / 8))

    def test_unknown_duration_falls_back_to_source_size(self):
        self.assertEqual(mod.estimate_master_bytes(None, 1080, 5000), 10000)


def run_cli(args):
    return subprocess.run([sys.executable, str(SCRIPTS / "preflight.py"),
                           *args], capture_output=True, text=True)


class TestCli(unittest.TestCase):
    def test_missing_file_exits_1(self):
        r = run_cli(["/nonexistent/take.mov"])
        self.assertEqual(r.returncode, 1)

    def test_no_args_is_usage_error(self):
        r = run_cli([])
        self.assertEqual(r.returncode, 2)


@unittest.skipUnless(FFMPEG, "ffmpeg/ffprobe not installed")
class TestIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.src = Path(cls.tmp.name) / "take.mp4"
        r = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-t", "2", "-i",
             "testsrc2=size=320x180:rate=30",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
             "-pix_fmt", "yuv420p", str(cls.src)],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_probe_qc_and_disk(self):
        qc = Path(self.tmp.name) / "qc"
        r = run_cli([str(self.src), "--qc-frames", str(qc)])
        self.assertEqual(r.returncode, 0, r.stderr)
        summary = json.loads(r.stdout)
        f = summary["files"][0]
        self.assertEqual(f["width"], 320)
        self.assertEqual(f["height"], 180)
        self.assertFalse(f["vfr"])
        self.assertIsNone(f["cfr_master"])
        self.assertAlmostEqual(f["duration"], 2.0, delta=0.2)
        self.assertAlmostEqual(f["fps"], 30.0, delta=0.1)
        # Several samples across the take, not just first and last: a frame
        # effect can be switched on after recording starts.
        self.assertEqual(len(f["qc_frames"]), mod.DEFAULT_QC_SAMPLES)
        for frame in f["qc_frames"]:
            self.assertTrue(Path(frame).is_file())
        self.assertTrue(summary["all_cfr"])
        self.assertTrue(summary["qc_ok"])
        self.assertIn("free_bytes", summary["disk"])

    def test_disk_gate_refuses_remux_before_any_write(self):
        """When the disk estimate does not fit, a planned remux must be
        refused BEFORE ffmpeg writes anything (runaway-write hardening)."""
        import contextlib
        import io
        real_is_vfr = mod.is_vfr
        real_check_disk = mod.core.check_disk
        mod.is_vfr = lambda *a, **k: True          # force a remux plan
        mod.core.check_disk = lambda *a, **k: (False, 0)  # force a full disk
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), \
                    contextlib.redirect_stderr(err):
                rc = mod.main([str(self.src), "--remux"])
        finally:
            mod.is_vfr = real_is_vfr
            mod.core.check_disk = real_check_disk
        self.assertEqual(rc, 1)
        self.assertIn("insufficient disk space", err.getvalue())
        summary = json.loads(out.getvalue())
        self.assertFalse(summary["disk"]["ok"])
        self.assertFalse(summary["all_cfr"])
        self.assertIsNone(summary["files"][0]["cfr_master"])
        cfr = self.src.with_name(self.src.stem + "-cfr.mp4")
        self.assertFalse(cfr.exists(), "remux output written despite refusal")

    def test_low_disk_without_remux_reports_and_exits_0(self):
        """A CFR-only pass on a tight disk still exits 0; the caller reads
        disk.ok false and stops before rendering."""
        import contextlib
        import io
        real_check_disk = mod.core.check_disk
        mod.core.check_disk = lambda *a, **k: (False, 0)
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                rc = mod.main([str(self.src)])
        finally:
            mod.core.check_disk = real_check_disk
        self.assertEqual(rc, 0)
        summary = json.loads(out.getvalue())
        self.assertFalse(summary["disk"]["ok"])
        self.assertTrue(summary["all_cfr"])


def frame(w, h, fill=(30, 30, 30), border=None, depth=0):
    """A synthetic rgb24 frame: optional flat border ring around noisy-ish
    interior content."""
    px = bytearray()
    for y in range(h):
        for x in range(w):
            d = min(x, y, w - 1 - x, h - 1 - y)
            if border is not None and d < depth:
                px += bytes(border)
            else:
                # Deterministic but varied interior, so it never reads flat.
                px += bytes(((x * 37 + y * 91) % 256,
                             (x * 17 + y * 53) % 256,
                             (x * 71 + y * 29) % 256))
    return bytes(px)


def layered_frame(w, h, layers):
    """A frame whose border is several flat colours, outermost first:
    layers is [(colour, thickness), ...]. The real defect was a black outer
    border plus a rounded orange ring."""
    px = bytearray()
    for y in range(h):
        for x in range(w):
            d = min(x, y, w - 1 - x, h - 1 - y)
            acc, colour = 0, None
            for c, t in layers:
                if d < acc + t:
                    colour = c
                    break
                acc += t
            if colour is None:
                px += bytes(((x * 37 + y * 91) % 256,
                             (x * 17 + y * 53) % 256,
                             (x * 71 + y * 29) % 256))
            else:
                px += bytes(colour)
    return bytes(px)


class TestRingGeometry(unittest.TestCase):
    def test_ring_zero_is_the_outer_edge(self):
        px = frame(10, 8)
        ring = mod.ring_pixels(px, 10, 8, 0)
        # perimeter of a 10x8 rectangle
        self.assertEqual(len(ring), 2 * 10 + 2 * (8 - 2))

    def test_ring_one_is_the_next_rectangle_in(self):
        px = frame(10, 8)
        ring = mod.ring_pixels(px, 10, 8, 1)
        self.assertEqual(len(ring), 2 * 8 + 2 * (6 - 2))

    def test_ring_beyond_the_centre_is_empty(self):
        self.assertEqual(mod.ring_pixels(frame(10, 8), 10, 8, 4), [])

    def test_negative_depth_is_empty(self):
        self.assertEqual(mod.ring_pixels(frame(10, 8), 10, 8, -1), [])


class TestVarianceAndColour(unittest.TestCase):
    def test_flat_pixels_have_zero_variance(self):
        self.assertEqual(mod.max_channel_variance([(10, 20, 30)] * 50), 0.0)

    def test_varied_pixels_have_positive_variance(self):
        px = [(i, 255 - i, i // 2) for i in range(0, 250, 10)]
        self.assertGreater(mod.max_channel_variance(px), 100.0)

    def test_single_pixel_has_no_variance(self):
        self.assertEqual(mod.max_channel_variance([(1, 2, 3)]), 0.0)

    def test_mean_colour(self):
        self.assertEqual(mod.mean_color([(0, 0, 0), (10, 20, 30)]),
                         (5.0, 10.0, 15.0))

    def test_colour_distance(self):
        self.assertAlmostEqual(
            mod.color_distance((0, 0, 0), (0, 3, 4)), 5.0)


class TestDetectBorderDepth(unittest.TestCase):
    W, H = 96, 54

    def test_clean_frame_has_no_border(self):
        self.assertEqual(
            mod.detect_border_depth(frame(self.W, self.H), self.W, self.H), 0)

    def test_flat_black_border_is_measured(self):
        px = frame(self.W, self.H, border=(0, 0, 0), depth=4)
        self.assertEqual(
            mod.detect_border_depth(px, self.W, self.H), 4)

    def test_multi_colour_decorative_frame_counts_every_layer(self):
        # The real defect: black outer border then an orange ring.
        px = layered_frame(self.W, self.H,
                           [((0, 0, 0), 3), ((255, 140, 0), 2)])
        self.assertEqual(mod.detect_border_depth(px, self.W, self.H), 5)

    def test_border_detection_is_bounded(self):
        # An entirely flat frame must not report a border the size of itself.
        px = frame(self.W, self.H, border=(5, 5, 5), depth=self.H)
        depth = mod.detect_border_depth(px, self.W, self.H)
        self.assertLessEqual(depth, int(min(self.W, self.H) * 0.25))


class TestBorderIsDistinct(unittest.TestCase):
    W, H = 96, 54

    def test_border_unlike_the_picture_is_distinct(self):
        px = frame(self.W, self.H, border=(0, 0, 0), depth=4)
        self.assertTrue(mod.border_is_distinct(px, self.W, self.H, 4))

    def test_zero_depth_is_never_distinct(self):
        px = frame(self.W, self.H)
        self.assertFalse(mod.border_is_distinct(px, self.W, self.H, 0))

    def test_flat_scene_matching_its_edges_is_not_a_border(self):
        # The false positive that matters: a genuinely dark, flat shot.
        px = bytes([20, 20, 20] * (self.W * self.H))
        depth = mod.detect_border_depth(px, self.W, self.H)
        self.assertFalse(mod.border_is_distinct(px, self.W, self.H, depth))


class TestRectMath(unittest.TestCase):
    def test_active_rect_insets_on_every_edge(self):
        self.assertEqual(mod.active_rect(100, 60, 5), (5, 5, 90, 50))

    def test_scale_rect_maps_thumbnail_to_full_frame(self):
        rect = mod.scale_rect((6, 3, 84, 48), (96, 54), (3840, 2160))
        self.assertEqual(rect, (240, 120, 3360, 1920))

    def test_scaled_dimensions_are_even(self):
        for v in mod.scale_rect((5, 3, 85, 47), (96, 54), (1920, 1080)):
            self.assertEqual(v % 2, 0)

    def test_aspect_of(self):
        self.assertAlmostEqual(mod.aspect_of((0, 0, 1920, 1080)), 16 / 9)

    def test_aspect_of_zero_height_is_zero(self):
        self.assertEqual(mod.aspect_of((0, 0, 100, 0)), 0.0)


class TestQcSampleTimes(unittest.TestCase):
    def test_samples_span_the_interior(self):
        times = mod.qc_sample_times(100.0, 5)
        self.assertEqual(len(times), 5)
        self.assertGreater(times[0], 0.0)
        self.assertLess(times[-1], 100.0)

    def test_samples_are_ordered(self):
        times = mod.qc_sample_times(600.0, 7)
        self.assertEqual(times, sorted(times))

    def test_more_than_two_samples_by_default(self):
        # The original check looked at exactly two frames and missed a defect
        # that started mid-take.
        self.assertGreater(len(mod.qc_sample_times(600.0)), 2)

    def test_zero_duration_is_a_single_sample(self):
        self.assertEqual(mod.qc_sample_times(0.0), [0.0])


@unittest.skipUnless(FFMPEG, "ffmpeg/ffprobe not installed")
class TestQcHaltsEndToEnd(unittest.TestCase):
    """Issue G, reproduced: a take with a baked-in border must STOP the
    stage, before transcription or any render is built on the bad canvas."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        cls.clean = d / "clean.mp4"
        cls.bordered = d / "bordered.mp4"
        r = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-t", "2", "-i",
             "testsrc2=size=320x180:rate=30", "-c:v", "libx264",
             "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p",
             str(cls.clean)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        # The Ecamm-style defect: content shrunk inside a flat black frame.
        r = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-t", "2", "-i",
             "testsrc2=size=320x180:rate=30", "-vf",
             "scale=240:134,pad=320:180:40:23:black", "-c:v", "libx264",
             "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p",
             str(cls.bordered)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_clean_source_passes(self):
        r = run_cli([str(self.clean)])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["qc_ok"])

    def test_bordered_source_halts_with_exit_3(self):
        r = run_cli([str(self.bordered)])
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("SOURCE QC FAILED", r.stderr)

    def test_halt_reports_the_inferred_active_rectangle(self):
        r = run_cli([str(self.bordered)])
        self.assertIn("inferred active content: crop=", r.stderr)
        qc = json.loads(r.stdout)["files"][0]["qc"]
        self.assertIsNotNone(qc["active_rect"])
        w, h = qc["active_rect"][2], qc["active_rect"][3]
        self.assertLess(w, 320)
        self.assertLess(h, 180)

    def test_halt_points_at_the_remedy(self):
        r = run_cli([str(self.bordered)])
        self.assertIn("normalize_source.py", r.stderr)

    def test_allow_qc_defects_downgrades_the_halt(self):
        r = run_cli([str(self.bordered), "--allow-qc-defects"])
        self.assertEqual(r.returncode, 0)
        self.assertFalse(json.loads(r.stdout)["qc_ok"])

    def test_no_qc_skips_the_pass(self):
        r = run_cli([str(self.bordered), "--no-qc"])
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("qc", json.loads(r.stdout)["files"][0])


if __name__ == "__main__":
    unittest.main()
