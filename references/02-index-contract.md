# The index contract

The files the curation stages hand to the build, and the formats every tool reads and writes. Keep them exact: the build depends on them, and the first run's accounting invariant caught bookkeeping mistakes twice because these formats made every change auditable.

## `media.csv`, one row per file in `handoff/media/`

| Column | Meaning |
|---|---|
| `media_id` | SHA-256 of the file's bytes; the stable identity across renames |
| `filename` | `YYYY-MM-DD_<original name>`; zero-filled parts mean unknown (`2022-00-00_` = year only, `2023-08-00_` = year and month) |
| `type` | `still`, `livephoto-still`, `livephoto-video`, `video`, `animated-gif` |
| `companion` | the other half of a Live Photo pair, symmetric and complete, blank otherwise |
| `width`, `height` | displayed dimensions **after EXIF orientation**; the build uses these and never decodes at runtime |
| `duration_s` | seconds, videos and GIFs only |
| `fps`, `hdr` | frame rate and a 10-bit HDR flag, so slow motion and tone-mapping are known before preparation |
| `date` | the settled date, equal to the filename prefix |
| `precision` | `day`, `month`, `year` |
| `date_source` | the rung that settled it: `sidecar`, `exif`, `container`, `prior`, `content-match`, `owner`, `visual` |
| `date_witness` | one sentence naming the witness when the date is not the file's own metadata |
| `exif_datetime_original` | the raw value as shipped, informational |
| `people` | family members present, semicolon-separated, from the identify stage |
| `tag` | tradition or theme tags, semicolon-separated |
| `featured` | `yes` for the larger-tile picks |
| `video_codec`, `has_audio` | for preparation |
| `original_source_path` | provenance back to the export: `<zip>!<member>` for a file from a Takeout zip, `<source label>!<relative path>` for a file from a folder source (the index's `source_path`) |

Line endings and column order are preserved by every tool that rewrites the file. The build reads: `filename`, `type`, `companion`, `width`, `height`, `duration_s`, `fps`, `hdr`, `date`, `precision`, `featured`, `video_codec`.

## `features.txt`

One filename per line, the stills that take larger tiles. Identical to the rows with `featured = yes`. About one in six of the stills, spread across periods with a minimum per period, both orientations represented.

## `cut-list.csv`

Every file considered and not kept: `media_id`, `filename`, `location` (which working subfolder holds it), `reason` (one word: `off-limits`, `excluded-type`, `over-cap`, `no-family`, `no-people`, `undated`, `unsupported`, `superseded`, `burst`, `duplicate`, `flagged`, `swapped`, `removed`, `redated`), `original_source_path`. `off-limits` is the owner's list, applied before any other test; the apply tool refuses such a file in any later round, so it never re-enters the set. `excluded-type` is a type the taste leaves out: every video with `[taste] include_videos = false`, every GIF with `include_gifs = false`, every Live Photo clip with `live_photos = "still"`. The cut list is the pool the review loop draws replacements from, so it must carry enough to find the file again.

## The accounting invariant

`rows in media.csv + rows in cut-list.csv = files accounted for`, every file exactly once. A swap removes a row from one and adds it to the other; a redate leaves a copy of the old name in `_removed/` and no cut-list row, because the same bytes are still in the set. Print the invariant after every change. If it does not balance, stop.

## `inventory.md` and `HANDOFF.md`

`inventory.md` is counts: files and moments, by type, by period, by extension and codec, date precision and source, featured, cut reasons, display-readiness. `HANDOFF.md` is the note to the build: what was done, the judgment calls, the uncertainties as uncertainties, the oddities the build must handle (HEIC, HEVC, HDR, slow motion, panoramas, tiny files, very long videos), and how to verify the transfer if the folder moves. It must never state a mechanism that was not demonstrated.

## `items.csv` and `takeout-sidecars.csv`, on the index side

`index/items.csv` is the index stage's row per file: the `media.csv` columns above plus the index's own (`source_kind`, `source_path`, the probe facts, the hashes, the pairing evidence) and `people_tags`, the names the file's sidecar carries (Takeout `people[].name`, or XMP `PersonInImage`, else the region names), semicolon-separated, blank when there is no sidecar or it names nobody. The identify stage turns `people_tags` into `people` and `family_present` in `people.csv`.

`source_path` has one shape for every source: `<zip>!<member>` for a file inside a Takeout zip and `<source label>!<relative path>` for a file in a folder source, the label being the source folder's name. The index looks a file's sidecar up by that path in `index/takeout-sidecars.csv`, which ingest writes with the columns `zip` (the zip, or the source label), `member` (the sidecar's own path inside it), `title`, `folder`, `photo_taken_ts` and `creation_ts` (epoch seconds), `lat`, `lon`, `people`, `description`, `title_collision`, `media_member` (the media file the sidecar belongs to: resolved by the Takeout naming rules for a JSON sidecar and by the same folder and the same stem for an XMP one; blank when unresolved) and `source` (`takeout-zip`, `takeout-json` or `xmp`). For a folder source, ingest counts the `.xmp` sidecars that reached no file and the `.json` files too large to be read as sidecars (over 64 000 bytes) in its per-source line, and names up to eight of them one by one with the reason (`! sidecar Album/IMG_0001.xmp: matches 2 files (IMG_0001.jpg, IMG_0001.png) and no single still among them; left to neither`), so a date that reached nothing is never only a number in a total.

## `show.json`, the display and taste settings

Written by `python curate/run.py show` and by the handoff stage (the same function in `curate/common.py`); read by every build-side command. Every key below is always present. Numbers are integers unless noted.

```json
{
  "written": "2026-09-15T14:03:00",
  "source": "config.toml",
  "output": { "width": 1920, "height": 1080, "fps": 30, "concat_copies": 3, "quality": "final" },
  "taste": {
    "tile_size": "medium",
    "base_row_height": 390,
    "feature_row_height": 614,
    "max_tile_height": 1228,
    "gutter": 6,
    "scroll_speed": 75,
    "background": "#07070F",
    "mixed_tiles": true,
    "chapters": 0,
    "captions": "none",
    "order": "chapters",
    "moving_cap": 4,
    "max_base_moving": 2,
    "include_videos": true,
    "include_gifs": true,
    "live_photos": "clip",
    "slow_motion": "slow",
    "seed": 20260905
  },
  "show": { "event": "the event", "event_date": "2026-10-10", "playback": "loop" },
  "audio": { "enabled": false, "files": [], "loop": true, "crossfade_s": 2, "fade_s": 2, "volume": 1.0 },
  "selection": {
    "cap_per_year": 21,
    "cap_source": "derived",
    "loop_minutes_target": 15,
    "seconds_per_item": 2.2,
    "target_items": 409,
    "year_shares": 19.5
  },
  "machines": { "player": "vlc", "display_os": "" },
  "off_limits": { "media_ids": ["<sha256 hex>"], "filenames": ["IMG_0012.HEIC"] }
}
```

Every value is derived in Python from `config.toml`; the JavaScript side only reads numbers and never repeats the arithmetic. A bad value stops the `show` stage with the key name and what it accepts.

- `output.width` and `output.height` come from `[output] resolution = "WxH"`, the display's logical resolution. Missing or blank means 2560×1440 and the `show` stage prints a warning naming the key. Anything else than two even numbers of at least 320 is an error.
- `output.fps` is `[output] fps`, default 60, accepted 10 to 120. `output.concat_copies` is `[output] concat_copies`, default 3, accepted 1 to 12. `output.quality` is `[output] quality`, `final` (x264 slow, crf 18) or `draft` (veryfast, crf 23), default `final`.
- `taste.tile_size` is `[taste] tile_size`: `small`, `medium` or `large`, default `medium`. Each preset is a share of `output.height`: small 0.28 base and 0.44 feature; medium 0.3611 and 0.5694 (520 and 820 px at 1440 rows, the first run's values); large 0.46 and 0.72. Each height is rounded to the nearest even integer. `[taste] base_row_height` and `feature_row_height` in pixels override the preset when set.
- `taste.max_tile_height` is twice the feature row height (1640 at 2560×1440 medium, the first run's cap). Tiles and clips are prepared to it, so a display change after `prep` means `bin/prep --force`; `bin/build` warns when the prepared cap disagrees with `show.json`.
- `taste.gutter` is 8 px scaled by width over 2560, never under 4. `taste.scroll_speed` is `[taste] scroll_speed` in px/s at the output resolution; 0 or missing means the first run's pace scaled to the height, 100 px/s at 1440. `taste.background` is `[taste] background`, a six-digit hex colour, default `#07070F`.
- `taste.chapters` is `[taste] chapters`; 0 means the build's default of ten, any other value is used. `taste.order` is `[taste] order`: `chapters` (the default), `chronological` (one chapter) or `shuffled` (the items shuffled on `taste.seed` before the deal). `taste.moving_cap` and `taste.max_base_moving` come from `[taste] motion_density`: `calm` 2 and 1, `normal` 4 and 2 (the default), `busy` 6 and 3. `taste.mixed_tiles` is `[taste] mixed_tiles`, default true; false means no featured picks and no anchors, every row a base row. `taste.include_videos` and `taste.include_gifs` are `[taste] include_videos` and `include_gifs`, default true. `taste.live_photos` is `[taste] live_photos`, `clip` (the default) or `still`; `taste.slow_motion` is `[taste] slow_motion`, `slow` (the default) or `realtime`. `taste.seed` is `[taste] seed`, a whole number, default 20260905; the shuffled order is a deterministic function of it. A value outside the accepted ones stops the `show` stage with the key and what it accepts. `taste.captions` and `show.playback` are carried through from the config for a later version; the build ignores them.
- `show.event` and `show.event_date` (an ISO date or blank) are `[show] event` and `event_date`.
- `audio` is `[audio]`: `enabled` (default false); `files`, the music in play order, each path absolute or relative to the project folder, each with one of the extensions `.mp3 .m4a .aac .wav .flac .ogg .opus` and, with `enabled` true, existing (a missing file with `enabled` false is a warning; the extension and existence are all the `show` stage checks, ffmpeg decodes at `prep`), written as absolute paths; `loop` (default true: repeat the playlist until it covers the video); `crossfade_s` (at least 0, default 2, between consecutive tracks); `fade_s` (at least 0, default 2, in at the start and out at the end of the soundtrack); `volume` (0.0 to 2.0, default 1.0, applied to the soundtrack). `enabled` with no files is an error. The 0.1 key `[show] audio = true` without an `[audio]` section is an error naming the section; `audio = false` is ignored.
- `selection` is informational, the cap plan for the brief and the record: `cap_per_year`, `cap_source` (`config` when `[selection] cap_per_year` is a number above 0, `derived` when it is 0 or missing), `loop_minutes_target` (`[show] loop_minutes_target`, default 15), `seconds_per_item` and `year_shares` (decimals) and `target_items` (the moment count the target implies), as `04-selection-lenses.md` defines them. With `cap_source` `config` the derivation never runs, so `loop_minutes_target`, `seconds_per_item` and `target_items` are `null` and neither `[output]`, `[taste]` nor `[show] loop_minutes_target` is read for the cap; `year_shares` is still the scope's. Nothing on the build side reads any of it.
- `machines.player` is `[machines] player` (`vlc`, `tv-usb` or `browser`, default `vlc`) and `machines.display_os` is `[machines] display_os`. `vlc` has the VLC launchers; `tv-usb` makes the render add the H.264 profile and level a TV stick decodes and warn about files of 4 GiB and over; `browser` has the kiosk launchers.
- `off_limits` resolves `[show] off_limits`, a list of strings. Each entry is one of: a 64-hex media id; a path, absolute or relative to the project folder, to an existing file (hashed to a media id) or folder (every file in it hashed, recursively); otherwise a filename, matched case-insensitively against a file's original name and its date-prefixed `filename`. Both forms go into `filenames`, the bare form as given, and a filename the index already knows (`index/items.csv`) also puts that file's media id into `media_ids`, so `add-item` refuses the same bytes under any name. The select stage cuts these files; `add-item` refuses them.

Not in `show.json`: `[tools] ffmpeg`, `ffprobe` and `chrome`, which the build reads from `config.toml` directly. `[tools] chrome` names the browser the render and the scheduler simulator start (blank means Playwright's bundled Chromium, then installed Google Chrome).

## The render's file names

`bin/render` writes into the project's `build/`: `test-<N>s.mp4` for `--seconds N` (`test-<from>s-<N>s.mp4` with `--from`), `slideshow.mp4` for one whole loop, `slideshow-x<N>.mp4` for `--concat` (N from `output.concat_copies`), and `-labels` before `.mp4` on any of them for `--labels`. With `audio.enabled` the verified video-only file keeps its name with `-silent` before `.mp4` (`slideshow-silent.mp4`, `test-60s-silent.mp4`, `test-3s-labels-silent.mp4`) and the file with the soundtrack takes the plain name; `slideshow-x<N>.mp4` is then the silent copies joined (`slideshow-silent-x<N>.mp4`, removed once the muxed file exists) with one soundtrack over the whole file; the playlist and each render's cut soundtrack stay in `build/audio/` as `playlist.m4a` and `<render name>.soundtrack.m4a`, derived files that go with the rest. The launchers take the first `slideshow-x*.mp4` in name order, then `slideshow.mp4`, so the plain names are the ones that play and no `-labels` or `-silent` file ever is. A muxed file that fails its probe is renamed with `BAD-` in front of the whole name (`BAD-slideshow.mp4`, `BAD-slideshow-x3.mp4`), and when the mux itself fails a file of the plain name left by an earlier render is renamed `OLD-<name>.mp4`; neither pattern matches what a launcher looks for, both are logged, the PROBLEMS lines name the file under its new name and the run still ends non-zero.

## `changes.log`

Append-only, one line per operation, written by the apply tool:

```
<ISO timestamp>  add     <filename>  type=<type> [companion=<name>]  <w>x<h> [<dur>s <codec>]  date=<date>/<precision>  [exif=<raw>]  [from cut-list (<reason>): <source path>]
<ISO timestamp>  remove  <filename>  -> handoff/_removed/, cut-list.csv reason=<swapped|removed|redated>
<ISO timestamp>  cut     <filename>  leaves cut-list.csv (now in the set)
```

## `replacements.csv`, the review round's return trip

Columns: `replaces,new_file,companion,date,featured,notes`. A row with `replaces` set and `new_file` blank is a drop with no replacement; a row with `replaces` blank is a plain addition (the slot was already emptied). Dates accept the zero-filled forms. The apply tool validates every row, dry-runs each, then applies and logs.

## Stable IDs and write-back

Because `media_id` is a content hash, two copies of the index can always be diffed by identity. Whenever the index leaves the project folder (a second machine, a helper's session), the return trip carries `media.csv` and `changes.log`, and the other side regenerates from them. Hand-typed change lists are how records go stale.
