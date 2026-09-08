# The decided brief (template)

Fill this into `project/BRIEF.md` after the intake and Step 0, before any building. It is the document the build runs from. A design conversation may argue both sides of a question; this document records what was decided, by whom, when, and what it replaced. Its changelog is the part the first run's brief lacked, and the part that would have shown the build that a two-day-old override was not a founding rule.

---

# <event> slideshow: build brief

**State, <date>.** Build machine: <OS, chip, memory>. Display machine: <OS, screen, resolution, player>. Sources: <what, where, how many files, how many years, sidecars present or not>. Working folder: <path>. Set status: <not yet selected | proposed cut of N moments | frozen at N files / N moments>. Hard stop: <date>. Owner hours budget: <hours>.

**One paragraph.** What is being built, where it plays, for whom, how long it runs, and the exact deliverable (an mp4 that loops in VLC; the browser player as fallback).

## Ground rules

- Sources are read-only. Derived assets go in the build folder, keyed by original filename.
- Dates come from the index; the filename prefix equals the index date. Any disagreement with a file's own metadata is a flag with a named witness, never a rule.
- The set is frozen at handoff; every later change goes through the apply tool and the change log.
- Everything that moves is a function of the clock, computed in script.
- <any owner rule stated verbatim at intake>

## Hardware and environment (Step 0 findings)

- <OS and version, chip, memory, disk>
- <Python, Node, ffmpeg, Chrome, VLC: versions, paths, how installed>
- <Playwright: bundled browser or installed Chrome via channel>
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
| 2 | Ordering | mini-timelines, N chapters, ring | strict chronology; arranged for variety | owner | |
| 3 | Large tiles | featured stills plus every video, no full-screen singles | heroes; promotion of videos | owner | |
| 4 | Live Photos | full clip, hold, no bounce, autoplay as the tile | trim and ping-pong; still with hover | owner | |
| 5 | Videos | feature rows, silent, scroll through, per-file start | full screen; paused scroll | owner | |
| 6 | Captions | none | baked into tiles | owner | |
| 7 | Audio | none | ambient in the quiet window | owner | |
| 8 | Output | <resolution> at 60 fps mp4 in VLC, ×3 concat | live browser | build | |
| 9 | Loop length | an output; expected <N> min at <speed> | a fixed target | build | |
| 10 | Chronology versus spacing | chronology wins; `disorderWeight` <N> | spacing wins | owner | |

## Sequence, layout, motion, render

Copy the relevant sections of `references/06-layout-motion-render.md` and edit the numbers to this show. Print the expected row counts and feature-row share here, from the anchor arithmetic.

## Tuning knobs

The config block with this show's values.

## Build order

0. Environment check; report.
1. Verify the handoff; print the invariant.
2. Prepare tiles, clips, frames.
3. Build the sequence; print counts and share.
4. Live-player round with the owner (checkpoint 2).
5. Apply flags through the ledger; rebuild; show the changes.
6. 60-second test render; window renders around special cases.
7. Full render; wrap check; ×3; soak.
8. Launcher; backup; the owner's full watch (checkpoint 3).
9. Additions cutoff: <date, evening>. Final render that night. Hard stop: <date>.

## Acceptance checks

From `references/06-layout-motion-render.md`, with this show's numbers. Update them whenever a decision changes.

## Change workflow

How a swap, a drop and a redate are applied; where candidates come from; that one swap barely moves the sequence while adding or removing re-deals every chapter, so the order is approved last.

## What this is not

Not a gallery, not interactive, not chronological end to end, not captioned, not scored. No hero slides, no pausing on single images. <edit to taste>

## Changelog

Every decision, one line, newest last. Each entry names what it superseded.

| Date | Decision | Superseded | By | Why |
|---|---|---|---|---|
| <date> | Intake answers recorded | | owner | |
| <date> | Step 0 findings; versions pinned | | build | |
| <date> | <e.g., `movingCap` 3 to 4> | <the previous value> | owner, at the live-player round | <one line> |
