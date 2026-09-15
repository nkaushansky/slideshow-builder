---
name: slideshow-builder
description: Build a looping photo-mosaic slideshow, or a curated photo set for a gallery or album, from a Google Takeout, an Apple Photos export or a folder of photos. Use when the user wants a slideshow for an event, a "best of" selection from years of photos, a themed set (a trip, a person, a tradition), or a gallery from their photo library. Starts with an intake, runs the curation and build stages, and stops at owner checkpoints.
---

# slideshow-builder

You are building a photo slideshow or a curated set from the user's own photos, on their machine. The process has nine stages, three owner checkpoints, and a short list of hard rules. Read this file fully before starting. The references hold the detail; this file holds the order and the stops.

## 0. Intake, before anything else

Do not touch a file until the intake is answered. Ask all of the questions below in **one message**, grouped as shown, with the default in brackets where one exists. Accept "default" as an answer. Then write the answers to `project/intake.md` and the machine-readable parts to `project/config.toml`. The full question set with the reasoning behind each is in `references/00-intake.md`; ask it as written.

**Source**
1. Where are the photos, and in what form: Google Takeout zips (kind `takeout`) or the unzipped Takeout folder (kind `folder`), an Apple Photos export, iCloud download, a folder tree, or a mix? Give the path or paths. For Apple Photos, export with File > Export > Export Unmodified Originals and tick "Export IPTC as XMP", so dates, places and the names of people travel with the files as .xmp sidecars.
2. Roughly how many files and how many years, if you know.
3. Are there other sources with photos that should be considered: other family members' phones, an old backup, printed-calendar exports, shared albums?

**Machines**
4. What machine will run this build: operating system and version, chip, memory, free disk?
5. What machine will show the slideshow, if different: operating system, screen size and resolution, and how it will play: VLC on a computer, a TV playing from a USB stick, or a browser? [the build machine, VLC; Step 0 detects its display] The answer lands in `[output] resolution` and `[output] fps` and in `[machines] player` (`vlc`, `tv-usb` or `browser`) in `config.toml`; `tv-usb` makes the render pick the H.264 level a TV stick decodes and warn about files of 4 GiB and over; `browser` has kiosk launchers of its own; when the display is the build machine, leave the resolution to Step 0.
6. Are Python, Node, ffmpeg and Google Chrome installed on the build machine? [I will check; answer only if you know something is missing]

**The show**
7. What is the event, the date, and the hard stop for a finished file? [hard stop = two days before]
8. Where will the screen be, how far away will people stand, will anyone be attending it, how long does it need to run, and is there internet? [unattended, offline, the length of the reception] Tile size small, medium or large? [medium; large for a wall seen from across the room]
9. Does the show loop until someone stops it, or play through once and end? [loop] Any words on a card before it starts, and after it ends? [none; 6 seconds each, 1 second of fade] `[show] playback` is `loop` or `once`; `title_card` and `end_card` hold at most 6 lines and 200 characters each, for `card_seconds`, fading in and out over `card_fade_s` (at most half of that). The cards go into the rendered file as their own segments around the loop, and the live player holds the same ones. An end card is only reached when the show plays once, and a show that plays once needs someone to restart it.
10. Who owns the room's sound? Should the slideshow have music? [no audio] Music: the files in play order, whether to repeat them until the loop ends, crossfade and fade seconds, and the volume; they go to `[audio]` in `config.toml` and the render lays them under the video; the DJ's sound is the alternative.

