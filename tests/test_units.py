"""Fast checks, no pipeline run: the pieces the review's four high-severity bugs lived in.

Takeout sidecar names (bug 3), the probe's return shape on a clip ffmpeg cannot decode (bug 4), sharpness without
OpenCV and the split requirements (bug 2), and the changes.log reading handoff guards itself with (bug 1).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from helpers import CURATE, have_ffmpeg

from stages import _probe, _takeout, handoff  # noqa: E402  (helpers put curate/ on sys.path)
import setup  # noqa: E402  (curate/setup.py, standard library only)


class TakeoutSidecarNames(unittest.TestCase):
    """_takeout.resolve_media_member: which media file a JSON sidecar describes (review bug 3)."""

    CASES = [
        # (sidecar member, media names in its folder, expected media member)
        ("F/IMG_0001.HEIC.json", {"IMG_0001.HEIC"}, "F/IMG_0001.HEIC"),
        ("F/IMG_0001.HEIC.supplemental-metadata.json", {"IMG_0001.HEIC"}, "F/IMG_0001.HEIC"),
        ("F/PXL_20230815_123456789.MP.jpg.supplemental-metad.json", {"PXL_20230815_123456789.MP.jpg"}, "F/PXL_20230815_123456789.MP.jpg"),
        ("F/IMG_0001.HEIC.su.json", {"IMG_0001.HEIC"}, "F/IMG_0001.HEIC"),
        ("IMG_1.jpg.json", {"IMG_1.jpg"}, "IMG_1.jpg"),
        # a duplicate title, older naming: the counter follows the whole title
        ("F/IMG_3000.jpg(1).json", {"IMG_3000.jpg", "IMG_3000(1).jpg"}, "F/IMG_3000(1).jpg"),
        # a duplicate title, newer naming: the counter follows the supplemental-metadata suffix, whole or cut short
        ("F/IMG_2000.jpg.supplemental-metadata(1).json", {"IMG_2000.jpg", "IMG_2000(1).jpg"}, "F/IMG_2000(1).jpg"),
        ("F/IMG_2000.jpg.supplemental-me(2).json", {"IMG_2000.jpg", "IMG_2000(2).jpg"}, "F/IMG_2000(2).jpg"),
        # a duplicate whose file is not in the folder must not claim the original
        ("F/IMG_2000.jpg.supplemental-metadata(1).json", {"IMG_2000.jpg"}, ""),
        ("F/IMG_3000.jpg(1).json", {"IMG_3000.jpg"}, ""),
        # a file whose own name carries a counter
        ("F/photo(1).jpg.json", {"photo(1).jpg"}, "F/photo(1).jpg"),
        ("F/photo(1).jpg.supplemental-metadata.json", {"photo(1).jpg", "photo.jpg"}, "F/photo(1).jpg"),
        # an older export cut long titles short: one media name starts with the cut title
        ("F/Screenshot_20200101-120000_Some Long Applicat.json", {"Screenshot_20200101-120000_Some Long Application Name.jpg"},
         "F/Screenshot_20200101-120000_Some Long Application Name.jpg"),
        # not a photo's sidecar
        ("F/metadata.json", {"IMG_1.jpg"}, ""),
        ("F/IMG_1.jpg", {"IMG_1.jpg"}, ""),
    ]

    def test_names(self):
        for member, names, want in self.CASES:
            with self.subTest(member=member, names=sorted(names)):
                self.assertEqual(_takeout.resolve_media_member(member, set(names)), want)

    def test_unresolved_sidecars_are_named_with_a_reason(self):
        rows = [dict(member=f"F/{m}", folder="F", title=t, source="takeout-zip") for m, t in (
            ("IMG_1.jpg.json", "IMG_1.jpg"),
            ("IMG_1.jpg.supplemental-metadata.json", "IMG_1.jpg"),    # a second sidecar for the same file: ambiguous
            ("IMG_9.jpg.json", "IMG_9.jpg"),                          # no such photo
            ("IMG_2.jpg.json", "IMG_2.jpg"),                          # fine
        )]
        ambiguous = _takeout.finish_rows(rows, {"F": {"IMG_1.jpg", "IMG_2.jpg"}})
        self.assertEqual(ambiguous, 1)
        self.assertEqual([r["media_member"] for r in rows], ["", "", "", "F/IMG_2.jpg"])
        lines = _takeout.unresolved_lines(rows)
        self.assertEqual(len(lines), 3, lines)
        self.assertTrue(any("F/IMG_9.jpg.json" in ln and "no media file" in ln for ln in lines), lines)
        self.assertTrue(any("F/IMG_1.jpg.json" in ln and "IMG_1.jpg" in ln and "another sidecar" in ln for ln in lines), lines)


@unittest.skipUnless(have_ffmpeg(), "needs ffmpeg")
class ProbeReturnShape(unittest.TestCase):
    """_probe.best_frame_distance returns three values on every path, the one index.py unpacks (review bug 4)."""

    def test_undecodable_clip(self):
        with tempfile.TemporaryDirectory() as td:
            still, clip = Path(td) / "IMG_1.JPG", Path(td) / "IMG_1.MOV"
            Image.new("RGB", (64, 48), (120, 80, 40)).save(still)
            clip.write_bytes(b"\x00\x00\x00\x14ftypqt  \x00\x00\x02\x00qt  " + b"garbage" * 100)
            self.assertEqual(_probe.best_frame_distance(str(still), str(clip), "ffmpeg"), (None, 0, None))


class SharpnessWithoutOpenCV(unittest.TestCase):
    """The index stage runs without OpenCV, and its sharpness numbers are the ones OpenCV gave (review bug 2)."""

    def test_probe_imports_without_opencv_or_onnxruntime(self):
        code = ("import sys; sys.modules['cv2'] = None; sys.modules['onnxruntime'] = None; "
                f"sys.path.insert(0, {str(CURATE)!r}); "
                "from stages import _probe; from PIL import Image; "
                "print(_probe.sharpness(Image.new('RGB', (64, 48), (10, 20, 30))))")
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])

    def test_laplacian_variance_matches_opencv(self):
        try:
            import cv2
        except ImportError:
            self.skipTest("OpenCV is not installed here, so there is nothing to compare against")
        rng = np.random.default_rng(7)
        for shape in ((1, 1), (2, 3), (5, 4), (48, 64), (333, 517), (1024, 768)):
            with self.subTest(shape=shape):
                gray = rng.integers(0, 256, shape).astype(np.float64)
                want = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                self.assertAlmostEqual(_probe.laplacian_variance(gray), want, places=6)

    def test_sharpness_of_a_photo_is_unchanged(self):
        try:
            import cv2
        except ImportError:
            self.skipTest("OpenCV is not installed here, so there is nothing to compare against")
        rng = np.random.default_rng(11)
        for size in ((1600, 1200), (1200, 1600), (640, 480)):
            with self.subTest(size=size):
                img = Image.fromarray(rng.integers(0, 256, (size[1], size[0], 3)).astype(np.uint8))
                g = img.convert("L")
                if max(g.size) > _probe.SHARPNESS_LONG_SIDE:
                    s = _probe.SHARPNESS_LONG_SIDE / max(g.size)
                    g = g.resize((max(1, int(g.width * s)), max(1, int(g.height * s))))
                want = round(float(cv2.Laplacian(np.asarray(g, dtype=np.float64), cv2.CV_64F).var()), 2)
                self.assertEqual(_probe.sharpness(img), want)


class Requirements(unittest.TestCase):
    """The core install needs nothing that lacks a build for older Macs; detection is its own, optional file (bug 2)."""

    @staticmethod
    def pins(name: str) -> dict[str, str]:
        out = {}
        for line in (CURATE / name).read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                pkg, _, version = line.partition("==")
                out[pkg.strip().lower()] = version.strip()
        return out

    def test_core_has_no_detection_packages(self):
        core = self.pins("requirements.txt")
        self.assertNotIn("opencv-python-headless", core)
        self.assertNotIn("onnxruntime", core)
        for pkg in ("pillow", "pillow-heif", "numpy", "imagehash", "scipy", "pywavelets", "tzdata", "tzlocal"):
            self.assertTrue(core.get(pkg), f"{pkg} is not pinned in requirements.txt")

    def test_detection_file_pins_both_packages(self):
        det = self.pins("requirements-detection.txt")
        self.assertTrue(det.get("opencv-python-headless"))
        self.assertTrue(det.get("onnxruntime"))

    def test_setup_reports_detection_as_optional(self):
        pins = {name.lower(): optional for name, _version, optional in setup.pinned()}
        self.assertFalse(pins["pillow"])
        self.assertTrue(pins["onnxruntime"])
        self.assertTrue(pins["opencv-python-headless"])

    def test_pip_failure_names_the_package_not_the_python(self):
        stderr = ("ERROR: Could not find a version that satisfies the requirement onnxruntime==1.29.0 (from versions: none)\n"
                  "ERROR: No matching distribution found for onnxruntime==1.29.0\n")
        msg = setup.pip_failure(stderr)
        self.assertIn("onnxruntime==1.29.0", msg)


class ChangesLog(unittest.TestCase):
    """handoff.unreplayed_changes: the lines written after the set was last laid down from the index (review bug 1)."""

    ADD = "2026-09-23T16:28:12.909Z  add     2019-01-12_IMG_5006.JPG  type=still  1200x1600  date=2019-01-12/day"
    REMOVE = "2026-09-23T16:28:12.909Z  remove  2019-03-03_IMG_5008.JPG  -> handoff/_removed/, cut-list.csv reason=swapped"
    MARK = "2026-09-23T16:00:00.000Z  handoff media.csv laid down from index/selection.csv: 31 files"

    def lines_after(self, *lines: str) -> list[str]:
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "changes.log"
            log.write_text("".join(ln + "\n" for ln in lines), encoding="utf-8")
            return handoff.unreplayed_changes(log)

    def test_no_log(self):
        self.assertEqual(handoff.unreplayed_changes(Path(tempfile.gettempdir()) / "no-such-changes.log"), [])

    def test_empty_log(self):
        self.assertEqual(self.lines_after(), [])

    def test_log_from_before_the_marker_counts_every_line(self):
        self.assertEqual(self.lines_after(self.ADD, self.REMOVE), [self.ADD, self.REMOVE])

    def test_lines_after_the_last_handoff(self):
        self.assertEqual(self.lines_after(self.ADD, self.MARK), [])
        self.assertEqual(self.lines_after(self.MARK, self.ADD, self.REMOVE), [self.ADD, self.REMOVE])
        self.assertEqual(self.lines_after(self.MARK, self.ADD, self.MARK, self.REMOVE), [self.REMOVE])


class StagesImport(unittest.TestCase):
    """Every curation stage imports: a syntax slip anywhere stops the suite here, not an hour into a run."""

    def test_import_every_stage(self):
        import importlib
        for name in ("ingest", "index", "validate", "identify", "select", "sheets", "handoff", "show"):
            with self.subTest(stage=name):
                importlib.import_module(f"stages.{name}")


if __name__ == "__main__":
    unittest.main()
