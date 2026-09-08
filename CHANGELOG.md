# Changelog

## 0.0.2, 2026-09-08

Code copied in and scrubbed. The first run's 40 curation scripts are in `curate/legacy/`, and the build side (11 library scripts, the player template, 11 wrappers, three launchers, `prep-options.json`, a blank `overrides.example.json`, `package.json` with Playwright pinned) is in `build/`. Every personal identifier is gone: names, the event, machine names, home paths, first-run photo filenames, tradition places and their coordinates, birth-year constants. Where a script hard-coded a decision from the first run (swap lists, replacement slots, anchors, caps), it now reads a small JSON input or a named constant marked `PORT:`.

New: `curate/common.py` (config loader, project paths, per-year caps pro-rated by month, age labels, anchors, pins, priors, `media_id`, atomic writes) and `curate/config.example.toml` (the file the intake fills; the owner-declared calendar-folder and filename-month priors are in it and off by default). Wrappers run `lib/` beside them; launchers find the rendered file beside the script, in `../build`, on a USB stick or from `SLIDESHOW_FILE`. Build-side environment variables are `SLIDESHOW_HANDOFF` and `SLIDESHOW_BUILD`.

Not yet: the legacy scripts still carry placeholder paths and are not runnable; the build side still assumes macOS for HEIC and keep-awake; no stage commands, no `requirements.txt`, no setup script. Those are the next two days.

## 0.0.1, 2026-09-08

Seed. The skill text (`.claude/skills/slideshow-builder/SKILL.md`), the operator brief (`CLAUDE.md`), the nine references, the README, the folder layout, and the MIT license. Model policy: YOLOv8n fetched at setup by default, never committed; any ONNX detector may be supplied through the project config. Scripts not yet ported; the references are complete enough to implement any stage. Not yet shared.
