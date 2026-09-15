# The nine stages

Each stage is a command over one project folder. Each is idempotent and resumable: it skips what exists, writes outputs under a temporary name and renames on completion, and prints its counts. Every stage reads the ledger and writes to it; nobody edits the index by hand. If a stage script is missing on the version you have, this file plus `04-selection-lenses.md` and `06-layout-motion-render.md` are enough to implement it.

Commands, as implemented in this repository (Windows, macOS and Linux; run from anywhere with `--project <folder>`, or from inside the project folder):

```
python curate/setup.py --project <folder> --apply  Step 0: environment, dependencies, models, tool report; writes the
                                                   detected timezone and display resolution into config.toml
python curate/run.py ingest    [--dry-run]
python curate/run.py index     [--dry-run]
python curate/run.py validate  [--list | --resolve <media_id> <gate> --by "<witness>"]
python curate/run.py identify  [--tags-only] [--force]
python curate/run.py select    [--lens v1|v2|v3|v4] [--dry-run]
python curate/run.py sheets    [--with-drops] [--featured] [--alternates <year>] [--replacements <flags.txt>] [--pdf]
python curate/run.py handoff   [--dry-run]
python curate/run.py show      [--dry-run]        handoff/show.json from config.toml, alone, after a config change
build/bin/prep [--force] [--only <file>]... [--tiles-only|--clips-only|--audio-only] [--verify-only]
build/bin/build  build/bin/live  build/bin/apply-replacements <round>  (.cmd on Windows)
build/bin/render [--seconds N] [--from <seconds>] [--labels] [--concat]
build/launchers/start-slideshow*.command|.bat      VLC on the display machine (plain and USB-stick editions);
                                                   start-slideshow-browser.* opens the live player in Chrome kiosk mode
```

Project folder layout:

```
project/
  intake.md  config.toml  BRIEF.md  hours.md
  sources/          the export as received (read-only; may be a symlink or a path in config)
  work/             flat working copy, one file per source file, plus quarantine subfolders
  index/            ingest.csv, takeout-sidecars.csv, items.csv, flags.csv, people.csv, selection.csv, sheets/
  handoff/          media/  media.csv  features.txt  cut-list.csv  inventory.md  HANDOFF.md  changes.log  show.json
  build/            tiles/ clips/ frames/ audio/ player.html sequence.txt manifest.json logs/ render output
```

## Step 0: environment check

Before ingest. `python curate/setup.py --project <folder> --apply` detects and reports: OS and version, chip, memory, free disk; Python, Node, ffmpeg, ffprobe, Chrome, VLC with versions and paths; the Playwright package in `build/` (version) and the browser the render will try first (`[tools] chrome` when set and present, else Playwright's bundled Chromium, else installed Chrome via `channel: 'chrome'`, resolved at render time, not launched at Step 0); whether the working folder is on a synced drive; the machine's timezone (tzlocal, then `TZ`, `/etc/localtime`, `/etc/timezone`) and the logical resolution of its display (`GetSystemMetrics` on Windows, `system_profiler` on macOS, `xrandr` on Linux). With `--apply` the detected timezone, display resolution and build OS are written into `config.toml` where the intake left them blank (`[project] timezone` when missing, blank or `UTC`; `[output] resolution`; `[machines] build_os`); an answer already in the config stands, and without `--apply` the lines to paste are printed. Ask for what it could not detect; the display machine's resolution is the intake's answer whenever it is not the build machine. The report also lands in `project/environment.md`. Pin versions in the brief. Known-good on the first run: Python 3.11+, Node 24 LTS, ffmpeg 7 or newer static build, Playwright 1.6x driving installed Chrome, VLC 3.x. Older macOS releases may refuse Homebrew and Playwright's own Chromium; the fallbacks are a static ffmpeg build, the official Node tarball, and Chrome via channel. Two web searches to confirm current versions for the detected OS are worth it; the first run skipped them and paid with a day.

Also measure two things that shape the render: the cost of a browser screenshot at the output resolution (if it is hundreds of milliseconds, the canvas pipeline in `06-layout-motion-render.md` is required, not optional) and the machine's idle-sleep setting (a one-minute idle sleep killed a preparation run on the first run; wrap long runs in the OS's keep-awake tool).

## 1. ingest

