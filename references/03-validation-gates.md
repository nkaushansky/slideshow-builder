# Validation gates

These run in the `validate` stage, after `index` and before anything is selected, and again whenever a date or pairing is about to be written. They write flags; they never fix silently. Every one of them exists because the first run wrote something wrong that the gate would have caught, and the wrong thing then traveled downstream as a rule.

## Gates on dates and pairings

1. **Second witness for any join on a filename stem.** Camera counters repeat across phones and wrap every 10,000 shots; in a two-device household over a decade, collisions are guaranteed. A stem match may pair a Live Photo, inherit a date, or link an export to an original only if a second witness agrees: timestamps within a few seconds (EXIF versus container versus sidecar), the same camera make and model, or pixel similarity (perceptual hash for still-to-still; first-frame hash for a video half or an animation). Absent a witness, do not join, and flag `stem-collision`.

2. **Era plausibility.** Reject a settled date that the file could not have: HEIC or HEVC before 2017; a camera model that did not exist in the claimed year; a resolution or file size the era could not produce; a Live Photo before late 2015. Flag `era-implausible`. This gate alone would have caught three of the first run's five wrong dates, at zero cost.

3. **Prefix versus intact metadata.** If the settled date disagrees with the file's own intact EXIF or sidecar time, the row must name a specific witness (the matched file, the method, the distance). "Re-export stamp" or any other unverified story is refused. Flag `prefix-exif-disagree` until a witness is cited.

4. **Live Photo pair validation.** The video half is 1 to 4 seconds long; its container creation time is within ±2 seconds of the still's capture time; the closest of the frames sampled across the clip is within 16 bits of the still on a 64-bit perceptual hash (the still is a key frame from inside the clip, so the first frame alone is not the witness; on real pairs the closest frame sits at 8 to 10 bits, unrelated frames at 22 or more). All three, or flag `pair-unverified` and treat the two files as separate items.

5. **Export title collisions.** When indexing a Takeout, key by member path, not by the title inside the sidecar; an export keeps the original title even when it renames the member with a `(1)` suffix. If two sidecars in one folder share a title, quarantine both from any automatic date or pairing decision. Flag `title-collision`.

6. **Owner corrections carry a confidence.** A date or fact supplied from memory is written with `date_source = owner` and a provisional mark until a second source agrees. On the first run, owner memory was right about a folder rule, a pinned photo and a recurring place, and wrong about the year of a trip; the fix was provenance, not distrust.

7. **"Content match" means a match ran.** The label is written only with the method and the distance recorded in the evidence. A hypothesis is written as a hypothesis, in the flags, not in the index.

8. **Age and era outliers on sheets.** For a whole-life show, a reviewer looking at composition will not notice that a child in one photo is ten years older than the rest of the page. Sort each period's sheet by estimated age, or highlight outliers, so the eye is drawn to them.

## Gates on the sources and the folder

9. **Copy, never move; quarantine, never delete; keep the export until after the event.** The first run deleted 163 GB of export zips the day integration finished, with 391 GB free, and lost the ability to re-check a pairing within the day.

10. **The working folder is not on a synced drive.** Warn at Step 0.

## Gates on the build side

11. **Verify derived sequences by content.** A frame sequence that is complete by count may be padded copies of one frame. Count distinct frames; a padding fallback fails past a small threshold and reports what it padded.

12. **Window renders around every special case.** Slow-motion clips, HDR clips, the longest videos, the loop wrap. A 60-second test render from the start of the loop covers nothing in the middle.

13. **The full watch.** The soak test measures dropped frames. Only a human watching the whole loop sees a frozen tile.

## What a flag looks like

`flags.csv`: `media_id, filename, gate, severity, detail, suggested_action, resolved_by, resolved_on`. Severity `block` stops the stage that depends on the value; `warn` goes to the sheets. Resolutions are dated changelog entries in the brief.
