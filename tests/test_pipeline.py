"""End to end on the synthetic library: every stage as the user runs it, through a two-second render.

setUpClass builds the library in a temporary folder, runs the stages once, then runs a few scenarios on copies of the
handed-off project; the tests read what those runs wrote. Each of the review's four high-severity bugs has a test here
(search for "bug"). The medium bugs still open are expected failures: when one is fixed its test reports an unexpected
success, which fails the suite until the decorator comes off.

Needs ffmpeg and ffprobe; the build side also needs Node, and the render needs Playwright's browser. What cannot run
here is skipped and says why. SLIDESHOW_KEEP_TEST_DIRS=1 keeps the temporary projects for a post-mortem.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

import fixture
from helpers import KEEP, by_original, frame_count, have_ffmpeg, have_node, have_playwright, node, read_csv, stage

from common import set_config_value  # noqa: E402  (helpers put curate/ on sys.path)

CURATION = [("ingest", ()), ("index", ()), ("validate", ()), ("identify", ("--tags-only",)), ("select", ()),
            ("sheets", ("--pdf",)), ("handoff", ()), ("show", ())]


class Pipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not have_ffmpeg():
            raise unittest.SkipTest("needs ffmpeg and ffprobe on PATH")
        cls.tmp = Path(tempfile.mkdtemp(prefix="slideshow-tests-"))
        cls.project = cls.tmp / "project"
        fixture.make_library(cls.project)
        fixture.write_config(cls.project)
        cls.runs, cls.errors = {}, {}
        for name, args in CURATION:
            cls.runs[name] = stage(cls.project, name, *args)
            if cls.runs[name].code != 0:
                return                                   # every later stage and every scenario reads what this one writes
        cls._build_side()
        for scenario in (cls._ledger, cls._guard, cls._truncated, cls._undated):
            try:
                scenario()
            except Exception as e:                       # one broken scenario must not take the others down
                cls.errors[scenario.__name__] = e

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "tmp", None):
            if KEEP:
                print(f"\nkept test projects in {cls.tmp}")
            else:
                shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def _build_side(cls):
        """prep, build and a two-second render. A failure here stops the render only: the scenarios run on their own
        copies, and one that needs the build side fails loudly on its own output rather than turning into a skip."""
        if not have_node():
            return
        for name, args in (("prep", ()), ("build", ())):
            cls.runs[name] = node(cls.project, name, *args)
            if cls.runs[name].code != 0:
                return
        if have_playwright():
            cls.runs["render"] = node(cls.project, "render", "--seconds", "2")

    # ------------------------------------------------------------ scenarios on copies of the handed-off project

    @classmethod
    def _copy(cls, name: str) -> Path:
        dst = cls.tmp / name
        shutil.copytree(cls.project, dst)
        return dst

    @classmethod
    def _ledger(cls):
        """An owner's swap through add-item, then a handoff: the swap must survive (review bug 1)."""
        if not have_node():
            return
        p = cls._copy("ledger")
        media = read_csv(p / "handoff" / "media.csv")
        cut = read_csv(p / "handoff" / "cut-list.csv")
        leaving = next(r["filename"] for r in media if r["type"] == "still" and r["featured"] != "yes")
        incoming = next(r["filename"] for r in cut if r["reason"] == "over-cap" and r["filename"].endswith(".JPG"))
        names = lambda: {r["filename"] for r in read_csv(p / "handoff" / "media.csv")}  # noqa: E731
        led = dict(leaving=leaving, incoming=incoming,
                   add=node(p, "add-item", str(p / "work" / incoming), incoming[:10], "--replace", leaving))
        led["refused"], led["after_refusal"] = stage(p, "handoff"), names()
        led["dry"] = stage(p, "handoff", "--dry-run")
        led["discard"], led["after_discard"] = stage(p, "handoff", "--discard-changes"), names()
        led["again"] = stage(p, "handoff")
        led["log"] = [ln for ln in (p / "handoff" / "changes.log").read_text(encoding="utf-8").splitlines() if ln.strip()]
        cls.ledger = led

    @classmethod
    def _guard(cls):
        """The same guard without the build tools: a change line in the log is enough to stop a handoff."""
        p = cls._copy("guard")
        with open(p / "handoff" / "changes.log", "a", encoding="utf-8") as f:
            f.write("2026-09-23T00:00:00.000Z  add     2019-01-01_IMG_0000.JPG  type=still  1600x1200  date=2019-01-01/day\n")
        cls.guard = stage(p, "handoff")

    @classmethod
    def _truncated(cls):
        """A Live Photo whose clip ffprobe can read and ffmpeg cannot decode (review bug 4)."""
        t = cls.tmp / "truncated"
        phone = t / "sources" / "phone"
        phone.mkdir(parents=True)
        src = cls.project / "sources" / "phone"
        for n in ("IMG_1001.JPG", "IMG_5001.JPG", "IMG_5002.JPG", "IMG_5003.JPG"):
            shutil.copy2(src / n, phone / n)
        fixture.truncated_copy(src / "IMG_1001.MOV", phone / "IMG_1001.MOV")
        fixture.write_config(t, sources=False)
        cls.truncated = {n: stage(t, n) for n in ("ingest", "index", "validate")}
        cls.truncated_project = t

    @classmethod
    def _undated(cls):
        """[selection] undated_cap seats undated files; they must get through prep (review finding 7, open)."""
        if not have_node():
            return
        p = cls._copy("undated")
        set_config_value(p / "config.toml", "selection", "undated_cap", "2")
        cls.undated = {"select": stage(p, "select", "--include-undated"), "handoff": stage(p, "handoff")}
        cls.undated["prep"] = node(p, "prep")

    # ------------------------------------------------------------ helpers

    def ran(self, name: str):
        r = self.runs.get(name)
        if r is None:
            self.skipTest(f"{name} did not run: an earlier stage failed or its tools are missing")
        self.assertEqual(r.code, 0, str(r))
        return r

    def scenario(self, attr: str):
        err = self.errors.get(f"_{attr}")
        if err is not None:
            raise AssertionError(f"the {attr} scenario failed to set up: {err!r}")
        if not hasattr(self, attr):
            self.skipTest(f"the {attr} scenario did not run: an earlier stage failed, or Node is not installed")
        return getattr(self, attr)

    def items(self, project: Path | None = None) -> dict[str, dict]:
        return by_original(read_csv((project or self.project) / "index" / "items.csv"))

    # ------------------------------------------------------------ the pipeline itself

    def test_curation_stages_succeed(self):
        for name, _ in CURATION:
            with self.subTest(stage=name):
                self.ran(name)

    def test_every_file_is_accounted_for(self):
        m = re.search(r"accounting: (\d+) planned = (\d+) verified \+ (\d+) failed", self.ran("ingest").out)
        self.assertTrue(m and m.group(1) == m.group(2) and m.group(3) == "0", self.runs["ingest"].out[-800:])
        self.assertRegex(self.ran("select").out, r"accounting: .* OK")
        self.assertRegex(self.ran("handoff").out, r"invariant: .* OK")
        self.assertTrue((self.project / "index" / "sheets" / "contact-sheets.pdf").is_file())

    def test_live_photo_shot_at_home_pairs(self):
        items = self.items()
        self.assertEqual(items["IMG_1001.JPG"]["type"], "livephoto-still")
        self.assertEqual(items["IMG_1001.MOV"]["type"], "livephoto-video")

    def test_build_side_succeeds(self):
        self.ran("prep")
        self.assertIn("acceptance checks: all pass", self.ran("build").out)

    def test_short_render(self):
        r = self.runs.get("render")
        if r is not None and r.code != 0 and "no browser could start" in r.out:
            self.skipTest("no browser could start here")
        self.assertIn("render OK", self.ran("render").out)
        self.assertEqual(frame_count(self.project / "build" / "test-2s.mp4"), 60)

    # ------------------------------------------------------------ bug 3: Takeout sidecars

    def test_takeout_duplicates_get_their_own_sidecars(self):
        """Review bug 3: `IMG_2000.jpg.supplemental-metadata(1).json` belongs to IMG_2000(1).jpg, not IMG_2000.jpg."""
        self.ran("index")
        sidecars = {r["member"].rsplit("/", 1)[-1]: r for r in read_csv(self.project / "index" / "takeout-sidecars.csv")}
        for sidecar, photo in (("IMG_2000.jpg.supplemental-metadata.json", "IMG_2000.jpg"),
                               ("IMG_2000.jpg.supplemental-metadata(1).json", "IMG_2000(1).jpg"),
                               ("IMG_3000.jpg.json", "IMG_3000.jpg"),
                               ("IMG_3000.jpg(1).json", "IMG_3000(1).jpg")):
            with self.subTest(sidecar=sidecar):
                self.assertEqual(sidecars[sidecar]["media_member"].rsplit("/", 1)[-1], photo)
        items = self.items()
        self.assertEqual(items["IMG_2000.jpg"]["people_tags"], "Sam Jones")
        self.assertEqual(items["IMG_2000(1).jpg"]["people_tags"], "Alex Jones")

    def test_a_sidecar_with_no_photo_is_named(self):
        """Review bug 3: a Takeout sidecar that reaches no file is named by ingest, not only counted."""
        self.assertIn("IMG_9999.jpg.supplemental-metadata.json", self.ran("ingest").out)

    def test_duplicate_titles_are_still_flagged(self):
        """Gate 5 is unchanged: two sidecars sharing a title in one folder are flagged for the owner."""
        self.ran("validate")
        flagged = {r["filename"].split("_", 1)[1] for r in read_csv(self.project / "index" / "flags.csv") if r["gate"] == "title-collision"}
        self.assertLessEqual({"IMG_2000.jpg", "IMG_2000(1).jpg", "IMG_3000.jpg", "IMG_3000(1).jpg"}, flagged)

    # ------------------------------------------------------------ bug 2: machines without the detection packages

    def test_identify_without_detection_packages_says_what_to_do(self):
        """Review bug 2: where OpenCV and onnxruntime have no build, identify says so and names --tags-only."""
        self.ran("identify")
        r = stage(self.project, "identify", "--force", without=("cv2", "onnxruntime"))
        self.assertEqual(r.code, 2, str(r))
        self.assertIn("--tags-only", r.out)
        self.assertNotIn("Traceback", r.out)

    # ------------------------------------------------------------ bug 1: the ledger

    def test_handoff_keeps_the_owners_swaps(self):
        """Review bug 1: a handoff after add-item must not rebuild the set from the index and undo the swap."""
        led = self.scenario("ledger")
        self.assertEqual(led["add"].code, 0, str(led["add"]))
        self.assertNotEqual(led["refused"].code, 0, str(led["refused"]))
        self.assertIn("--discard-changes", led["refused"].out)
        self.assertIn(led["incoming"], led["after_refusal"])
        self.assertNotIn(led["leaving"], led["after_refusal"])
        self.assertNotEqual(led["dry"].code, 0, str(led["dry"]))

    def test_handoff_discard_changes_rebuilds_and_says_so(self):
        led = self.scenario("ledger")
        self.assertEqual(led["discard"].code, 0, str(led["discard"]))
        self.assertIn(led["leaving"], led["after_discard"])
        self.assertNotIn(led["incoming"], led["after_discard"])
        self.assertEqual(led["again"].code, 0, str(led["again"]))
        marks = [ln for ln in led["log"] if ln.split()[1:2] == ["handoff"]]
        self.assertGreaterEqual(len(marks), 3, led["log"])      # the first handoff, the discard, the one after
        self.assertTrue(any("discard" in ln for ln in marks), led["log"])

    def test_handoff_refuses_on_a_change_line(self):
        g = self.scenario("guard")
        self.assertNotEqual(g.code, 0, str(g))
        self.assertIn("--discard-changes", g.out)

    # ------------------------------------------------------------ bug 4: a clip ffmpeg cannot decode

    def test_truncated_clip_does_not_stop_index(self):
        """Review bug 4: index finishes, leaves the pair unverified, and validate flags it."""
        t = self.scenario("truncated")
        for name, r in t.items():
            with self.subTest(stage=name):
                self.assertEqual(r.code, 0, str(r))
        items = self.items(self.truncated_project)
        self.assertEqual(items["IMG_1001.MOV"]["type"], "video")
        flags = read_csv(self.truncated_project / "index" / "flags.csv")
        self.assertTrue(any(f["gate"] == "pair-unverified" and "IMG_1001" in f["filename"] for f in flags))

    # ------------------------------------------------------------ findings still open (expected failures)

    @unittest.expectedFailure
    def test_known_bug_live_photo_shot_away_pairs(self):
        """Review finding 5: the still's clock is EXIF local time, the clip's is converted to the project's zone."""
        self.assertEqual(self.items()["IMG_1002.JPG"]["type"], "livephoto-still")

    @unittest.expectedFailure
    def test_known_bug_example_config_seats_no_tradition(self):
        """Review finding 6: config.example.toml ships a live October 24-31 anchor."""
        rows = read_csv(self.project / "index" / "selection.csv")
        self.assertEqual([r["filename"] for r in rows if "AUTUMN-TRADITION" in r["anchor"]], [])

    def test_undated_scenario_sets_up(self):
        u = self.scenario("undated")
        self.assertEqual(u["select"].code, 0, str(u["select"]))
        self.assertEqual(u["handoff"].code, 0, str(u["handoff"]))
        self.assertRegex(u["select"].out, r"undated\s+2\s+\d+\s+2")

    @unittest.expectedFailure
    def test_known_bug_undated_files_reach_prep(self):
        """Review finding 7: seated undated files carry a blank date and precision, which prep refuses."""
        self.assertEqual(self.scenario("undated")["prep"].code, 0)


if __name__ == "__main__":
    unittest.main()
