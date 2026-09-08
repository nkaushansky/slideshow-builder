# The nine stages

Each stage is a command over one project folder. Each is idempotent and resumable: it skips what exists, writes outputs under a temporary name and renames on completion, and prints its counts. Every stage reads the ledger and writes to it; nobody edits the index by hand. If a stage script is missing on the version you have, this file plus `04-selection-lenses.md` and `06-layout-motion-render.md` are enough to implement it.

Commands, as implemented in this repository (Windows, macOS and Linux; run from anywhere with `--project <folder>`, or from inside the project folder):

```
python curate/setup.py --project <folder>          Step 0: environment, dependencies, models, tool report
python curate/run.py ingest    [--dry-run]
python curate/run.py index     [--dry-run]
python curate/run.py validate  [--list | --resolve <media_id> <gate> --by "<witness>"]
python curate/run.py identify
python curate/run.py select    [--lens v1|v2|v3|v4] [--dry-run]
python curate/run.py sheets    [--with-drops] [--featured] [--alternates <year>] [--replacements <flags.txt>]
python curate/run.py handoff   [--dry-run]
build/bin/prep  build/bin/build  build/bin/live  build/bin/apply-replacements <round>  build/bin/render  (.cmd on Windows)
```

Project folder layout:

```
project/
  intake.md  config.toml  BRIEF.md  hours.md
  sources/          the export as received (read-only; may be a symlink or a path in config)
  work/             flat working copy, one file per source file, plus quarantine subfolders
  index/            items.csv, flags.csv, people.csv, selection.csv, sheets/
  handoff/          media/  media.csv  features.txt  cut-list.csv  inventory.md  HANDOFF.md  changes.log
  build/            tiles/ clips/ frames/ player.html sequence.txt manifest.json logs/ render output
```

## Step 0: environment check

Before ingest. Detect and report: OS and version, chip, memory, free disk; Python, Node, ffmpeg, ffprobe, Chrome, VLC with versions and paths; Playwright's ability to launch a browser (bundled Chromium, else installed Chrome via `channel: 'chrome'`); whether the working folder is on a synced drive. Pin versions in the brief. Known-good on the first run: Python 3.11+, Node 24 LTS, ffmpeg 7 or newer static build, Playwright 1.6x driving installed Chrome, VLC 3.x. Older macOS releases may refuse Homebrew and Playwright's own Chromium; the fallbacks are a static ffmpeg build, the official Node tarball, and Chrome via channel. Two web searches to confirm current versions for the detected OS are worth it; the first run skipped them and paid with a day.

Also measure two things that shape the render: the cost of a browser screenshot at the output resolution (if it is hundreds of milliseconds, the canvas pipeline in `06-layout-motion-render.md` is required, not optional) and the machine's idle-sleep setting (a one-minute idle sleep killed a preparation run on the first run; wrap long runs in the OS's keep-awake tool).

## 1. ingest

Input: the sources. Output: `work/` flat, `index/ingest.csv` with one row per file.
- Copy, never move. Sources stay untouched for the life of the project.
- Flatten into one folder. On basename collision, prefix with the source path chain, never a sequence number, so origin stays readable.
- For Takeout: index the JSON sidecars **inside the zips** first, before extracting anything. Thousands of sidecars index in seconds. Extract only what later stages need.
- Hash every file (SHA-256) and assign a stable `media_id` from the hash. IDs survive renames; filenames do not.
- Verify by flags: after every copy pass, compare the folder to the CSV byte for byte and write the result into the CSV. When a copy dies mid-run, this is what makes the rerun safe.
- Resumable in chunks with size verification. Preserve modification times, but never trust them as dates.

Benchmarks from the first run: 2,080 files flattened in about 20 minutes over a slow mount; 10,422 Takeout sidecars indexed in 5 seconds; 9,980 Takeout stills perceptually hashed in 44 minutes on two cores (a few minutes on a real machine).

## 2. index

Input: `work/`. Output: `index/items.csv`, one row per file, with the columns in `02-index-contract.md`.
- **Dates, in this order of trust:** Takeout `photoTakenTime` or other sidecar time; EXIF `DateTimeOriginal`; video container creation time (note UTC versus local; two timestamps a day apart are common); owner-declared priors about folders or filenames (a "2024 calendar" folder holding photos from 2023, a month encoded in a name), applied only as a prior and validated against files that also have EXIF; content match to a dated file with the method and distance recorded; visual estimate, flagged. Never file modification time.
- Record `precision` (day, month, year), `confidence` (a letter grade by rung) and `evidence` (a sentence naming the witness). A settled date that disagrees with intact EXIF must cite the witness that overrode it.
- **Dimensions after EXIF orientation.** Many stills are stored rotated with an orientation tag; the layout needs displayed width and height.
- Duration, codec, audio presence, frame rate for videos; flag 10-bit HDR (HLG or PQ) and high frame rate (slow motion) files, because both need special handling in the build.
- **Perceptual hash** (256-bit) and **sharpness** (Laplacian variance) for every still.
- **Live Photo pairing:** same stem, one image plus one video, validated by the pair gate in `03-validation-gates.md`. Record `companion` symmetrically.
- **Bursts:** perceptual distance at most 12 within a 3-second window; keep the sharpest or largest, park the rest in `work/_burst-duplicates/`, never delete. **Exact duplicates** by hash: keep one.
- **GPS:** from sidecars or EXIF, including QuickTime location; cluster by day for trips and recurring places.
- Rename working copies with a `YYYY-MM-DD_` prefix, zero-filled for unknown parts, so the date travels with the file; the CSV, not the name, remains the record.

