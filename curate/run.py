"""Run one curation stage against a project folder.

    python curate/run.py <stage> [--project <folder>] [--dry-run] [stage options]
    python curate/run.py list

Stages live in curate/stages/<stage>.py and each exposes ``main(argv) -> int``. Every stage
reads <project>/config.toml through common.py and refuses to run without it. Mutating stages
honour --dry-run: they print the plan and write nothing. Each prints its counts on success and
exits non-zero on failure; nothing is retried silently.

A stage runs with the Python in <repo>/.venv, the one `python curate/setup.py` installs the
pinned packages into: whichever interpreter you start this with, it re-runs itself there. Set
SLIDESHOW_VENV when setup was given a --venv elsewhere. While a stage runs, the machine is held
awake, because index and identify can outlast a sleep timer.
"""
from __future__ import annotations

import contextlib
import importlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

WIN = sys.platform.startswith("win")
MAC = sys.platform == "darwin"

# Where setup.py puts the environment, spelled the same way it spells it. SLIDESHOW_VENV overrides the
# place, for a machine where setup ran with --venv somewhere else.
VENV = os.path.abspath(os.path.expanduser(os.environ.get("SLIDESHOW_VENV") or os.path.join(REPO, ".venv")))
VENV_PYTHON = os.path.join(VENV, "Scripts", "python.exe") if WIN else os.path.join(VENV, "bin", "python")
REEXEC = "SLIDESHOW_REEXEC"     # set in the child: this is the second time round, so never re-run again

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

STAGES = {
    "ingest": "copy sources into work/, hash, index Takeout sidecars inside the zips",
    "index": "dates, dimensions after orientation, hashes, sharpness, pairs, bursts, duplicates, GPS -> index/items.csv",
    "validate": "the gates in references/03 -> index/flags.csv (never rewrites a value)",
    "identify": "person and face presence per file -> index/people.csv",
    "select": "the four lenses, consensus, featured picks -> index/selection.csv, index/cut-list.csv",
    "sheets": "numbered contact sheets of the proposed cut, replacement pools -> index/sheets/",
    "handoff": "freeze the set as the index contract -> handoff/",
    "show": "write handoff/show.json from config.toml (display, taste and off-limits settings for the build side)",
}


def in_venv() -> bool:
    """True when the interpreter running us is the one setup.py installed the packages into.

    sys.prefix is the root of the environment in use, so this compares two folders instead of the
    many spellings of one executable (a symlink, a relative path, python against python3)."""
    try:
        return os.path.realpath(sys.prefix) == os.path.realpath(VENV)
    except OSError:
        return False


def use_venv(argv: list[str]) -> None:
    """Re-run this script with the venv's Python, so a stage finds Pillow, numpy and OpenCV.

    Every document says "python curate/run.py <stage>", and with the system Python that used to
    mean a raw ModuleNotFoundError from index. A missing environment is not a refusal, though:
    ingest --dry-run and show are standard library only, so this warns once and carries on.

    The child is marked, because a folder can hold bin/python and still not be an environment: with
    pyvenv.cfg missing or unreadable sys.prefix stays the system prefix, in_venv() is false however
    often we re-run, and without the mark this would exec itself forever."""
    if in_venv():
        return
    if not os.path.isfile(VENV_PYTHON):
        print(f"run.py: the environment `python curate/setup.py` creates was not found at {VENV_PYTHON}; "
              f"stages that need Pillow, numpy or OpenCV will fail until it exists", file=sys.stderr)
        return
    if os.environ.get(REEXEC):
        print(f"run.py: the environment at {VENV} did not take (pyvenv.cfg missing or invalid), so its Python runs "
              f"as {sys.executable}; carrying on with this one, and a stage that needs Pillow, numpy or OpenCV may fail",
              file=sys.stderr)
        return
    cmd = [VENV_PYTHON, os.path.abspath(__file__)] + argv
    env = dict(os.environ, **{REEXEC: "1"})
    if WIN:
        # os.execv on Windows is not a real exec: the console can get its prompt back while the new
        # process is still running, and Ctrl-C stops reaching it. Waiting on a child is reliable.
        sys.exit(subprocess.call(cmd, env=env))
    os.execve(VENV_PYTHON, cmd, env)


@contextlib.contextmanager
def keep_awake():
    """Hold the machine awake for the length of a stage; index and identify outlast a sleep timer.

    Windows tells the power manager directly and takes the request back on the way out. macOS uses
    caffeinate tied to our pid, so it ends when we do however we end. Linux has no one way to ask,
    so it does nothing. None of this is worth stopping a stage over: a failure prints one line."""
    keeper = None
    if WIN:
        try:
            import ctypes
            if ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) == 0:
                raise OSError("SetThreadExecutionState refused the request")
        except Exception as e:
            print(f"run.py: could not hold the machine awake ({e}); check the sleep timer before a long stage",
                  file=sys.stderr)
    elif MAC:
        caffeinate = shutil.which("caffeinate")
        if caffeinate:
            try:
                keeper = subprocess.Popen([caffeinate, "-i", "-w", str(os.getpid())])
            except OSError as e:
                print(f"run.py: could not hold the machine awake ({e}); check the sleep timer before a long stage",
                      file=sys.stderr)
    try:
        yield
    finally:
        if WIN:
            try:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            except Exception:
                pass
        if keeper is not None and keeper.poll() is None:
            # It would go when we go, but ending it here keeps a stray caffeinate out of the way
            # when this runs inside a longer-lived shell.
            keeper.terminate()


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
    use_venv(argv)                      # from here on this is the venv's Python, or it said why not
    with keep_awake():
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