Input: the sources. Output: `work/` flat, `index/ingest.csv` with one row per file.
- Copy, never move. Sources stay untouched for the life of the project.
- Accepted file types: stills `.jpg .jpeg .heic .heif .png .webp`; videos `.mov .mp4 .m4v .avi .mkv .mts .m2ts .3gp .webm .wmv .mpg .mpeg`; animated `.gif`. Anything else is cut with reason `unsupported` at select, so it stays in the accounting instead of reaching the build.
- Flatten into one folder. On basename collision, prefix with the source path chain, never a sequence number, so origin stays readable.
- For Takeout: index the JSON sidecars **inside the zips** first, before extracting anything. Thousands of sidecars index in seconds. Extract only what later stages need.
- For folder sources (a folder tree, an Apple Photos export, an iCloud download, an unzipped Takeout): the sidecars beside the files are indexed into the same `index/takeout-sidecars.csv` and never copied as media. That is `.json` files that parse as a Takeout sidecar (a `photoTakenTime`), `.xmp` files (capture time, GPS, the names of people, a description; a malformed one is counted and skipped, never fatal) and `.aae` files (left out of the copy, nothing read). Each row names its kind in a `source` column and its media file the way the zip case does, so the index looks both up alike; a `.json` that is not a sidecar is copied as before and cut as `unsupported`.
- Hash every file (SHA-256) and assign a stable `media_id` from the hash. IDs survive renames; filenames do not.
- Verify by flags: after every copy pass, compare the folder to the CSV byte for byte and write the result into the CSV. When a copy dies mid-run, this is what makes the rerun safe.
- Resumable in chunks with size verification. Preserve modification times, but never trust them as dates.

Benchmarks from the first run: 2,080 files flattened in about 20 minutes over a slow mount; 10,422 Takeout sidecars indexed in 5 seconds; 9,980 Takeout stills perceptually hashed in 44 minutes on two cores (a few minutes on a real machine).

## 2. index

