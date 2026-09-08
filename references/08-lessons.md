# Lessons from the first run

The first run built a whole-life slideshow for a family milestone: about 20,000 candidate files considered, about 470 moments kept, a 15-minute loop rendered twice, played unattended for an afternoon without anyone noticing the loop seam. It took seven calendar days across three machines and three Claude surfaces, about 15 hours of curation time and 9 to 16 hours of the owner's. Eight things went wrong; all were caught before the event, four of them by the owner's eyes. Every one is now a rule in the skill. This file explains why.

## What went wrong, and the rule it produced

**1. Five items dated or paired by camera number.** Three photos from one year inherited the dates of older photos with the same IMG number; a GIF inherited a date from a still with the same stem; an export "Live Photo pair" was two unrelated captures sharing a title. The renamer keyed its prefix map by filename stem; the export pairing keyed sidecars by title. An audit then chose the filename side over intact EXIF, labeled the rows "content match" although no match had run, and wrote a fictional mechanism into the handoff note. The build inherited "never re-derive from EXIF, several files carry wrong EXIF by design" as a ground rule, which switched off the one check that would have caught it. The owner found them in the live player. Rules: second witness for any stem join; era plausibility; prefix-versus-metadata is a flag with a named witness; "content match" means a match ran; a brief with a changelog, so an override reads as an override.

**2. A photo with no family member in it made the cut.** The people gate was "any human in frame", and the strongest lens rewarded person-area, which an unrelated adult filling the frame maximizes. Nothing asked "is this our person". Rule: presence is not identity; the identify stage; sheets say who the detector saw.

**3. The build brief was written for the wrong file count.** It was frozen against the first packaging while curation continued, and a rebuild from originals the same afternoon changed the count and the type mix. The item count survived; the file count and the video count did not, and the video count set the feature-row share, so the loop came out 15 minutes instead of 12. Rules: intake before the brief; counts as references to the index, not numbers in prose; the anchor arithmetic before the build; changelog.

**4. Most of a day on an old operating system's toolchain.** The package manager no longer supported the OS, the browser-automation library refused its own browser, the sandbox hung a headless browser, a standard command was missing, and a one-minute idle sleep killed a preparation run. The brief had asked about the machine; it had not pinned versions, and web search was available. Rules: Step 0 detects and pins; keep-awake around long runs; measure the screenshot path before designing the render.

**5. An overnight render before any review.** Obsolete by morning, with an imperfect wrap. Rules: render last; prove the wrap cheaply first; the build order puts the owner's round before the render.

**6. A frame-extraction bug found two days before the event.** A time window given in the wrong unit cut every slow-motion sequence to three seconds; a padding fallback silently copied the last frame hundreds of times; the completion marker recorded a full count; the test render, the render's own checks and a two-hour soak all passed. The owner found a frozen tile watching the finished video. Rules: fallbacks fail loudly past a threshold; verify derived sequences by content; window renders around every special case; the full watch.

**7. The curation index went stale across machines.** Two copies of the index, changes flowing one way. Each replacement round carried a change list generated on one machine and pasted into the other, and the curation side's records stayed wrong until a reconciliation pass after the event. Rules: one machine, one folder, one ledger; stable IDs; the return trip carries the index and the log.

**8. A replacement round applied from the wrong chat thread.** Two sessions on one machine; the project session did not know the set had changed until it read the change log. The data was right because the disk was the source of truth. Rules: every session starts by reading the ledger; one thread per project.

## Also worth knowing

- The export zips were deleted the day integration finished, with plenty of disk free; a pairing could not be re-checked a day later. Keep sources until after the event.
- An owner's recollection of a trip's year was wrong; GPS in the export settled it. Record owner facts with a confidence.
- Sixty contact sheets were made where fifteen would have done; most of the owner's sheet time went to alternates.
- Claude's guesses about what flagged photos showed were right four times in nine. Never guess; show a sheet.
- A sandboxed VM with a two-core limit and a call ceiling turned a five-minute hash sweep into forty-five and made every copy a chore. Run the heavy stages on a real machine.
- Context compaction in a long chat lost the verbatim text of a spec that lived only in the chat. Specs live in files from the first minute.
- A hover-to-play interaction appeared in a data-side note, written for a gallery, and had to be explicitly overridden by the build brief for an unattended screen. Data documents describe data; the brief decides interaction.
- The neutral, both-sides design brief was right for the design conversation and wrong as the build's input. Two documents: a neutral brief for design, a decided brief with a changelog for the build.

## What worked, and is kept exactly

- Copy never move; quarantine never delete; verify by flags after every pass.
- Metadata-first triage of the export: sidecars in seconds, pixels only for candidates.
- Perceptual-hash matching of exports to originals, which recovered real dates for hundreds of files and upgraded low-resolution copies.
- GPS as the tiebreaker for places and trips.
- Pins: a date fix can never drop a keeper.
- Four selection lenses with consensus as evidence; numbered sheets with drops below the line.
- The index contract with its accounting invariant.
- Determinism: one clock drives the live player, the render and the simulator; scheduling questions answered by simulation in a fraction of a second.
- Taste as knobs with printed trade-offs, not one-off edits.
- Cheap proofs before expensive steps: 60-second test renders and the wrap probe made the full render pass first time.
- Idempotent, resumable, dry-runnable tools; nothing in the handoff ever deleted, only moved aside.
- The owner's review style: flags with timestamps and one-line reasons, quick decisions, concrete taste statements. Ask for it explicitly.
- Rendering to a looping video instead of trusting a browser for four hours. The single most consequential decision.
- Mini-timelines: chronology, variety and the loop seam solved by one mechanism.
