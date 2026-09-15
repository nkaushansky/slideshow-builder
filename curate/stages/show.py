"""show: write handoff/show.json from config.toml, the display, taste, music, selection and off-limits settings the build reads.

    python curate/run.py show [--project P] [--dry-run]

Every number the JavaScript side needs (viewport, frame rate, row heights, gutter, scroll speed,
background, concat copies, quality preset), the taste knobs (order, motion density, mixed tiles,
videos, GIFs, Live Photos, slow motion, seed), the music ([audio], every file resolved and checked)
and the cap plan ([selection] cap_per_year, or derived from [show] loop_minutes_target and the tile
size) are derived in common.py from config.toml, so the build only reads numbers; the rules are in
references/02-index-contract.md. [show] off_limits is resolved to media_ids and filenames so the
apply tool can refuse them. The handoff stage writes the same file; run this stage alone after
changing config.toml so the build side sees the change without a new handoff. A bad value exits
with the key name and what it accepts. Dry-run prints the derived values, the cap plan included,
and writes nothing.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import CONFIG_NAME, SHOW_JSON_NAME, describe_show, project, say, write_show_json  # noqa: E402


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="show", description=__doc__.split("\n\n")[0])
    ap.add_argument("--project", help="project folder (default: SLIDESHOW_PROJECT or a config.toml above the cwd)")
    ap.add_argument("--dry-run", action="store_true", help="print the derived settings, write nothing")
    a = ap.parse_args(argv)
    P = project()

    warnings: list[str] = []
    settings = P.show_settings(warnings)
    say(f"show: {P.root / CONFIG_NAME}")
    for w in warnings:
        say("  !", w)
    for line in describe_show(settings):
        say("  " + line)
    overrides = P.cap_overrides()
    if overrides:
        say("  cap overrides ([selection.cap_overrides]): " + ", ".join(f"{y} = {c}" for y, c in sorted(overrides.items())))
    path = P.handoff / SHOW_JSON_NAME
    if a.dry_run:
        say(f"show: dry run; would write {path}")
        return 0
    write_show_json(P, settings)
    say(f"show: wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
