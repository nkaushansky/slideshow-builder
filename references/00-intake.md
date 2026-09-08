# Intake: what to ask, and what to detect instead of asking

The intake exists because the first run learned most of these facts late, and each late fact cost a day or a rework: the machine's operating system surfaced after the brief was written, the target count changed after the brief was frozen, the honoree's family was never defined for the selection, and the owner's taste on Live Photos was argued about instead of asked. Ask everything below in one message before touching a file. Defaults are in brackets; they are what worked on the first run and are safe to accept.

## Ask

### Source
1. **Where are the photos, and in what form?** Google Takeout zips, an Apple Photos export, an iCloud download, a folder tree, or a mix. Paths.
   Why: the whole index stage depends on it. Takeout sidecars carry capture time, place and people tags and can be read without opening the zips; a folder of exports may have lost its metadata entirely and needs the date ladder.
2. **Roughly how many files, how many years?**
   Why: sizes the machine time and the cap.
3. **Other sources worth considering?** Another family member's phone, an old backup, printed-calendar or photo-book exports, shared albums.
   Why: on the first run a second phone's photos carried the same camera counters as the first, and a set of print exports had lost every timestamp. Knowing this up front turns a forensics phase into a plan.

### Machines
4. **Build machine:** OS and version, chip, memory, free disk.
   Why: an older Mac on an old OS cost most of a day of toolchain work on the first run; the brief had not asked.
5. **Display machine, if different:** OS, screen size and resolution, how it will play (VLC, browser, TV over HDMI).
   Why: the output resolution and the launcher depend on it. A 5K panel is driven at its logical resolution, not its physical one.
6. **Tools installed?** Python, Node, ffmpeg, Chrome. [Detect; ask only what cannot be detected]

### The show
7. **Event, date, hard stop.** [hard stop two days before the event]
   Why: the hard stop sets the additions cutoff and the last render. On the first run a bug was found the day of the hard stop and fixed the same afternoon; a day of slack is the difference between a fix and a failure.
8. **Room and run-of-show.** Where the screen sits, viewing distance, attended or unattended, how long it must run, whether there is internet. [unattended, offline, the length of the reception]
   Why: viewing distance sets the tile size and whether a bigger screen matters; unattended rules out anything that needs a click.
9. **Audio.** Who owns the room's sound? [no audio]

### The people
10. **Who is it about, and who counts as family for the selection?** Names and relationships.
    Why: the first run's people gate was "any human in frame", and one photo of an unrelated adult made the cut. The selection needs an identity, not a presence.
11. **Seed photos or tags.** 5 to 20 clear photos of each family member, or people tags in the export. [both]

### Scope and theme
12. **Years or dates.** [the honoree's whole life, or the whole export]
13. **Whole-life show or a theme?** A trip, a sport, a tradition, a place, a group. [whole life]
    Why: a theme changes the candidate pool and the lens weights (see `04-selection-lenses.md`).
14. **Must-include and off-limits.** [none; off-limits is the family's call, and the skill never decides it]
15. **How many moments, or let it fall out?** [a cap per year pro-rated for partial years; about 450 to 500 moments for a 15-minute loop]
    Why: loop length is an output of moment count and scroll speed. Pick the count as content, not as a runtime target.

### Taste (defaults are the first run's)
16. Mixed tile sizes with occasional larger tiles, no full-screen singles. [yes]
17. Live Photos play their whole clip and hold the last frame; videos play silently; nothing pauses the scroll or goes full screen. [yes]
18. Chronological inside short chapters that each sweep the whole span, so a two-minute glance covers every era. [yes]
19. Captions. [none; if the owner wants them, they are baked into tiles during preparation, not rendered live]
20. Anything else the owner already knows they want or hate. Verbatim.

### Time and privacy
21. **Owner hours available** for sheets and watching. [3 to 4 hours total]
    Why: drives the number of sheets and the number of review rounds.
22. **Working folder and cleanup.** Where derived copies live and what to delete afterwards. [beside the export; delete derived copies after the event, keep the index, the change log and the final video]
23. **Consent.** Confirm that nothing leaves the machine and that the owner is entitled to use these photos for this purpose. Do not upload photos to any service.

## Detect, do not ask

Run these in Step 0 and report the findings:
- OS and version, chip, memory, free disk on the build machine.
- Python, Node, ffmpeg, ffprobe, Chrome, VLC: present, path, version. Compare against the pinned versions in `01-stages.md`.
- Inside the export: whether Takeout sidecars exist and how many; share of HEIC stills and HEVC videos; presence of Live Photo pairs; longest videos; any 10-bit HDR video; any slow-motion (high frame rate) video; panoramas and extreme aspect ratios; tiny files.
- Whether the working folder is on a synced drive (Google Drive, iCloud Drive, OneDrive, Dropbox). Warn if so: synced folders fought both git and file deletion on the first run. Prefer a plain local folder.

## Write down

Save the answers as `project/intake.md` (prose, the owner's words kept verbatim where taste is concerned) and `project/config.toml` (paths, machines, dates, cap, theme, family names, defaults chosen). Then fill the decided brief from `07-decided-brief-template.md`. The intake answers are the brief's first changelog entries.
