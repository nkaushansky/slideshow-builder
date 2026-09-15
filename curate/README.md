# curate

The Python side: ingest, index, validate, identify, select, review sheets, handoff, and `show`, the settings file for the build. Each stage is a command over the project folder described in `references/01-stages.md`, reads `project/config.toml`, and refuses to run without it.

## Commands

```
python curate/setup.py [--project <folder>] [--apply] [--skip-models] [--skip-node] [--skip-ffmpeg]   once per machine
python curate/run.py <stage> [--project <folder>] [--dry-run] [--force] [options]
python curate/run.py list
```

| Stage | Reads | Writes | Options |
|---|---|---|---|
| `ingest` | the `[[sources]]` in the config | `work/`, `index/ingest.csv`, `index/takeout-sidecars.csv` (sidecars inside Takeout zips, and the Takeout JSON and `.xmp` sidecars beside files in folder sources; an `.xmp` that reaches no file and a `.json` too large to read as a sidecar are counted and named, up to eight, with the reason) | `--workers N` |
| `index` | `work/`, the sidecar index, `[priors]` | `index/items.csv`, `index/_probe-cache.jsonl`; renames working copies with the date prefix; parks bursts and duplicates | |
| `validate` | `items.csv`, sidecars | `index/flags.csv` | `--list`, `--resolve <media_id> <gate> --by "<witness>"` |
| `identify` | `items.csv`, `[family] names`, the models | `index/people.csv` | `--tags-only` (people tags against the family names, no models), `--force`, `--all` (include parked files), `--limit N` |
| `select` | `items.csv`, `people.csv`, `flags.csv`, the config (`[family] gate`; the `[show]` scope and `loop_minutes_target`; `[selection]` with its `weights`, `featured` and `cap_overrides` tables; the `[taste]` type switches and `mixed_tiles`; `[show] off_limits` and `must_include`; `[pins]`) | `index/selection.csv`, `index/cut-list.csv` | `--lens v1..v4`, `--include-undated`, `--allow-presence-gate` |
| `sheets` | the above | `index/sheets/*.jpg`, `index/sheets/index.md`, `index/sheets/contact-sheets.pdf` | `--with-drops`, `--featured`, `--alternates <year>`, `--replacements <flags.txt>`, `--pdf` |
| `handoff` | the above | `handoff/media/`, `media.csv`, `features.txt`, `cut-list.csv`, `inventory.md`, `HANDOFF.md`, `changes.log`, `show.json` | |
| `show` | `[output]`, `[taste]`, `[show]`, `[audio]`, `[selection]`, `[machines]` in the config | `handoff/show.json` alone, after a config change | |

The project folder is found from `--project`, from `SLIDESHOW_PROJECT`, or by walking up from the current directory to a `config.toml`. `python curate/common.py` prints what a config resolves to, the derived show settings and the cap plan included. Every stage prints its counts and the accounting line; a stage whose accounting does not balance writes nothing and exits non-zero.