**The people**
11. Who is the show about: one honoree, a couple, a family? Name the people who "count" as family for the selection, so that photos with none of them in frame can be dropped; spell the names as the photo app does (a one-word name such as `Sam` also matches a tag such as `Sam Jones`). A show with no people requirement (a place, a trip's scenery) sets the people gate to `none`.
12. Can you provide 5 to 20 clear photos of each of those people, or does your export already carry people tags (a Google Takeout does; an Apple export does with "Export IPTC as XMP" ticked)? [both, if possible] The tags feed the family gate (`[family] gate = "family"`) through `identify --tags-only`, which needs no detection models; run the plain `identify` whenever the models from Step 0 are installed, because only it fills the person count and person area that the `people` gate, the v4 score and the featured gate use (on a tags-only `people.csv`, select refuses `gate = "people"` and names the choices). The seed photos are recorded for the face-matching milestone.

**Scope and theme**
13. Which years or dates? [the honoree's whole life, or the whole export] Dates go to `[show] scope_start` and `scope_end`, which pro-rate the first and last years' caps from their months; whole years go to `first_year` and `last_year`; with neither, the birth year and the event year stand in.
14. Is this a whole-life show, or a theme: a trip, a sport, a tradition, a place, a group of people? [whole life]
15. Any must-include photos or events, and anything off limits? [none; the family decides what is off limits] Either list takes filenames, media ids, or a folder of photos. Off-limits files are excluded by select and refused by the apply tool; must-include files are seated like pins.
16. How many moments do you want on screen, roughly, or should the cap fall out of the loop length? [derived from the loop length target (`[show] loop_minutes_target`, 15 minutes) and the tile size, pro-rated for partial periods; or a cap per period in `[selection] cap_per_year`, with `[selection.cap_overrides]` for single years] Should the cap count in years, quarters or months? [year; `[selection] period`, and a trip or a season wants `month`, where a year's cap would seat one week and call it a year] Are there undated files worth seating? [none; `[selection] undated_cap` 0]

**Taste** (defaults are what worked on the first run)
17. Mixed tile sizes with occasional larger tiles, no full-screen singles? [yes] No means no featured picks and videos in the grid, every row a base row.
18. Live Photos as clip or still? [clip] Videos and GIFs included? [yes] Slow motion as the phone shows it, or at real time? [slow] Clips are always silent and nothing pauses the scroll.
19. Order: chronological within short chapters that each sweep the whole span, one long timeline, or shuffled? [chapters] Motion density: calm, normal or busy, at most 2, 4 or 6 tiles moving at once? [normal]
20. Captions? [none] `date` puts each tile's own date under it at the precision the file carries (`2019`, `June 2021`, `June 15, 2021`); `text` puts the description the export carried for that file, which you can edit in `handoff/media.csv` before the build. The player draws them on the page, so they are in the live player and not in the rendered video.
21. Anything else you already know you want or hate? Verbatim.

**Time and privacy**
22. How many hours can you give to reviewing contact sheets and watching the loop? [3 to 4 hours total]
23. Where should the working folder live, and what should be deleted when the event is over? [beside the export; delete derived copies, keep the index and the final video]
24. Consent: nothing leaves the machine, and you are entitled to use these photos for this purpose. [confirm]

After the answers, run **Step 0, the environment check**, from `references/01-stages.md`: `python curate/setup.py --project <folder> --apply` detects the operating system, Python, Node, ffmpeg, Chrome and VLC with versions, checks disk space, detects the machine's timezone and the logical resolution of its display, and writes them, with `[machines] build_os`, into `config.toml` where the intake left them blank. Ask for whatever it could not detect. Then run `python curate/run.py ingest --dry-run`, which counts the sidecars of every source (Takeout JSON inside the zips or beside the files, Apple .xmp) without copying anything, and report what it found and what must be installed, with pinned versions; the HEIC/HEVC share and the special cases (Live Photo pairs, HDR, slow motion, panoramas, tiny files, long videos) come out of the index stage and `HANDOFF.md`. Then fill `references/07-decided-brief-template.md` into `project/BRIEF.md`. From here on, every decision is a dated line in the brief's changelog.

## 1. The stages

Run them in order. Each stage is a command in `curate/` or `build/`; each reads and writes the project folder and is resumable. Details, inputs, outputs and benchmarks are in `references/01-stages.md`. If a stage script is missing or fails on this machine, implement or repair it from the references before continuing, and say so in the changelog.

| Stage | What it does | Who acts |
|---|---|---|
| ingest | Copy, never move, into one flat working folder; index the sidecars, inside Takeout zips or beside the files (Takeout JSON, XMP); hash every file; assign stable IDs; verify by flags | Claude |
| index | Sidecars first, then EXIF, container times, dimensions after orientation, duration, codec, perceptual hash, sharpness; pair Live Photos; find bursts and duplicates; settle a date with precision, the rung that settled it and a witness | Claude |
| validate | The gates in `references/03-validation-gates.md`; writes flags, never silently fixes | Claude, owner resolves flags |
| identify | Who is in frame: the export's people tags matched against the family names (`--tags-only` needs no models and serves the family gate only), plus person and face detection for presence, person area and group size | Claude |
| select | Build the candidate pool from the scope, leave out the types the taste excludes, apply the cap (derived from the loop length target, or set per period; `[selection] period` is the year, the quarter or the month), run the four lenses and the consensus pass, choose featured picks | Claude |
| review | Numbered contact sheets of the proposed cut, approval and edits by number, alternates on request; a PDF of the sheets for an owner who is not at the machine | **Owner checkpoint 1** |
| handoff | Freeze the set as the index contract: `media/`, `media.csv`, `features.txt`, `cut-list.csv`, `inventory.md`, `HANDOFF.md`, `show.json`; the accounting invariant must balance | Claude |
| build | Prepare tiles, clips and the music tracks, build the sequence and rows in the chosen order, open the live player for one review round, apply flags through the change ledger | **Owner checkpoint 2** |
| render | Test render (labelled when the owner is not at the machine), full render of exactly one loop with the wrap proved, the title and end cards joined on as their own segments, the soundtrack muxed on when there is music, concat for playback, soak, launcher; then the full watch | **Owner checkpoint 3** |

The three checkpoints are stops. At each one, present what the owner needs to see, wait for their answer, apply it, and record it.

## 2. Hard rules

These came from the first run's failures (`references/08-lessons.md`). They are not optional.

1. **A camera filename is not an identity.** Never join, pair or date files by IMG number or stem alone. Every join needs a second witness: timestamps within seconds, the same camera, or pixel similarity. Absent a witness, do not join.
2. **Reject impossible dates.** A HEIC or HEVC file before 2017, a phone model that did not exist in the claimed year, a resolution the era could not produce. Flag, do not write.
3. **A prefix that disagrees with intact metadata is a flag, never a rule.** If a settled date overrides the file's own EXIF, the record must name the witness. Never write a mechanism you have not demonstrated.
4. **Sources are read-only.** Copy, never move; quarantine, never delete; keep the export until the event is over.
5. **Owner memory is a witness with a confidence.** Record it as provisional until a second source agrees.
6. **Presence is not identity.** "A person is in frame" is a gate; "one of the family is in frame" is what the show needs. Use the identify stage, and say on every sheet who the detector thinks is present.
7. **Never guess what a photo shows.** Contact sheets and the owner's eyes decide. Claude's guesses about flagged photos were right less than half the time on the first run.
8. **Fifteen sheets, not sixty.** Review the proposed cut, with alternates on demand. Do not put four full selection passes in front of the owner.
9. **One machine, one folder, one ledger.** Curation and build run on the same machine against the same project folder. Every change to the set goes through the apply tool and the change log, and the index is regenerated from the ledger, never hand-edited.
10. **Pin the toolchain.** Step 0 names versions and verifies them. Do not build on "it should work".
11. **Render last, prove cheaply first.** No full render before the owner's live-player round. A 60-second test render and a wrap probe before every full render. Window renders around every special case (slow motion, HDR, the longest videos).
12. **A fallback that can mask a failure must fail loudly.** Padding, retries and defaults get thresholds. Verify derived sequences by content (distinct frames), not by file count.
13. **Watch the final video once, all the way through, before declaring it done.** A soak test measures dropped frames, not frozen tiles.
14. **The brief has a changelog.** Every decision is dated, owned, and names what it superseded, so an override never reads as a founding rule.

## 3. Working agreements

- Work in `project/` inside the user's chosen working folder; never in this repository.
- Every mutating command has `--dry-run`; use it first, show the plan, then run.
- Print counts after every stage and keep the invariant: kept files + cut files = files accounted for, every file exactly once.
- Log time. Ask the owner to note their hours at each checkpoint; write them to `project/hours.md`.
- Keep the change log append-only, and regenerate `media.csv` from it rather than editing by hand.
- If the user runs Cowork instead of Claude Code, do the conversations there but run the stages on a real machine with a terminal; a sandboxed VM with a call ceiling turned a 5-minute step into 45 on the first run.

## 4. Done

The build is done when: the final render passes its checks (frame count exact, wrap identical, moving-tile cap respected, output format correct), the owner has watched it end to end, the launcher has been double-clicked on the display machine, a backup copy exists, the day-of checklist in `references/09-runbook.md` is complete, and the project folder holds the brief with its changelog, the index, the change log and the hours. After the event, run the post-event steps in the runbook: archive, reconcile, and write the retrospective.
