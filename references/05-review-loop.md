# The review loop

The owner's time is the scarcest input and the only reliable judge of what a photo shows. The loop is designed so the owner looks at diffs and numbered choices, never at the whole library, and so every decision lands in the ledger without anyone retyping it.

## Contact sheets (checkpoint 1)

- **One sheet per period** (a year for a whole-life show, a day or a leg for a trip), thumbnails about 400 px wide so faces can be judged, each labeled with its date-prefixed filename and a short number. The sheets stay one per year whatever `[selection] period` counts in: a year is what an owner reviews in one sitting, and fifty-two week sheets are not. A year's header cap is then the sum of the caps of the periods inside it, so the count against the cap still reads true.
- **Proposed picks above a line, drops grayed below it.** The owner approves a whole period in a minute or edits by number: "swap 7 for D3", "drop 12".
- **Header per sheet:** the period, the count against the cap, which family members the identify stage saw, and any validation flags on that period, so the reviewer knows what to look for.
- **Captions are not on the sheets.** `[taste] captions` is a decision about the show, not about the review; the sheets carry the filename, the date and what identify saw, as they always have. Look at captions in the live player.
- **Age and era outliers highlighted** (see the gates). Composition is what a reviewer naturally judges; a child ten years too old for the page is not.
- **Sheet count.** Review the proposed cut only: about 15 sheets for a whole-life show. Offer alternates for any period on request rather than presenting every lens's full output. The first run put 60 year sheets in front of the owner, most of which were alternates; fifteen would have done.
- **Featured picks** get one sheet of their own, with swaps by number.
- Record the owner's edits verbatim in the brief's changelog, then re-run `select` with the edits as pins and exclusions.

## The live-player round (checkpoint 2)

- Open the live player fullscreen on the display machine, or the build machine if that is what is available, with review aids on: filename and date on every tile, period and time on every row, click-to-flag with a note. With `[taste] captions` on, every tile also carries its caption; with the labels on it sits at the top of the tile so both read.
- **The cards and the ending are part of this round.** The live player holds the title card before the scroll, and with `[show] playback = "once"` it stops after exactly one loop, holds the end card and freezes. Read both cards on screen at the size they will play; `player.html?card=title` and `?card=end` show one card alone, which is also the picture the render puts into the video. The flagging page never holds a card and never stops, so use the plain live player for this. A card that is too long to read at a glance is a config change and a new `python curate/run.py show`, not a build.
- Ask the owner to flag with a **timestamp and a one-line reason**: wrong era, wrong person, unflattering, duplicate feel, too small to read. Precise flags are what made the first run's loop fast; taste stated as a rule ("this decade after that one is fine, these two mixed is not") turns straight into a knob.
- For every flagged item, list **candidates from the cut list in the same weeks**, over-cap reason first, with their source paths; make one sheet per flag, the leaving item first, candidates numbered; the owner picks by number or says drop.
- Write `replacements.csv` (format in `02-index-contract.md`), dry-run the apply, show the plan, apply, rebuild, and show the owner the changed rows in the player. Seconds, not hours.
- Date and pairing corrections found here go through the redate and drop tools, never through editing the CSV.
- **Batch.** One round after the first build, one more after applying it if the owner wants. Every round re-deals the chapters, so the owner approves the order last.

## The full watch (checkpoint 3)

After the final render: the owner watches the whole loop once, at speed, on the display machine if possible. This is the only check that sees a frozen tile, a wrong-era jump, or a video that starts in the wrong place. The cards are in the file too, as their own segments at either end, so the watch starts and ends with them; with music the soundtrack covers them. Budget the time (a 15-minute loop) and the day (before the hard stop, not on it).

## If curation and build are on different machines

They should not be. If they must be, every round's return trip carries the regenerated `media.csv` and `changes.log`, and the far side regenerates its records from them before making sheets. Hand-typed change lists in a chat message are how the first run's curation records went stale the same day.

## Owner time budget

First run: 74 sheets at one to two minutes each, about 2 hours; five or more live-player sittings, 2 to 4 hours; decisions throughout. Target for this skill: about 1 hour of sheets, 1 to 2 hours in the player, the full watch. Ask the owner to write down their hours at each checkpoint; that number decides what this project becomes.