Input: `work/`. Output: `index/items.csv`, one row per file, with the columns in `02-index-contract.md`.
- **Dates, in this order of trust:** sidecar time (Takeout `photoTakenTime`; XMP `photoshop:DateCreated`, else `xmp:CreateDate`, else `exif:DateTimeOriginal`, the project timezone applied when the value carries no offset), inside a zip or beside the file alike; EXIF `DateTimeOriginal`; video container creation time (note UTC versus local; two timestamps a day apart are common); owner-declared priors about folders or filenames (`[priors]`: a "2024 calendar" folder holding photos from 2023, a month encoded in a name, and with `folder_year_rule` a four-digit year in the nearest folder's name, precision year, in that order), applied only as a prior and validated against files that also have EXIF; content match to a dated file with the method and distance recorded; visual estimate, flagged. Never file modification time.
- Record `precision` (day, month, year), `date_source` (the rung that settled it: sidecar, exif, container, prior, pair, owner) and `date_witness` (a sentence naming the witness). A settled date that disagrees with intact EXIF must cite the witness that overrode it.
- **Dimensions after EXIF orientation.** Many stills are stored rotated with an orientation tag; the layout needs displayed width and height.
- Duration, codec, audio presence, frame rate for videos; flag 10-bit HDR (HLG or PQ) and high frame rate (slow motion) files, because both need special handling in the build.
- **Perceptual hash** (256-bit) and **sharpness** (Laplacian variance) for every still.
- **Live Photo pairing:** same stem, one image plus one video, validated by the pair gate in `03-validation-gates.md`. Record `companion` symmetrically.
- **Bursts:** perceptual distance at most 12 within a 3-second window; keep the sharpest or largest, park the rest in `work/_burst-duplicates/`, never delete. **Exact duplicates** by hash: keep one.
- **GPS:** from sidecars or EXIF, including QuickTime location; cluster by day for trips and recurring places.
- **People tags** from the sidecar (Takeout `people[].name`; XMP `PersonInImage`, else the region names) into `people_tags`, semicolon-separated, for the identify stage.
- Rename working copies with a `YYYY-MM-DD_` prefix, zero-filled for unknown parts, so the date travels with the file; the CSV, not the name, remains the record.

## 3. validate

Input: `items.csv`. Output: `index/flags.csv`. Runs the gates in `03-validation-gates.md` and writes one row per finding with severity and the evidence. It never rewrites a date or a pairing. The owner resolves flags through the review stage or by declaring a witness, and each resolution is a dated changelog line.

## 4. identify

Input: `items.csv`, seed photos, export people tags. Output: `index/people.csv`: per file, which family members are present, the largest face share, person count, person-area share, group size.
- The export's people tags (`people_tags` in `items.csv`) matched against `[family] names`: a tag matches a name when they are equal case-insensitively, or when the one-word config name equals the tag's first word. `--tags-only` runs this without the detection models: `persons` and `faces` stay blank, `people` holds the matched names and `family_present` is `yes` when a tag matches, `no` when the file has tags and none matches, blank when it has none. The detection run fills the same two columns the same way. Rows already in `people.csv` are skipped unless `--force`. The stage prints how many rows got tags and how many are family. A tags-only `people.csv` serves the `family` gate only: under `gate = "people"` select stops and names the detection run and the other gates, because it would have nothing to check and would pass every candidate; the v4 person-area and group weights score every candidate alike, and the sheets print `people ?`.
- Face embeddings (an ArcFace-class model through onnxruntime) seeded from the owner's 5 to 20 photos per person, with a match threshold tuned on the seeds, are the later milestone; `[family] seed_photos` is recorded for it and nothing reads it yet.
- A "family present" flag per file. The selection uses it as a gate or a heavy weight, per the intake. The sheets print who the detector thinks is present and the matched names, so the reviewer knows what to check.
- Person detection for presence and person-area (any small ONNX person detector) and face detection for counts. Note the license of any model you ship; see `curate/models/README.md`.

## 5. select

Input: `items.csv`, `people.csv`, `flags.csv`, `config.toml`. Output: `index/selection.csv` (selected, lens ranks, featured, pins, tradition tags), `index/cut-list.csv` with one-word reasons.
- Build the candidate pool from the scope or theme: the date range (`[show] scope_start` and `scope_end`, else `first_year` and `last_year`, else the birth year and the event year), people, places, albums, tags. The types the taste leaves out are cut too: `[taste] include_videos = false` cuts every video, `include_gifs = false` every GIF, `live_photos = "still"` every Live Photo clip, all with reason `excluded-type`; a Live Photo whose clip is cut competes as a plain still.
- The owner's off-limits list (`[show] off_limits`: filenames, media ids, or a file or folder path) is applied before any other test; a match is cut with reason `off-limits`, and a Live Photo pair goes together.
- Apply the cap: `[selection] cap_per_year`, or, when it is 0 or missing, a cap derived from `[show] loop_minutes_target` and the tile size (`04-selection-lenses.md`); pro-rated for the partial first and last years from the scope dates' months (else the birth month and the event month); `[selection.cap_overrides]` replaces single years' caps last; a Live Photo pair costs one slot; candidates must pass the people gate (`[family] gate`: `none` skips the check, `people` wants any person in frame, `family` wants one of the named people); no pick within perceptual distance 26 of an already seated pick; a bucket with no dissimilar candidate is left short rather than forced. The stage prints which gate ran and one cap line with the arithmetic: `cap: derived 21 per year from a 15-minute target at 2.2 s per item (medium tiles, 100 px/s): 409 moments over 19.5 year-shares`, or `cap: 33 per year from config`.
- Run the four lenses and the consensus pass from `04-selection-lenses.md`, the v4 weights from `[selection.weights]`. Seat owner pins first (`[pins] files` and `[show] must_include`, matched by media id, by the dated filename or by the original name; a miss is a warning), then tradition anchors, then one motion item per month, then the rest.
- Choose featured picks: about one in six of the stills, criteria in the lenses reference and thresholds in `[selection.featured]`; `[taste] mixed_tiles = false` sets the fraction to 0, so there are none, and the stage says so.
- Reasons for every cut: off-limits, excluded-type, over-cap, no-people (or no-family), undated, unsupported, superseded, burst, duplicate, flagged. Print the count per reason (`excluded-type N` when N is above 0), the off-limits count, the number of pins seated, and a rough loop estimate at the cap plan's seconds per item.

## 6. review (owner checkpoint 1)

Numbered contact sheets of the proposed cut, one per period, drops grayed below a line, candidates numbered; the owner approves or edits by number. Alternates per period on request. `--pdf` bundles every sheet into `index/sheets/contact-sheets.pdf`, one page per sheet (years ascending, then featured, alternates, replacements), for an owner who is not at the machine; `--pdf` alone re-bundles the sheets already on disk. Details in `05-review-loop.md`. Target: about 15 sheets for a whole-life show, an hour of the owner's time.

## 7. handoff

Freeze the set as the contract in `02-index-contract.md`: `handoff/media/` with byte-identical copies, `media.csv`, `features.txt`, `cut-list.csv`, `inventory.md`, `HANDOFF.md`, an empty `changes.log`, and `show.json`. Verify: file count and byte total; every companion exists; every featured line is a still; kept rows plus cut rows equal files accounted for, every file exactly once. Print the invariant. With `[taste] live_photos = "still"`, a `livephoto-still` whose clip was cut is written as `type = still` with no companion; the count is logged and named in `HANDOFF.md`, and the companion check skips those rows. `HANDOFF.md` must not contain any mechanism that was not demonstrated; uncertainties are listed as uncertainties.

### `show`, the settings file

`python curate/run.py show` writes `handoff/show.json` on its own: the display and taste settings the build reads (resolution, frame rate, row heights, gutter, scroll speed, background, concat copies, quality preset, the order, the moving-tile caps from the motion density, the type switches, the Live Photo and slow-motion modes, the seed) derived from `[output]` and `[taste]` in `config.toml`, the music from `[audio]` with every file resolved to an absolute path and checked, the cap plan under `selection` for the record, plus `[show] off_limits` resolved to media ids and filenames so the apply tool can refuse them. Every number is derived in Python; the JavaScript side only reads them. The handoff stage writes the same file, so run `show` alone after a config change to update the build side without a new handoff. It prints the derived numbers and the cap plan; `--dry-run` prints them and writes nothing; a bad value exits with the key name and what it accepts. The rules are in `02-index-contract.md`.

## 8. build (owner checkpoint 2)

Prepare tiles and clips (and, with `[audio]` enabled, the music tracks, one `build/audio/NN-<stem>.m4a` per file in play order), generate the sequence and rows, open the live player, run one review round, apply flags through the ledger. The viewport, frame rate, row heights, gutter, scroll speed, background, order, moving-tile caps and seed come from `handoff/show.json`; without it the build uses the first run's defaults (2560×1440, 60 fps, medium tiles, chapters, four moving tiles) and says so in one warning. `[taste] slow_motion` decides whether high-frame-rate clips play slow or at real time; `<project>/prep-options.json` (else the repository's `build/prep-options.json`) names the per-file exceptions, and the prep report names the mode and the exceptions. `bin/build` reports which it used. Algorithms and knobs in `06-layout-motion-render.md`; the review loop in `05-review-loop.md`. On the first run, preparation of about 470 items took about an hour of machine time (tiles, H.264 clips with HDR tone-mapping, slow-motion handling), and a swap applied through the ledger took seconds.

