# tests

The regression suite. It runs the stages as a user runs them, as separate processes against a project folder, on a synthetic library it generates in a temporary folder each time, so no photo is committed and nothing in the repository is written. Standard library `unittest`, nothing to install beyond what `curate/setup.py` already put in `.venv`.

```
.venv/bin/python -m unittest discover -s tests          macOS and Linux
.venv\Scripts\python -m unittest discover -s tests      Windows
```

One file at a time: `-m unittest discover -s tests -p test_units.py`. The whole suite takes about a minute, most of it the pipeline's `setUpClass`.

## What it needs

- The repository's `.venv` (run `python curate/setup.py` first). The suite runs the stages with the Python that runs it.
- `ffmpeg` and `ffprobe` on PATH for the pipeline tests; without them `test_pipeline.py` is skipped and says so.
- Node for the build side (`prep`, `build`, `add-item`) and `test_layout.py`; without it those are skipped.
- Playwright and its Chromium for the two-second render (`setup.py` runs `npm install` in `build/` and `playwright install chromium`); without the package the render test is skipped, and without a browser that starts it is skipped and says so.

`SLIDESHOW_KEEP_TEST_DIRS=1` leaves the temporary projects behind and prints where, for a post-mortem.

## What is in it

| File | What it covers |
|---|---|
| `test_units.py` | Fast, no pipeline run. Takeout sidecar names (old and new duplicate naming, a cut-short suffix, a duplicate whose file is missing), unresolved sidecars named with a reason, the probe's return shape on a clip ffmpeg cannot decode, sharpness without OpenCV and its equality with OpenCV where OpenCV is installed, the split requirements, `setup.py` reporting detection as optional, the `changes.log` reading handoff guards itself with, and every stage importing. |
| `test_pipeline.py` | End to end on the library `fixture.py` generates (stills from five years, Live Photo pairs shot at home and away, videos, a gif, scans, and a Takeout zip carrying both duplicate namings and an orphan sidecar): `ingest` through `show`, then `prep`, `build` and a two-second render, with the accounting lines checked. Then scenarios on copies of the handed-off project: an owner's swap through `add-item` followed by `handoff` (refused, `--dry-run` refused, `--discard-changes`, and again), a change line alone, a Live Photo whose clip is truncated, and `undated_cap`. |
| `test_layout.py` | The layout engine through `bin/build --dry-run` on synthetic `media.csv` files of 469 items (the first run's mix), 409 items with mixed tiles off, and a 40-item trip; the build's own acceptance checks must pass and the dry run must write nothing. |
| `fixture.py`, `helpers.py` | The generated library and configs; running a stage, reading what it wrote. |

Each of the 2026-09-23 review's four high-severity bugs has tests that fail on 0.4.0 and pass now; search for "bug" in the files.

## Expected failures are open findings

A test marked `@unittest.expectedFailure` asserts the right behaviour for a finding that is still open, and its docstring names the finding: the Live Photo shot away from home that does not pair (5), the example config's live October anchor (6), undated files that `select --include-undated` seats and `prep` then refuses (7), and the loop estimate that ignores mixed tiles (8). They show as `expected failures` in the summary. When one is fixed its test passes, `unittest` reports an unexpected success and the run fails: take the decorator off in the same change.

## When to run it

Before and after any change to `curate/` or `build/`, and after changing a pinned version. A failing test is a finding, not a flake: the fixture is generated from fixed seeds, so the same code gives the same result on every run.
