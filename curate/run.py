"""Run one curation stage against a project folder.

    python curate/run.py <stage> [--project <folder>] [--dry-run] [stage options]
    python curate/run.py list

Stages live in curate/stages/<stage>.py and each exposes ``main(argv) -> int``. Every stage
reads <project>/config.toml through common.py and refuses to run without it. Mutating stages
honour --dry-run: they print the plan and write nothing. Each prints its counts on success and
exits non-zero on failure; nothing is retried silently.
"""
from __future__ import annotations

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

STAGES = {
    "ingest": "copy sources into work/, hash, index Takeout sidecars inside the zips",
    "index": "dates, dimensions after orientation, hashes, sharpness, pairs, bursts, duplicates, GPS -> index/items.csv",
    "validate": "the gates in references/03 -> index/flags.csv (never rewrites a value)",
    "identify": "person and face presence per file -> index/people.csv",
    "select": "the four lenses, consensus, featured picks -> index/selection.csv, index/cut-list.csv",
    "sheets": "numbered contact sheets of the proposed cut, replacement pools -> index/sheets/",
    "handoff": "freeze the set as the index contract -> handoff/",
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        print("\nstages:")
        for k, v in STAGES.items():
            print(f"  {k:10s} {v}")
        return 0 if argv else 2
    name = argv[0]
    if name == "list":
        for k, v in STAGES.items():
            print(f"{k:10s} {v}")
        return 0
    if name not in STAGES:
        print(f"unknown stage {name!r}; one of: {', '.join(STAGES)}", file=sys.stderr)
        return 2
    try:
        mod = importlib.import_module(f"stages.{name}")
    except ModuleNotFoundError as e:
        if e.name and e.name.endswith(name):
            print(f"stage {name!r} is not implemented yet (curate/stages/{name}.py missing); "
                  f"implement it from references/01-stages.md", file=sys.stderr)
            return 3
        raise
    return int(mod.main(argv[1:]) or 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
