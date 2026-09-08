# build

The JavaScript side: media preparation, the sequencer, the one-file player with live and render modes, the deterministic render, the change ledger tools, the review page and the scheduler simulator. Algorithms, knobs and checks are in `references/06-layout-motion-render.md`; the ledger formats in `references/02-index-contract.md`.

## Status

Ported from the first run and wired to the project folder. Every command works on one project (the folder the intake created, holding `config.toml`), found in this order: `--project <folder>` on the command line, `SLIDESHOW_PROJECT` in the environment, or the nearest `config.toml` at or above the current directory. `SLIDESHOW_HANDOFF` and `SLIDESHOW_BUILD` override the two folders explicitly. There is no fallback into this repository: without a project every command stops with a message naming the three ways to point at one. `node lib/common.js --paths` prints what resolved.

Everything derived lands in the project's `build/` folder: `tiles/`, `clips/`, `frames/`, `prep-manifest.json`, `manifest.json`, `sequence.txt`, `player.html`, `player-review.html`, `review.html`, logs and renders. Asset paths inside the manifests are relative to that folder, which is where the player lives. `[tools] ffmpeg` and `ffprobe` in `config.toml` are honoured, then `<repo>/tools/ffmpeg/`, then the PATH.

- **HEIC without `sips`.** Still-image facts (displayed and stored dimensions, orientation, DateTimeOriginal) and JPEG conversion go through `common.imageInfo` and `common.makeJpeg`: JPEG in pure JS, `sips` on macOS as the fast path, otherwise `curate/heic.py` (pillow-heif) run with the repo's `.venv` Python. `sips` output keeps the pixels stored-rotated with the orientation tag; `heic.py` writes them upright with the tag cleared and the rest of the EXIF carried across. The tile verification accepts both.
- **Stable identity.** `media_id` (SHA-256 of the bytes) is the first column of `media.csv` and `cut-list.csv`. `add-item` computes it for every file it adds and fills it in on rows that still lack one; the column is inserted at the front if a file predates it. New rows carry `date_source` (`owner` by default, `--date-source` to override) and `date_witness` (`--witness "<sentence>"`). `changes.log` lines follow the contract's format exactly (`add`, `remove`, `cut`, padded to eight columns; a `pair` line records a plain still upgraded to a Live Photo still by a later-added companion).
- **Write-back.** `apply-replacements` copies the current `media.csv` and `changes.log` into the round folder on every run, success or stop; a dry run writes them to `<folder>/dry-run/`. The round always carries the live index home.
- **Browser.** `render` and `simsched` try Playwright's bundled Chromium first and fall back to installed Google Chrome (`channel: 'chrome'`), logging which one started. Install the bundle with `npx playwright install chromium` inside `build/`.
- **Windows.** Every command has a `bin/<name>.cmd`; `prep`, `build`, `add-item`, `frames` and `render` run under `bin/keepawake.ps1`, which holds the machine awake through `SetThreadExecutionState` for as long as the command runs (display too for `render`), the way the POSIX wrappers use `caffeinate`. `live.cmd` and `review.cmd` open the pages in Chrome. The `.cmd` files are CRLF on purpose.
- **Not yet tested on this port:** anything that needs ffmpeg or a browser (clips, frames, render, simsched, the wrap check), and the macOS `sips` and `caffeinate` paths. The pure-JS, Python and CSV paths were exercised on Windows against a synthetic project: path resolution, `prep` tiles for JPEG, PNG and HEIC, `build`, `add-item` with a HEIC swap, `apply-replacements` with write-back, `redate` dry run, and the `.cmd` wrapper with the keep-awake.

## Layout

```
build/
  package.json            Playwright pinned
  lib/                    build.js, prep.js, render.js, frames.js, add-item.js, apply-replacements.js,
                          redate.js, review.js, candidates.js, simsched.js, common.js
  bin/                    one wrapper per command, POSIX and Windows: prep build add-item apply-replacements
                          redate render frames review candidates live simsched, plus keepawake.ps1
  player.template.html    the player; build.js inlines the manifest into it to produce <project>/build/player.html
  launchers/              desktop launchers for macOS and Windows; play slideshow-x3.mp4 from beside
                          the script, ../build, a USB stick, or $SLIDESHOW_FILE
  overrides.example.json  copy to <project>/overrides.json (or build/overrides.json here, gitignored) for
                          per-item start and trim overrides
  prep-options.json       per-file preparation switches
```

Each wrapper puts an optional local toolchain (`<repo>/tools/node`, `<repo>/tools/ffmpeg`, both gitignored) on the PATH and runs the matching script in `lib/`. Usage: `bin/build --project <folder>` (or `bin\build.cmd` on Windows), and likewise for the rest.
