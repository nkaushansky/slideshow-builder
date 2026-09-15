---
name: slideshow-builder
description: Build a looping photo-mosaic slideshow, or a curated photo set for a gallery or album, from a Google Takeout, an Apple Photos export or a folder of photos. Use when the user wants a slideshow for an event, a "best of" selection from years of photos, a themed set (a trip, a person, a tradition), or a gallery from their photo library. Starts with an intake, runs the curation and build stages, and stops at owner checkpoints.
---

# slideshow-builder

You are building a photo slideshow or a curated set from the user's own photos, on their machine. The process has nine stages, three owner checkpoints, and a short list of hard rules. Read this file fully before starting. The references hold the detail; this file holds the order and the stops.

## 0. Intake, before anything else

Do not touch a file until the intake is answered. Ask all of the questions below in **one message**, grouped as shown, with the default in brackets where one exists. Accept "default" as an answer. Then write the answers to `project/intake.md` and the machine-readable parts to `project/config.toml`. The full question set with the reasoning behind each is in `references/00-intake.md`; ask it as written.

**Source**
1. Where are the photos, and in what form: Google Takeout zips, an Apple Photos export, iCloud download, a folder tree, or a mix? Give the path or paths.
2. Roughly how many files and how many years, if you know.
3. Are there other sources with photos that should be considered: other family members' phones, an old backup, printed-calendar exports, shared albums?

**Machines**
4. What machine will run this build: operating system and version, chip, memory, free disk?
5. What machine will show the slideshow, if different: operating system, screen size and resolution, and how it will play (VLC, a browser, a TV)? [the build machine; Step 0 detects its display] The answer lands in `[output] resolution` and `[output] fps` in `config.toml`; when the display is the build machine, leave the resolution to Step 0.
6. Are Python, Node, ffmpeg and Google Chrome installed on the build machine? [I will check; answer only if you know something is missing]

**The show**
7. What is the event, the date, and the hard stop for a finished file? [hard stop = two days before]
8. Where will the screen be, how far away will people stand, will anyone be attending it, how long does it need to run, and is there internet? [unattended, offline, the length of the reception] Tile size small, medium or large? [medium; large for a wall seen from across the room]
9. Who owns the room's sound? Should the slideshow have audio? [no audio; music is planned, so say what you want and it is recorded]

**The people**
10. Who is the show about: one honoree, a couple, a family? Name the people who "count" as family for the selection, so that photos with none of them in frame can be dropped. A show with no people requirement (a place, a trip's scenery) sets the people gate to `none`.
11. Can you provide 5 to 20 clear photos of each of those people, or does your Takeout already carry people tags? [both, if possible]

**Scope and theme**
12. Which years or dates? [the honoree's whole life, or the whole export]
13. Is this a whole-life show, or a theme: a trip, a sport, a tradition, a place, a group of people? [whole life]
14. Any must-include photos or events, and anything off limits? [none; the family decides what is off limits] Either list takes filenames, media ids, or a folder of photos. Off-limits files are excluded by select and refused by the apply tool; must-include files are seated like pins.
15. How many moments do you want on screen, roughly, or should the cap fall out of the loop length? [a cap per year, pro-rated for partial years; about 450 to 500 moments for a 15-minute loop]

**Taste** (defaults are what worked on the first run)
16. Mixed tile sizes with occasional larger tiles, no full-screen singles? [yes] (recorded; this version does not act on it)
17. Live Photos play in full, videos play silently, nothing pauses the scroll? [yes] (recorded; this version does not act on it: Live Photos always play in full and clips are always silent)
18. Chronological within short chapters that each sweep the whole span, rather than one long timeline? [yes]
19. Captions? [none] (recorded; this version does not act on it)
20. Anything else you already know you want or hate? Verbatim.

**Time and privacy**
21. How many hours can you give to reviewing contact sheets and watching the loop? [3 to 4 hours total]
22. Where should the working folder live, and what should be deleted when the event is over? [beside the export; delete derived copies, keep the index and the final video]
23. Consent: nothing leaves the machine, and you are entitled to use these photos for this purpose. [confirm]

After the answers, run **Step 0, the environment check**, from `references/01-stages.md`: `python curate/setup.py --project <folder> --apply` detects the operating system, Python, Node, ffmpeg, Chrome and VLC with versions, checks disk space, detects the machine's timezone and the logical resolution of its display, and writes them, with `[machines] build_os`, into `config.toml` where the intake left them blank. Ask for whatever it could not detect. Look inside the export for sidecars and HEIC/HEVC share, and report what you found and what must be installed, with pinned versions. Then fill `references/07-decided-brief-template.md` into `project/BRIEF.md`. From here on, every decision is a dated line in the brief's changelog.

## 1. The stages

Run them in order. Each stage is a command in `curate/` or `build/`; each reads and writes the project folder and is resumable. Details, inputs, outputs and benchmarks are in `references/01-stages.md`. If a stage script is missing or fails on this machine, implement or repair it from the references before continuing, and say so in the changelog.

| Stage | What it does | Who acts |
|---|---|---|
| ingest | Copy, never move, into one flat working folder; hash every file; assign stable IDs; verify by flags | Claude |
| index | Sidecars first, then EXIF, container times, dimensions after orientation, duration, codec, perceptual hash, sharpness; pair Live Photos; find bursts and duplicates; settle a date with precision, confidence and a witness | Claude |
| validate | The gates in `references/03-validation-gates.md`; writes flags, never silently fixes | Claude, owner resolves flags |
| identify | Who is in frame: people tags from the export plus face embeddings from the seed photos; person area and group size | Claude |
| select | Build the candidate pool from the scope or theme, apply the cap, run the four lenses and the consensus pass, choose featured picks | Claude |
| review | Numbered contact sheets of the proposed cut, approval and edits by number, alternates on request; a PDF of the sheets for an owner who is not at the machine | **Owner checkpoint 1** |
| handoff | Freeze the set as the index contract: `media/`, `media.csv`, `features.txt`, `cut-list.csv`, `inventory.md`, `HANDOFF.md`, `show.json`; the accounting invariant must balance | Claude |
| build | Prepare tiles and clips, build the sequence and rows, open the live player for one review round, apply flags through the change ledger | **Owner checkpoint 2** |
| render | Test render (labelled when the owner is not at the machine), full render of exactly one loop with the wrap proved, concat for playback, soak, launcher; then the full watch | **Owner checkpoint 3** |

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
