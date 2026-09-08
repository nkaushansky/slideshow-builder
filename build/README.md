# build

The JavaScript side: media preparation, the sequencer, the one-file player with live and render modes, the deterministic render, the change ledger tools, the review page and the scheduler simulator. Algorithms, knobs and checks are in `references/06-layout-motion-render.md`; the ledger formats in `references/02-index-contract.md`.

## Status

The first run's scripts are here, scrubbed and with the wrappers repointed at `lib/`. They ran on macOS and are not yet portable:

- `lib/common.js` resolves the handoff and build folders relative to the repository root (`slideshow-handoff/` and `build/`) unless `SLIDESHOW_HANDOFF` and `SLIDESHOW_BUILD` are set. Until it reads the project folder from `config.toml`, set both variables before running anything, or the build will write into this code folder.
- HEIC conversion and stored-dimension probing call `sips` (macOS only). The port moves HEIC to JPEG onto the Python side with `pillow-heif` and keeps `sips` as an optional fast path.
- The wrappers in `bin/` are POSIX shell and use `caffeinate` when present. A Windows form with a `powercfg` keep-awake is planned.
- `render.js` and `simsched.js` launch Chrome through Playwright's `channel: 'chrome'`; that stays as the fallback when Playwright's bundled Chromium is unavailable.
- `bin/live` and `bin/review` open Google Chrome by its macOS path.

## Layout

```
build/
  package.json            Playwright pinned
  lib/                    build.js, prep.js, render.js, frames.js, add-item.js, apply-replacements.js,
                          redate.js, review.js, candidates.js, simsched.js, common.js
  bin/                    one wrapper per command: prep build add-item apply-replacements redate render
                          frames review candidates live simsched
  player.template.html    the player; build.js inlines the manifest into it to produce player.html
  launchers/              desktop launchers for macOS and Windows; play slideshow-x3.mp4 from beside
                          the script, ../build, a USB stick, or $SLIDESHOW_FILE
  overrides.example.json  copy to overrides.json (gitignored) for per-item start and trim overrides
  prep-options.json       per-file preparation switches
```

Each wrapper puts an optional project-local toolchain (`tools/node/bin`, `tools/ffmpeg`, both gitignored) on the PATH and runs the matching script in `lib/`.
