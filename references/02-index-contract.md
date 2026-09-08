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

Every file considered and not kept: `media_id`, `filename`, `location` (which working subfolder holds it), `reason` (one word: `over-cap`, `no-family`, `no-people`, `undated`, `superseded`, `burst`, `duplicate`, `flagged`, `swapped`, `removed`, `redated`), `original_source_path`. The cut list is the pool the review loop draws replacements from, so it must carry enough to find the file again.

## The accounting invariant

`rows in media.csv + rows in cut-list.csv = files accounted for`, every file exactly once. A swap removes a row from one and adds it to the other; a redate leaves a copy of the old name in `_removed/` and no cut-list row, because the same bytes are still in the set. Print the invariant after every change. If it does not balance, stop.

## `inventory.md` and `HANDOFF.md`

`inventory.md` is counts: files and moments, by type, by period, by extension and codec, date precision and source, featured, cut reasons, display-readiness. `HANDOFF.md` is the note to the build: what was done, the judgment calls, the uncertainties as uncertainties, the oddities the build must handle (HEIC, HEVC, HDR, slow motion, panoramas, tiny files, very long videos), and how to verify the transfer if the folder moves. It must never state a mechanism that was not demonstrated.

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
