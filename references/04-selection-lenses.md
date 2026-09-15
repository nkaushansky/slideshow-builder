# Selection: the four lenses, consensus, and theme presets

The selection stage is the part of this project that generalizes furthest. It is a scoring pipeline over the index, not a judgment call, and it was the reason the first run's owner accepted a cut of about 470 moments on sight. Selection is autonomous; approval is the owner's, on numbered sheets.

## The shared frame

- **The cap.** N moments per period, pro-rated for partial periods (the first and last partial years of the scope, from the months of `[show] scope_start` and `scope_end`, else the birth month and the event month; or the length of a trip). By default it is derived from the loop length: the first run played 469 moments in a 15-minute loop at medium tiles and 100 px/s, 2.2 seconds per item, and that figure is scaled by the tile size (the base row height over 0.3611 of the screen height) and the scroll speed (the height's default pace, 100 px/s at 1440 rows, over the configured speed); `[show] loop_minutes_target` (15) in seconds over the seconds per item is the item count, and the cap is that count over the year-shares in scope (1.0 for a full year, months/12 for the partial first and last), rounded up, at least 1. A 15-minute target at medium tiles and 100 px/s over 19.5 year-shares gives 409 moments and 21 per year. `[selection] cap_per_year` set to a number above 0 replaces the derivation (the first run used 33) and nothing the derivation would need is read then - not the display settings, not `loop_minutes_target` - so those three numbers are `null` in `show.json` and the printed line is the cap alone; `[selection.cap_overrides]`, years as keys and whole numbers as values, replaces single years' caps after the pro-rating. The select stage prints the plan on one line, and `show.json` carries it under `selection`. The cap is a ceiling, not a floor; short buckets stay short.
- **A Live Photo pair costs one slot.**
- **Types the taste leaves out.** `[taste] include_videos = false` cuts every video, `include_gifs = false` every GIF and `live_photos = "still"` every Live Photo clip, with reason `excluded-type`; a Live Photo whose clip is cut competes as a plain still, with no motion seating.
- **Every candidate passes the people gate**, or the family gate when the identify stage ran. Configure which in `config.toml` (`[family] gate`). The family gate reads `family_present` from `people.csv`, which identify fills from the export's people tags (`identify --tags-only`, no models needed) or from its detection run, matching each tag against `[family] names` as the photo app spells them (equal case-insensitively, or a one-word name equal to the tag's first word); a file with no matching tag, or no tags at all, is cut `no-family`. When no row carries a `family_present` value at all, select refuses to run the gate and names the way to fill it: identify on an index that carries `people_tags` (`--tags-only`, `--force` to refresh rows already written), or the detection run when the export has no tags; when every row is answered and none says `yes`, it says that instead, because then the names and the tags disagree.
- **Diversity:** no pick within perceptual distance 26 of an already seated pick. A bucket with no dissimilar candidate is left short rather than forced; a forced-pick fallback let a pixel-identical duplicate into every cut on the first run until it was removed.
- **Pins:** an owner-pinned item is seated first and a date correction can never drop it. Adopted after a pinned photo fell out of a cut when its date moved.
- **Anchors:** recurring events the owner names, found by GPS, by date window, or by eye, seated before the general pool.

## The lenses

Each lens is a scoring function plus a seating order. They are deliberately different so that consensus means something.

**v1, quality.** Score = 0.6 × pixel-count percentile + 0.4 × sharpness percentile within the period. Seat by round-robin over months, best remaining shot first. "Best" means big and sharp.

**v2, people and motion.** Largest weight on person-area share (how much of the frame is people), a group bonus (person count capped at 6), one deliberate motion item per month (real video preferred, a Live Photo only if it is the month's only motion), and a novelty constraint: at least 50 percent different from v1. "Best" means the audience will see themselves.

**v3, breadth and traditions.** Tradition anchors seated first, then one photo per distinct day before any second photo from a day. "Best" means no day left behind. Known flaw: a chronological sweep spends day-rich periods on their first months; seat by round-robin over months, not by date order.

**v4, synthesis, the recommended default.** Pins, then anchors, then one motion item per month, then month round-robin over unused days, exact-day buckets before month-only and year-only buckets. Score = 0.40 person-area + 0.10 group + 0.20 sharpness + 0.15 resolution + 0.15 consensus, where consensus is how many of v1 to v3 chose the item; the weights are `[selection.weights]` (`person_area`, `group`, `sharpness`, `resolution`, `consensus`, each at least 0, normalised to sum 1 when they do not, and the stage says so). On the first run, 129 items chosen by all three earlier lenses were seated by v4 with three exceptions.

Operational definitions: faces = face-detector count (a gate and a small bonus); people = person-detector count; sharpness = Laplacian variance percentile; resolution = pixel-count percentile; variety = the distance-26 rule plus the round-robins. Nothing here scores expression, eye contact or composition: the sheets are the only place those are judged, which is why the sheets are a checkpoint and not a formality.

## Featured picks

About one in six of the stills, chosen by a quality score and then reviewed on one sheet with swaps. Favor: sharp, one or two clear subjects, strong color or composition, reads at a glance from across the room. Avoid: large groups, busy wide scenes, anything soft. Spread across periods with a minimum of two per period; include both orientations; Live Photo stills are eligible. The thresholds are `[selection.featured]`: `max_people` 3, `min_short_side` 1000, `min_long_side` 1500, `min_sharpness_pct` 0.10. Featured stills and every standalone video become the layout's anchors, so the count directly sets the share of large tiles (see `06-layout-motion-render.md`); do the arithmetic before the build, not after. `[taste] mixed_tiles = false` turns featured picks off (the fraction becomes 0 and the stage says so), and the build then treats no item as an anchor: every row is a base row.

## Theme presets

A theme is a query that builds the pool plus a reweighting of the lenses. Presets to start from:

| Theme | Pool | Lens changes |
|---|---|---|
| Whole life | every dated item in range | defaults |
| A trip | GPS cluster of days away from home, plus the travel days | v3 weight up: breadth per day; cap per day rather than per month |
| A sport or activity | album names, date windows, scene tags, a place | v2 weight up: motion and person-area; group bonus up; sharpness threshold relaxed for action blur only when the subject is sharp |
| Concerts, stage, low light | album names, dates, place | v1 sharpness percentile computed within the pool, not the library; resolution weight down |
| One person or a group | identify-stage presence of the named people, co-occurrence for groups | family gate becomes a filter; person-area weight up; group bonus for the named group only |
| Traditions | anchors by date window and place across years | one per year per tradition seated first; then breadth |

Scene tags for the sport and stage themes come from album names and dates first; if content tagging is used (a local zero-shot model on thumbnails, or Claude reading a sheet), every tag is confirmed on a sheet before it drives a cut, because guesses about photo contents were right less than half the time on the first run.

## Outputs

`selection.csv` with, per file: `selected`, `v1_rank`, `v2_rank`, `v3_rank`, `v4_rank`, `consensus`, `featured`, `pin`, `anchor`, `tag`. `cut-list.csv` with one-word reasons (`excluded-type` for the types the taste leaves out). Counts per period printed, with the cap line and a rough loop estimate at the plan's seconds per item.