## 3. validate

Input: `items.csv`. Output: `index/flags.csv`. Runs the gates in `03-validation-gates.md` and writes one row per finding with severity and the evidence. It never rewrites a date or a pairing. The owner resolves flags through the review stage or by declaring a witness, and each resolution is a dated changelog line.

## 4. identify

Input: `items.csv`, seed photos, export people tags. Output: `index/people.csv`: per file, which family members are present, the largest face share, person count, person-area share, group size.
- Face embeddings (an ArcFace-class model through onnxruntime) seeded from the owner's 5 to 20 photos per person; a match threshold tuned on the seeds; the export's people tags as a second witness where they exist.
- A "family present" flag per file. The selection uses it as a gate or a heavy weight, per the intake. The sheets print who the detector thinks is present so the reviewer knows what to check.
- Person detection for presence and person-area (any small ONNX person detector) and face detection for counts. Note the license of any model you ship; see `curate/models/README.md`.

## 5. select

Input: `items.csv`, `people.csv`, `flags.csv`, `config.toml`. Output: `index/selection.csv` (selected, lens ranks, featured, pins, tradition tags), `index/cut-list.csv` with one-word reasons.
- Build the candidate pool from the scope or theme: date range, people, places, albums, tags.
- Apply the cap: moments per period, pro-rated for partial periods; a Live Photo pair costs one slot; candidates must pass the people or family gate; no pick within perceptual distance 26 of an already seated pick; a bucket with no dissimilar candidate is left short rather than forced.
- Run the four lenses and the consensus pass from `04-selection-lenses.md`. Seat owner pins first, then tradition anchors, then one motion item per month, then the rest.
- Choose featured picks: about one in six of the stills, criteria in the lenses reference.
- Reasons for every cut: over-cap, no-people (or no-family), undated, superseded, burst, duplicate, flagged.

## 6. review (owner checkpoint 1)

Numbered contact sheets of the proposed cut, one per period, drops grayed below a line, candidates numbered; the owner approves or edits by number. Alternates per period on request. Details in `05-review-loop.md`. Target: about 15 sheets for a whole-life show, an hour of the owner's time.

## 7. handoff

Freeze the set as the contract in `02-index-contract.md`: `handoff/media/` with byte-identical copies, `media.csv`, `features.txt`, `cut-list.csv`, `inventory.md`, `HANDOFF.md`, and an empty `changes.log`. Verify: file count and byte total; every companion exists; every featured line is a still; kept rows plus cut rows equal files accounted for, every file exactly once. Print the invariant. `HANDOFF.md` must not contain any mechanism that was not demonstrated; uncertainties are listed as uncertainties.

## 8. build (owner checkpoint 2)

Prepare tiles and clips, generate the sequence and rows, open the live player, run one review round, apply flags through the ledger. Algorithms and knobs in `06-layout-motion-render.md`; the review loop in `05-review-loop.md`. On the first run, preparation of about 470 items took about an hour of machine time (tiles, H.264 clips with HDR tone-mapping, slow-motion handling), and a swap applied through the ledger took seconds.

## 9. render (owner checkpoint 3)

Test render of 60 seconds; window renders around every special case; full render of exactly one loop with the wrap proved identical; concatenate three copies so the player's own seam lands rarely; soak in the playback app; the launcher; a backup copy; the owner's full watch. Then the runbook. Benchmarks: a 15-minute loop at 2560×1440, 60 fps took about 100 minutes on 2017-era hardware; the soak was two hours.

## The ledger, across all stages

`handoff/changes.log` is append-only. The apply tool (add, replace, drop, redate) is the only way the set changes after handoff; it moves removed files to `handoff/_removed/`, updates the cut list with a reason, regenerates `media.csv`, and runs preparation for the changed items. Stable IDs mean a rename is never a new item. If curation and build ever run on different machines, the change log and the regenerated index travel back with every round; on the first run they did not, and the curation records went stale the same day.
