"""Shared pieces of the regression suite: where things are, running a stage, reading what it wrote.

The stages run as the user runs them, as separate processes against a project folder: `python curate/run.py <stage>`
for the curation side and `node build/lib/<script>.js` for the build side (the `build/bin` wrappers are thin shells
over the same scripts). The project is named through SLIDESHOW_PROJECT, which both halves honour.
"""
from __future__ import annotations

import csv
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CURATE = REPO / "curate"
BUILD_LIB = REPO / "build" / "lib"
if str(CURATE) not in sys.path:
    sys.path.insert(0, str(CURATE))

# The suite runs under the repository's .venv (python curate/setup.py makes it), which is what the stages need.
PYTHON = sys.executable
KEEP = bool(os.environ.get("SLIDESHOW_KEEP_TEST_DIRS"))   # leave the temporary projects behind for a post-mortem


def have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def have_node() -> bool:
    return bool(shutil.which("node"))


def have_playwright() -> bool:
    return have_node() and (REPO / "build" / "node_modules" / "playwright" / "package.json").is_file()


class Run:
    """One command's exit code and its combined output."""

    def __init__(self, cmd: list[str], code: int, out: str):
        self.cmd, self.code, self.out = cmd, code, out

    def __str__(self) -> str:
        tail = "\n".join(self.out.strip().splitlines()[-40:])
        return f"$ {' '.join(self.cmd)}\nexit {self.code}\n{tail}"


def _run(cmd: list[str], project: Path, timeout: int) -> Run:
    env = {k: v for k, v in os.environ.items() if k not in ("SLIDESHOW_HANDOFF", "SLIDESHOW_BUILD")}
    env.update(SLIDESHOW_PROJECT=str(project), PYTHONIOENCODING="utf-8")
    p = subprocess.run(cmd, cwd=str(project), env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return Run(cmd, p.returncode, (p.stdout or "") + (p.stderr or ""))


def stage(project: Path, name: str, *args: str, timeout: int = 600, without: tuple[str, ...] = ()) -> Run:
    """python curate/run.py <name> [args] against the project. `without` names modules the stage must find missing,
    as on a machine that has no build of them (the detection packages on an Intel Mac)."""
    if not without:
        return _run([PYTHON, str(CURATE / "run.py"), name, *args], project, timeout)
    code = (f"import runpy, sys\nfor m in {list(without)!r}: sys.modules[m] = None\n"
            f"sys.argv = [{str(CURATE / 'run.py')!r}] + sys.argv[1:]\nrunpy.run_path(sys.argv[0], run_name='__main__')")
    return _run([PYTHON, "-c", code, name, *args], project, timeout)


def node(project: Path, script: str, *args: str, timeout: int = 900) -> Run:
    """node build/lib/<script>.js [args] against the project."""
    return _run(["node", str(BUILD_LIB / f"{script}.js"), *args], project, timeout)


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def by_original(items: list[dict]) -> dict[str, dict]:
    """index/items.csv rows keyed by the name the file came in with."""
    return {r["original_name"]: r for r in items}


def frame_count(video: Path) -> int:
    """Decoded frames in a video, counted by ffprobe."""
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_frames", "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    return int(out.stdout.strip() or 0)