`setup.py --project <folder> --apply` writes what Step 0 detected (the timezone, the display's logical resolution, the build OS) into `config.toml` where it is blank; without `--apply` it prints the lines to paste. `show` derives the numbers the build reads (viewport, frame rate, row heights, gutter, scroll speed, background, concat copies, quality preset) from `[output]` and `[taste]`, prints them, and writes `handoff/show.json`; the rules are in `references/02-index-contract.md`, and a bad value exits with the key name and what it accepts. `[family] gate` is `none` (no people check), `people` (any person in frame) or `family` (one of the named people); select prints which ran. `[show] off_limits` takes filenames, media ids, or a file or folder path; select cuts a match with reason `off-limits` before any other test, and the build's `add-item` refuses it. `[show] must_include` entries are seated like `[pins] files`, with a warning for any that is not among the candidates. `sheets --pdf` bundles every sheet in `index/sheets/` into `contact-sheets.pdf`, one page per sheet, for an owner who is not at the machine; alone, it re-bundles the sheets on disk.

The scope is `[show] scope_start` and `scope_end` (dates; the first and last years' caps are pro-rated from their months), else `first_year` and `last_year`, else the honoree's birth year and the event year; none of the three is an error naming them. `[selection] cap_per_year = 0` (or missing) derives the cap from `[show] loop_minutes_target` at 2.2 seconds per item, scaled by the tile size and the scroll speed, over the year-shares in scope; a cap above 0 is used as it stands and nothing else is read for it (no `[output]`, no `[taste]`, no `loop_minutes_target`, as in 0.2), so select and sheets cannot stop on a key the cap does not depend on, `show.json` carries `null` for the three derived numbers and select's loop estimate says it has no pace to work from; select prints the plan on one line, `[selection.cap_overrides]` gives single years their own cap, and `[selection.weights]` and `[selection.featured]` hold the v4 weights and the featured thresholds. `[taste] include_videos`, `include_gifs` and `live_photos = "still"` cut those types with reason `excluded-type` (a Live Photo whose clip is cut competes as a plain still and is handed off as one); `mixed_tiles = false` makes no featured picks. `[audio]` (`enabled`, `files` in play order, `loop`, `crossfade_s`, `fade_s`, `volume`) is checked by `show`: every file must carry a music extension, and with `enabled = true` must exist (a missing file with `enabled = false` is a warning); `enabled` with no files, or the 0.1 key `[show] audio = true` without the section, is an error. `identify --tags-only` fills `people` and `family_present` from the sidecars' `people_tags` against `[family] names` without the detection models (a tag matches a name when equal case-insensitively, or when a one-word name equals the tag's first word); it serves the `family` gate, and select refuses `gate = "people"` on such a `people.csv` because it would have no person counts to check. When no file in `items.csv` carries a people tag at all, `--tags-only` says so loudly (the export has none, or the index predates the `people_tags` column and must be re-run) because every row it writes then leaves `family_present` blank; when every row is already in `people.csv` and still blank it names `--force`. Select's refusal of the family gate names the same remedy, and says instead when `family_present` is answered everywhere but no row says `yes`. `[priors] folder_year_rule` dates a file no better rung could to a four-digit year in its folder's name, precision year, witness named; it is the only prior that also looks at the source folder's own name (outermost, so the nearest folder still wins), while `calendar_folder_year_rule` and `filename_month_rule` read the folders between the source and the file exactly as they did in 0.2.

Accepted files: stills `.jpg .jpeg .heic .heif .png .webp`, videos `.mov .mp4 .m4v .avi .mkv .mts .m2ts .3gp .webm .wmv .mpg .mpeg`, animated `.gif`; one list in `common.py` shared by every stage and matched by the build side. Anything else is cut with reason `unsupported`.

`ffmpeg` and `ffprobe` are needed for videos (duration, codec, HDR, container time, Live Photo pair verification, video thumbnails, first-frame detection). Without them the stages still run, leave the video columns blank, say so loudly, and the validate stage flags every unverified pair; on Windows `setup.py` downloads a static build into the repository's `tools/ffmpeg/` when none is found; elsewhere install one and put it on PATH or set `[tools] ffmpeg` and `ffprobe` in the config; then re-run `index`.

## Layout

```
curate/
  common.py            config loader, project paths, per-year caps and the cap plan, age labels, anchors, pins, priors, media_id,
                       the show settings and show.json writer, the off-limits resolver, the config patcher
  config.example.toml  copy to <project>/config.toml; the intake fills it
  requirements.txt     pinned dependencies (installed by setup.py into .venv)
  setup.py             creates the environment, installs, fetches models, reports versions
  run.py               runs one stage
  heic.py              HEIC/JPEG dimensions and conversion, used by the build side where sips is absent
  stages/              one module per stage (show.py included), plus _probe.py, _takeout.py, _xmp.py, _lenses.py helpers
  models/              downloaded by setup; see models/README.md for licenses
```

## Status

All seven stages ran end to end on Windows against a 50-file sample of a real library (HEIC, three Live Photo pairs, a 240 fps clip, a 62-second video, a 10-bit HDR clip, a GIF, a burst, an exact duplicate, calendar-folder prints, a webp), followed by the build side's `prep`, `build`, `add-item` and a 60-second render. The Live Photo pair gate was tuned on that sample (see `references/03-validation-gates.md`, gate 4). The family gate runs from the export's people tags (`identify --tags-only`, or the detection run; both fill `family_present`); `[family] gate = "family"` refuses to run when `people.csv` carries no identities unless `--allow-presence-gate` is given, and `"none"` skips the check. Face matching against the seed photos is still a later milestone. Not yet exercised: Takeout zips on real data (tested on fabricated zips only), and macOS. 0.2 added the `show` stage, gate `none`, off-limits and must-include, `--pdf` and the wider file types; 0.3 added the derived cap, scope dates, the taste switches, `[audio]`, sidecars beside files and `identify --tags-only`; `CHANGELOG.md` says what each smoke test covered.

Things the port changed on purpose from the first run's scripts: the per-call time budget argument is gone; the calendar-folder, filename-month and folder-year priors are config, off by default; a date is never inherited from another file by stem alone; the Takeout sidecar lookup keys by member path and quarantines title collisions; the identify stage applies EXIF orientation before detection; unsupported extensions are cut with reason `unsupported` instead of reaching the build.
