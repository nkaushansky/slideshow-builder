# The decided brief (template)

Fill this into `project/BRIEF.md` after the intake and Step 0, before any building. It is the document the build runs from. A design conversation may argue both sides of a question; this document records what was decided, by whom, when, and what it replaced. Its changelog is the part the first run's brief lacked, and the part that would have shown the build that a two-day-old override was not a founding rule.

---

# <event> slideshow: build brief

**State, <date>.** Build machine: <OS, chip, memory>. Display machine: <OS, screen, `[output] resolution` and `fps` as detected or answered, player>. Sources: <what, where, how many files, how many years, sidecars present or not>. Scope: <`[show] scope_start` to `scope_end`, or `first_year` to `last_year`>. Working folder: <path>. Set status: <not yet selected | proposed cut of N moments | frozen at N files / N moments>. Playback: <`[show] playback` loop, or once with the cards below>. Hard stop: <date>. Owner hours budget: <hours>.

**One paragraph.** What is being built, where it plays, for whom, how long it runs, and the exact deliverable (an mp4 that loops in VLC or plays from a stick on a TV, with or without music, with or without a title and an end card; the browser player as fallback).

## Ground rules

- Sources are read-only. Derived assets go in the build folder, keyed by original filename.
- Dates come from the index; the filename prefix equals the index date. Any disagreement with a file's own metadata is a flag with a named witness, never a rule.
- The set is frozen at handoff; every later change goes through the apply tool and the change log.
- Everything that moves is a function of the clock, computed in script.
- <any owner rule stated verbatim at intake>

## Hardware and environment (Step 0 findings)

- <OS and version, chip, memory, disk>
- <Python, Node, ffmpeg, Chrome, VLC: versions, paths, how installed>
- <timezone and display resolution as Step 0 detected them, and whether `--apply` wrote them or the intake answered>
- <Playwright: `[tools] chrome`, bundled browser or installed Chrome via channel>
- <screenshot cost measured at the output resolution; sleep settings; keep-awake command>
- <anything that failed and the fallback taken>

## Inputs

- <counts: files, moments, stills, Live Photo pairs, videos, GIFs; HEIC and HEVC shares; HDR and slow-motion files; longest videos; oddities>
- <the index columns the build consumes>
- Verification of the copy: <file count, byte total, the invariant>

## Decisions

| # | Decision | Chosen | Alternatives considered | Decided by | Date |
|---|---|---|---|---|---|
| 1 | Format | scrolling mosaic, justified rows | hero singles; static grid; hybrid | owner | |
| 2 | Ordering | `[taste] order` <chapters (mini-timelines, N chapters, ring), chronological (one chapter) or shuffled (seed N)> | strict chronology; arranged for variety; a shuffle | owner | |
| 3 | Large tiles | `[taste] mixed_tiles` <yes: featured stills plus every video, no full-screen singles; no: none, every row a base row> | heroes; promotion of videos; a flat grid | owner | |
| 4 | Live Photos | `[taste] live_photos` <clip: full clip, hold, no bounce, autoplay as the tile; still: the still alone> | trim and ping-pong; still with hover | owner | |
| 5 | Videos | included (`[taste] include_videos`, `include_gifs`), feature rows, silent, scroll through, per-file start; slow motion <slow or realtime> | full screen; paused scroll; stills only | owner | |
| 6 | Captions | `[taste] captions` <none; date, each tile's date at its own precision; text, the `caption` column of `media.csv`, edited by the owner before the build> | the other two; baked into the tiles | owner | |
| 7 | Audio | <none, or `[audio]`: the files in play order, loop <on or off>, crossfade <s> s, fade <s> s, volume <v>, muxed onto the render> | the DJ's sound; ambient in the quiet window | owner | |
| 8 | Output | `[output]`: <resolution> at <fps> fps, quality <final or draft>, ×<concat_copies> concat; `[machines] player` <vlc, tv-usb or browser> | live browser | build | |
| 9 | Loop length | an output of the cap; expected <N> min at <speed> px/s (`[taste] scroll_speed`, 0 = the first run's pace scaled to `[output]` height) with <tile_size> tiles | a fixed target | build | |
| 10 | Chronology versus spacing | chronology wins; `disorderWeight` <N> | spacing wins | owner | |
| 11 | Cap source and period | <derived: N per <period> from a <M>-minute target (`[show] loop_minutes_target`) at <s> s per item over <Y> period-shares; or config: `[selection] cap_per_year` N>; `[selection] period` <year, quarter or month>; undated <`[selection] undated_cap` N, 0 = none seated>; overrides <`[selection.cap_overrides]`, years as keys, or none> | the other one; the other units | owner | |
| 12 | Motion density | `[taste] motion_density` <calm, normal or busy> (`movingCap` <N>, `maxBaseMoving` <N>) | the other two | owner | |
| 13 | Playback and cards | `[show] playback` <loop: the file plays on repeat; once: one pass, ending on the end card>; title card <the words, or none>; end card <the words, or none>; <`card_seconds`> s each, <`card_fade_s`> s of fade | a loop with no cards; a card painted over the first rows | owner | |

## Sequence, layout, motion, render

Copy the relevant sections of `references/06-layout-motion-render.md` and edit the numbers to this show. Print the expected row counts and feature-row share here, from the anchor arithmetic.

## Tuning knobs

The config block with this show's values: `[output]`, `[taste]` and `[audio]` from `config.toml` as `python curate/run.py show` derived them, the playback mode and the two cards, and the cap plan with its period (paste the lines `select` printed, the cap line and the per-period table), then the build script's own knobs.

## Build order

0. Environment check (`python curate/setup.py --project <folder> --apply`); report.
1. Verify the handoff; print the invariant.
2. Prepare tiles, clips, music tracks, frames.
3. Build the sequence; print counts and share.
4. Live-player round with the owner (checkpoint 2).
5. Apply flags through the ledger; rebuild; show the changes.
6. 60-second test render; window renders around special cases.
7. Full render; wrap check on the loop; the cards joined on as their own segments when there are any; the soundtrack muxed on when there is music; `--concat` (×<concat_copies>, refused when the show plays once); soak.
8. Launcher; backup; the owner's full watch (checkpoint 3).
9. Additions cutoff: <date, evening>. Final render that night. Hard stop: <date>.

## Acceptance checks

From `references/06-layout-motion-render.md`, with this show's numbers. Update them whenever a decision changes.

## Change workflow

How a swap, a drop and a redate are applied; where candidates come from; that one swap barely moves the sequence while adding or removing re-deals every chapter, so the order is approved last.

## What this is not

Not a gallery, not interactive, not chronological end to end (unless `[taste] order` says so), not captioned unless `[taste] captions` says so, silent unless `[audio]` says otherwise, endless unless `[show] playback` says `once`. No hero slides, no pausing on single images. <edit to taste>

## Changelog

Every decision, one line, newest last. Each entry names what it superseded.

| Date | Decision | Superseded | By | Why |
|---|---|---|---|---|
| <date> | Intake answers recorded | | owner | |
| <date> | Step 0 findings; versions pinned | | build | |
| <date> | <e.g., `movingCap` 3 to 4> | <the previous value> | owner, at the live-player round | <one line> |
