# build

The JavaScript side: media preparation, the sequencer, the one-file player with live and render modes, the deterministic render, the change ledger tools, the review page and the scheduler simulator. Algorithms, knobs and checks are in `references/06-layout-motion-render.md`; the ledger formats in `references/02-index-contract.md`.

Status: the scripts from the first run are being ported here. They ran on macOS; the port makes HEIC conversion platform-independent (done on the Python side), adds a Windows keep-awake and launcher, and pins Playwright.

Planned layout:

```
build/
  package.json          Playwright pinned
  lib/                  build.js, prep.js, render.js, frames.js, add-item.js, apply-replacements.js, redate.js, review.js, candidates.js, simsched.js, common.js
  bin/                  wrappers for each command, one per platform where needed
  player.template.html  the player
  launchers/            desktop launchers for macOS and Windows, parameterized
  overrides.example.json
  prep-options.json
```
