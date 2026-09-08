# Changelog

## 0.1.0, 2026-09-08

First shareable version. The whole path ran on Windows against a 50-file sample of a real library: intake answered as a test user, Step 0 through `curate/setup.py` (which fetched a static ffmpeg and the two models), then ingest, index, validate, identify, select, sheets, handoff, `prep`, `build`, an `add-item` round through the ledger, and a 60-second render at 2560x1440, 60 fps, through Playwright's bundled Chromium. The sample covered HEIC, three Live Photo pairs, a 240 fps clip, a 62-second video, a 10-bit HDR clip (synthetic), a GIF, a burst, an exact duplicate, calendar-folder prints and a webp.

Changed by the smoke test: the Live Photo pair gate now compares the still with frames sampled across the clip on a 64-bit perceptual hash (real pairs sit at 8 to 10 bits, unrelated frames at 22 or more; the first frame alone and the 256-bit hash both failed real pairs), and records the frame count and correlation in the witness; unsupported extensions are cut with reason `unsupported`; the Python side finds the repository's `tools/ffmpeg` without config edits; the setup download progress is quiet when not on a terminal. The first run's legacy scripts are deleted; every stage is now its own module.

Not exercised on this version: macOS (the `sips` fast path, `caffeinate`, the `.command` launchers, Chrome by its macOS path in `bin/live` and `bin/review`), Linux, Takeout zips on real data (fabricated zips only), the family gate (identity is the next milestone), the full-loop render and soak (the 60-second test and the wrap probe ran), and the fresh-session intake, which the owner should try once by cloning and saying "Let's build a slideshow from my photos".

## 0.0.3, 2026-09-08

The stages are real. `curate/run.py <stage>` runs `ingest`, `index`, `validate`, `identify`, `select`, `sheets` and `handoff` under `curate/stages/`, each wired to `common.py`, resumable, dry-runnable, printing its counts and refusing to write when its accounting does not balance. New in the port: the validate stage from `references/03` (stem-join witness, era plausibility, prefix-versus-metadata witness, Live Photo pair gate, Takeout title collisions, provisional owner dates); Takeout sidecars indexed inside the zips and keyed by member path; `media_id` (SHA-256) as the identity from ingest to the build ledger; HEIC handled in Python (`curate/heic.py`, pillow-heif) with `sips` kept as the macOS fast path; `curate/setup.py` (venv, pinned `requirements.txt`, YuNet and YOLOv8n fetched and exported at setup with a license manifest, toolchain report, optional Windows ffmpeg fetch).

Build side: every command resolves the project folder (`--project`, `SLIDESHOW_PROJECT`, or the nearest `config.toml`) and never writes into the repository; `add-item` computes `media_id` and writes contract-format `changes.log` lines; `apply-replacements` writes `media.csv` and `changes.log` back into the round folder on every run; Windows `.cmd` wrappers with a `SetThreadExecutionState` keep-awake; Playwright's bundled Chromium tried before installed Chrome.

Tested on Windows with synthetic media only: all seven stages end to end, then `prep` and `build` on the handoff. Untested: ffmpeg paths, detection on real photos, macOS. The legacy scripts stay in `curate/legacy/` until the smoke test passes.

## 0.0.2, 2026-09-08

Code copied in and scrubbed. The first run's 40 curation scripts are in `curate/legacy/`, and the build side (11 library scripts, the player template, 11 wrappers, three launchers, `prep-options.json`, a blank `overrides.example.json`, `package.json` with Playwright pinned) is in `build/`. Every personal identifier is gone: names, the event, machine names, home paths, first-run photo filenames, tradition places and their coordinates, birth-year constants. Where a script hard-coded a decision from the first run (swap lists, replacement slots, anchors, caps), it now reads a small JSON input or a named constant marked `PORT:`.

New: `curate/common.py` (config loader, project paths, per-year caps pro-rated by month, age labels, anchors, pins, priors, `media_id`, atomic writes) and `curate/config.example.toml` (the file the intake fills; the owner-declared calendar-folder and filename-month priors are in it and off by default). Wrappers run `lib/` beside them; launchers find the rendered file beside the script, in `../build`, on a USB stick or from `SLIDESHOW_FILE`. Build-side environment variables are `SLIDESHOW_HANDOFF` and `SLIDESHOW_BUILD`.

Not yet: the legacy scripts still carry placeholder paths and are not runnable; the build side still assumes macOS for HEIC and keep-awake; no stage commands, no `requirements.txt`, no setup script. Those are the next two days.

## 0.0.1, 2026-09-08

Seed. The skill text (`.claude/skills/slideshow-builder/SKILL.md`), the operator brief (`CLAUDE.md`), the nine references, the README, the folder layout, and the MIT license. Model policy: YOLOv8n fetched at setup by default, never committed; any ONNX detector may be supplied through the project config. Scripts not yet ported; the references are complete enough to implement any stage. Not yet shared.
