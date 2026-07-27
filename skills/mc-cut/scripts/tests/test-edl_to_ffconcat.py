#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Tests for edl_to_ffconcat.py: the virtual timeline written from an EDL.

The pure builders are covered directly. The all-intra guard is the one that
matters most and is covered by behaviour, because a long-GOP source produces a
timeline that is WRONG in exactly the way nothing else notices: right
duration, wrong frames.
"""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "edl_to_ffconcat", HERE.parent / "edl_to_ffconcat.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


SEGS = [
    {"source": "/m.mp4", "start": 14.23, "end": 19.10},
    {"source": "/m.mp4", "start": 19.59, "end": 20.56},
    {"source": "/m.mp4", "start": 1221.433, "end": 1222.167},
]


class TestFfconcatLines(unittest.TestCase):
    def test_header_is_first(self):
        self.assertEqual(mod.ffconcat_lines(SEGS)[0], "ffconcat version 1.0")

    def test_one_triple_per_segment(self):
        lines = mod.ffconcat_lines(SEGS)[1:]
        self.assertEqual(len(lines), len(SEGS) * 3)
        self.assertEqual(lines[0], "file '/m.mp4'")
        self.assertEqual(lines[1], "inpoint 14.230000")
        self.assertEqual(lines[2], "outpoint 19.100000")

    def test_source_override_replaces_every_path(self):
        lines = mod.ffconcat_lines(SEGS, "/proxy-intra.mp4")
        files = [ln for ln in lines if ln.startswith("file ")]
        self.assertEqual(len(files), 3)
        self.assertTrue(all(ln == "file '/proxy-intra.mp4'" for ln in files))

    def test_times_keep_sub_millisecond_precision(self):
        """Truncating to 3dp would drift across hundreds of segments."""
        lines = mod.ffconcat_lines(SEGS)
        self.assertIn("outpoint 1222.167000", lines)


class TestMpvEdlLines(unittest.TestCase):
    def test_header_is_the_mpv_magic(self):
        self.assertEqual(mod.mpv_edl_lines(SEGS)[0], "# mpv EDL v0")

    def test_mpv_takes_length_not_end(self):
        line = mod.mpv_edl_lines(SEGS)[1]
        self.assertTrue(line.endswith(",14.230000,4.870000"),
                        f"expected start,LENGTH; got {line}")

    def test_path_is_byte_length_quoted(self):
        """%<bytes>%<path> so a comma in a filename cannot split the record."""
        line = mod.mpv_edl_lines(SEGS, "/a,b.mp4")[1]
        self.assertTrue(line.startswith("%8%/a,b.mp4,"), line)

    def test_quoting_counts_bytes_not_characters(self):
        """"/é.mp4" is 6 characters but 7 bytes; mpv counts bytes, and a
        character count would truncate the path it reads."""
        path = "/é.mp4"
        self.assertEqual(len(path), 6)
        self.assertEqual(len(path.encode()), 7)
        line = mod.mpv_edl_lines(SEGS, path)[1]
        self.assertTrue(line.startswith("%7%"), line)


class TestGuardBehaviour(unittest.TestCase):
    """The all-intra guard, exercised through main()."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.edl = self.d / "edl.json"
        self.edl.write_text(json.dumps({"source": "/m.mp4", "segments": SEGS}))
        self.out = self.d / "t.ffconcat"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, argv, intra):
        real = mod.is_all_intra
        mod.is_all_intra = lambda *a, **k: intra
        try:
            return mod.main(argv)
        finally:
            mod.is_all_intra = real

    def test_long_gop_source_is_refused_and_writes_nothing(self):
        rc = self._run([str(self.edl), "-o", str(self.out),
                        "--source", "/m.mp4"], intra=False)
        self.assertEqual(rc, 1)
        self.assertFalse(self.out.exists(),
                         "a refused run must not leave a wrong timeline")

    def test_allow_long_gop_is_an_explicit_escape_hatch(self):
        rc = self._run([str(self.edl), "-o", str(self.out),
                        "--source", "/m.mp4", "--allow-long-gop"],
                       intra=False)
        self.assertEqual(rc, 0)
        self.assertTrue(self.out.exists())

    def test_intra_source_writes_the_timeline(self):
        rc = self._run([str(self.edl), "-o", str(self.out),
                        "--source", "/m.mp4"], intra=True)
        self.assertEqual(rc, 0)
        body = self.out.read_text()
        self.assertTrue(body.startswith("ffconcat version 1.0"))
        self.assertEqual(body.count("inpoint"), 3)

    def test_unprobeable_source_is_an_error_not_a_pass(self):
        real = mod.is_all_intra
        mod.is_all_intra = lambda *a, **k: None
        try:
            rc = mod.main([str(self.edl), "-o", str(self.out),
                           "--source", "/m.mp4"])
        finally:
            mod.is_all_intra = real
        self.assertEqual(rc, 1)

    def test_empty_edl_is_a_usage_error(self):
        empty = self.d / "empty.json"
        empty.write_text(json.dumps({"source": "/m.mp4", "segments": []}))
        self.assertEqual(mod.main([str(empty), "-o", str(self.out)]), 2)


class TestIsAllIntraParsing(unittest.TestCase):
    """is_all_intra reads ffprobe's key_frame column; the shapes it must
    survive are csv rows with trailing commas and blank lines."""

    def _with_stdout(self, text, rc=0):
        class P:
            returncode = rc
            stdout = text
        real = mod.subprocess.run
        mod.subprocess.run = lambda *a, **k: P()
        try:
            return mod.is_all_intra("/x.mp4")
        finally:
            mod.subprocess.run = real

    def test_all_ones_is_intra(self):
        self.assertTrue(self._with_stdout("1,\n1,\n1,\n"))

    def test_any_zero_is_not_intra(self):
        self.assertFalse(self._with_stdout("1,\n0,\n1,\n"))

    def test_no_frames_is_unknown(self):
        self.assertIsNone(self._with_stdout("\n"))

    def test_ffprobe_failure_is_unknown(self):
        self.assertIsNone(self._with_stdout("1,\n", rc=1))


if __name__ == "__main__":
    unittest.main(verbosity=1)
