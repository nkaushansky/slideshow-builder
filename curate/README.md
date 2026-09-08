# curate

The Python side: ingest, index, validate, identify, select, review sheets, handoff. Each stage is a command over the project folder described in `references/01-stages.md`, reads `project/config.toml`, and refuses to run without it.

## Commands

```
python curate/setup.py [--project <folder>] [--fetch-ffmpeg] [--skip-models]   once per machine
python curate/run.py <stage> [--project <folder>] [--dry-run] [--force] [options]
python curate/run.py list
```

| Stage | Reads | Writes | Options |
|---|---|---|---|
| `ingest` | the `[[sources]]` in the config | `work/`, `index/ingest.csv`, `index/takeout-sidecars.csv` | `--workers N` |
| `index` | `work/`, the sidecar index | `index/items.csv`, `index/_probe-cache.jsonl`; renames working copies with the date prefix; parks bursts and duplicates | |
| `validate` | `items.csv`, sidecars | `index/flags.csv` | `--list`, `--resolve <media_id> <gate> --by "<witness>"` |
| `identify` | `items.csv`, the models | `index/people.csv` | `--all` (include parked files), `--limit N` |
| `select` | `items.csv`, `people.csv`, `flags.csv`, the config | `index/selection.csv`, `index/cut-list.csv` | `--lens v1..v4`, `--include-undated`, `--allow-presence-gate` |
| `sheets` | the above | `index/sheets/*.jpg`, `index/sheets/index.md` | `--with-drops`, `--featured`, `--alternates <year>`, `--replacements <flags.txt>` |
| `handoff` | the above | `handoff/media/`, `media.csv`, `features.txt`, `cut-list.csv`, `inventory.md`, `HANDOFF.md`, `changes.log` | |

The project folder is found from `--project`, from `SLIDESHOW_PROJECT`, or by walking up from the current directory to a `config.toml`. `python curate/common.py` prints what a config resolves to. Every stage prints its counts and the accounting line; a stage whose accounting does not balance writes nothing and exits non-zero.

`ffmpeg` and `ffprobe` are needed for videos (duration, codec, HDR, container time, Live Photo pair verification, video thumbnails, first-frame detection). Without them the stages still run, leave the video columns blank, say so loudly, and the validate stage flags every unverified pair; set `[tools] ffmpeg` and `ffprobe` in the config, or run `setup.py --fetch-ffmpeg` on Windows, then re-run `index`.

## Layout

```
curate/
  common.py            config loader, project paths, per-year caps, age labels, anchors, pins, priors, media_id
  config.example.toml  copy to <project>/config.toml; the intake fills it
  requirements.txt     pinned dependencies (installed by setup.py into .venv)
  setup.py             creates the environment, installs, fetches models, reports versions
  run.py               runs one stage
  heic.py              HEIC/JPEG dimensions and conversion, used by the build side where sips is absent
  stages/              one module per stage, plus _probe.py, _takeout.py, _lenses.py helpers
  legacy/              the first run's scripts, scrubbed; kept until the smoke test passes, then deleted
  models/              downloaded by setup; see models/README.md for licenses
```

## Status

All seven stages ran end to end on a synthetic project on Windows (ingest through handoff, then the build side's `prep` and `build` on the resulting handoff folder). Not yet exercised: anything that needs ffmpeg, detection quality on real photos (the synthetic fixtures contain no people), the family gate (identity is a later milestone; `[family] gate = "family"` refuses to run until then unless `--allow-presence-gate` is given), and macOS. The Day 3 smoke test on a real sample covers those.

Things the port changed on purpose, beyond the paths: the per-call time budget argument is gone; the calendar-folder and filename-month priors are config, off by default; a date is never inherited from another file by stem alone; the Takeout sidecar lookup keys by member path and quarantines title collisions; the identify stage applies EXIF orientation before detection.
