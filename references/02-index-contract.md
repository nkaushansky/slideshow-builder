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
| `original_source_path` | provenance back to the export, including zip member paths |

Line endings and column order are preserved by every tool that rewrites the file. The build reads: `filename`, `type`, `companion`, `width`, `height`, `duration_s`, `fps`, `hdr`, `date`, `precision`, `featured`, `video_codec`.

## `features.txt`

One filename per line, the stills that take larger tiles. Identical to the rows with `featured = yes`. About one in six of the stills, spread across periods with a minimum per period, both orientations represented.

## `cut-list.csv`

Every file considered and not kept: `media_id`, `filename`, `location` (which working subfolder holds it), `reason` (one word: `off-limits`, `over-cap`, `no-family`, `no-people`, `undated`, `unsupported`, `superseded`, `burst`, `duplicate`, `flagged`, `swapped`, `removed`, `redated`), `original_source_path`. `off-limits` is the owner's list, applied before any other test; the apply tool refuses such a file in any later round, so it never re-enters the set. The cut list is the pool the review loop draws replacements from, so it must carry enough to find the file again.

## The accounting invariant

`rows in media.csv + rows in cut-list.csv = files accounted for`, every file exactly once. A swap removes a row from one and adds it to the other; a redate leaves a copy of the old name in `_removed/` and no cut-list row, because the same bytes are still in the set. Print the invariant after every change. If it does not balance, stop.

## `inventory.md` and `HANDOFF.md`

`inventory.md` is counts: files and moments, by type, by period, by extension and codec, date precision and source, featured, cut reasons, display-readiness. `HANDOFF.md` is the note to the build: what was done, the judgment calls, the uncertainties as uncertainties, the oddities the build must handle (HEIC, HEVC, HDR, slow motion, panoramas, tiny files, very long videos), and how to verify the transfer if the folder moves. It must never state a mechanism that was not demonstrated.

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
    "captions": "none"
  },
  "show": { "event": "the event", "event_date": "2026-10-10", "playback": "loop" },
  "audio": { "enabled": false, "files": [], "loop": true, "crossfade_s": 2 },
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
- `taste.mixed_tiles`, `taste.captions` and `show.playback` are carried through from the config for a later version; the build ignores them. `taste.chapters` is `[taste] chapters`; 0 means the build's default of ten, any other value is used.
- `show.event` and `show.event_date` (an ISO date or blank) are `[show] event` and `event_date`.
- `audio` is carried through from an `[audio]` section when one exists, else the defaults shown. Nothing acts on it in this version.
- `machines.player` is `[machines] player` (`vlc`, `tv-usb` or `browser`, default `vlc`; only `vlc` has launchers) and `machines.display_os` is `[machines] display_os`; both carried through.
- `off_limits` resolves `[show] off_limits`, a list of strings. Each entry is one of: a 64-hex media id; a path, absolute or relative to the project folder, to an existing file (hashed to a media id) or folder (every file in it hashed, recursively); otherwise a filename, matched case-insensitively against a file's original name and its date-prefixed `filename`. Both forms go into `filenames`, the bare form as given, and a filename the index already knows (`index/items.csv`) also puts that file's media id into `media_ids`, so `add-item` refuses the same bytes under any name. The select stage cuts these files; `add-item` refuses them.

Not in `show.json`: `[tools] ffmpeg`, `ffprobe` and `chrome`, which the build reads from `config.toml` directly. `[tools] chrome` names the browser the render and the scheduler simulator start (blank means Playwright's bundled Chromium, then installed Google Chrome).

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
