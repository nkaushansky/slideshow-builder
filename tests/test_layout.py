"""The layout engine on synthetic sets: `bin/build --dry-run` lays each show out and runs its own acceptance checks.

No media is needed: build falls back to media.csv's dimensions when prep has not run. The sets are a phone library's
mix (landscape and portrait stills, some 16:9, a few panoramas, videos, Live Photos, featured stills) at the sizes
that matter: the first run's 469 items, a derived 15-minute cut with mixed tiles off, and a small trip show.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import fixture
from helpers import KEEP, have_node, node, stage

SCENARIOS = {
    # name: (items, video share, featured share, mixed tiles, years)
    "first-run-mix": (469, 54 / 469, 75 / 469, True, 13),
    "derived-cut-mixed-off": (409, 0.08, 0.0, False, 13),
    "trip": (40, 0.10, 0.14, True, 1),
}


@unittest.skipUnless(have_node(), "needs Node")
class Layout(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="slideshow-layout-"))
        cls.results = {}
        for name, (items, videos, featured, mixed, years) in SCENARIOS.items():
            p = cls.tmp / name
            fixture.write_layout_project(p, items, videos, featured, mixed, years)
            show = stage(p, "show")
            built = node(p, "build", "--dry-run") if show.code == 0 else None
            cls.results[name] = (p, show, built)

    @classmethod
    def tearDownClass(cls):
        if KEEP:
            print(f"\nkept layout projects in {cls.tmp}")
        else:
            shutil.rmtree(cls.tmp, ignore_errors=True)

    def built(self, name: str):
        p, show, built = self.results[name]
        self.assertEqual(show.code, 0, str(show))
        self.assertEqual(built.code, 0, str(built))
        return p, built

    def test_acceptance_checks_pass(self):
        for name in SCENARIOS:
            with self.subTest(scenario=name):
                _, built = self.built(name)
                self.assertIn("acceptance checks: all pass", built.out)

    def test_dry_run_writes_nothing(self):
        p, _ = self.built("trip")
        self.assertFalse((p / "build").exists())

    @unittest.expectedFailure
    def test_known_issue_loop_estimate_ignores_mixed_tiles(self):
        """Review finding 8: the cap assumes 2.2 s per item whatever the row mix; with mixed tiles off a show plays for
        about 60% of the time the owner was promised. Within 15% is the bar."""
        p, built = self.built("derived-cut-mixed-off")
        per_item = json.loads((p / "handoff" / "show.json").read_text(encoding="utf-8"))["selection"]["seconds_per_item"]
        m = re.search(r"loop \d+ px = (\d+)m(\d+)s", built.out)
        actual = int(m.group(1)) * 60 + int(m.group(2))
        promised = SCENARIOS["derived-cut-mixed-off"][0] * per_item
        self.assertLess(abs(actual - promised) / promised, 0.15, f"{actual} s played for {promised:.0f} s promised")


if __name__ == "__main__":
    unittest.main()