## 9. render (owner checkpoint 3)

Test render of 60 seconds (`--seconds 60`; add `--labels` when the owner is not at the machine, so every tile carries its filename and date and every row its number and chapter, written to a `-labels` file the launchers never pick up); window renders around every special case; full render of exactly one loop with the wrap proved identical; `--concat` writes `slideshow-x<N>.mp4`, N copies back to back (`[output] concat_copies`, default 3), so the player's own seam lands rarely; soak in the playback app; the launcher; a backup copy; the owner's full watch. Size, frame rate and the x264 preset come from `show.json` (`[output] resolution`, `fps`, `quality`). With `[audio]` enabled, the verified silent render keeps its name with `-silent` before `.mp4` (`slideshow-silent.mp4`, `test-60s-silent.mp4`), the soundtrack is muxed on under the plain name, and `--concat` joins the silent copies and lays one soundtrack over the whole file, so the music runs across the seams (`06-layout-motion-render.md`). With `[machines] player = "tv-usb"` the encoder adds the H.264 profile and level a TV stick decodes and warns about any final file of 4 GiB or over, which FAT32 sticks refuse. The launchers play the plain-named file: VLC through `start-slideshow.command` and the USB-stick pair, without muting, so a silent file plays nothing and a file with music plays it; `start-slideshow-browser.command` and `.bat` open `player.html` in Chrome kiosk mode as the fallback. Then the runbook. Benchmarks: a 15-minute loop at 2560×1440, 60 fps took about 100 minutes on 2017-era hardware; the soak was two hours.

## The ledger, across all stages

`handoff/changes.log` is append-only. The apply tool (add, replace, drop, redate) is the only way the set changes after handoff; it moves removed files to `handoff/_removed/`, updates the cut list with a reason, regenerates `media.csv`, and runs preparation for the changed items. Stable IDs mean a rename is never a new item. If curation and build ever run on different machines, the change log and the regenerated index travel back with every round; on the first run they did not, and the curation records went stale the same day.
