# curate

The Python side: ingest, index, validate, identify, select, review sheets, handoff, apply, reconcile. Each stage is a command over the project folder described in `references/01-stages.md`, reads `project/config.toml`, and refuses to run without it.

## Status

The first run's scripts are in `legacy/`, scrubbed of anything personal but not yet runnable: their paths are placeholders (`~/photo-project`, `~/slideshow-work`) and their `PORT:` comments mark the constants that must come from the config. The port moves each one under `stages/`, wired to `common.py`, and deletes the legacy copy once the smoke test passes. Until a stage exists as a command, Claude implements it from the references before continuing, and records that in the project brief's changelog.

`common.py` is done: it finds the project folder (`--project`, `SLIDESHOW_PROJECT`, or a `config.toml` above the current directory), loads and checks the config, and provides the paths, the per-year caps pro-rated by month, the age labels for sheets, the anchors, pins and priors, plus `media_id` (SHA-256), atomic writes and the date-prefix rule. Run `python common.py` inside a project to see what the config resolves to.

## Layout

```
curate/
  common.py            config loader, project paths, shared helpers
  config.example.toml  copy to <project>/config.toml; the intake fills it
  requirements.txt     pinned dependencies (Day 2)
  setup.py             creates the environment, installs, fetches models, reports versions (Day 2)
  stages/              one module per stage (Day 2)
  legacy/              the first run's scripts, scrubbed, kept until each is ported
  models/              downloaded by setup; see models/README.md for licenses
```

## Legacy scripts by stage

| Stage | Scripts |
|---|---|
| ingest | `flatten.py` |
| index | `scan.py`, `scan_new.py`, `exif_now.py`, `orient.py`, `burst.py`, `rename.py`, `gps.py`, `inventory.py` |
| identify (presence only) | `persons.py` |
| select | `selects.py` (v1), `select_v2.py`, `select_v3.py`, `select_v4.py`, `features.py`, `feat_alts.py`, `feat_swap.py`, `feat_sheet.py` |
| review | `sheets.py` to `sheets_v4.py`, `repl_pools.py`, `repl_sheets.py`, `repl2_pools.py`, `repl2_sheets.py` |
| handoff | `handoff_copy.py`, `build_csvs.py`, `copy_v2.py` to `copy_v4.py` |
| Takeout | `tk_index.py`, `tk_phash.py`, `tk_motion.py`, `tk_score.py`, `tk_seat.py`, `tk_sheets.py`, `tk_integrate.py`, `tk_csv.py`, `tk_sync.py` |

Things the port must change, beyond the paths: the per-call time budget argument (a sandbox ceiling; drop it), the calendar-folder and filename-month priors (config, off by default), the stem-inheritance rung in `rename.py` (gate it by the witness rule in `references/03-validation-gates.md`), the Takeout sidecar lookup in `tk_index.py` (key by member path, quarantine title collisions), and EXIF orientation in `persons.py`.
