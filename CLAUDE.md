# slideshow-builder

Maintainer note: if a `_private/` folder exists here, you are the maintainer's session. Read `_private/BUILD-BRIEF.md` first; it describes the porting work and the rules for what may be committed. That folder is gitignored and never ships.

## What this repository is

A Claude skill, with its scripts and references, that builds a looping photo-mosaic slideshow (or a curated set for a gallery) from a photo export. The skill lives in `.claude/skills/slideshow-builder/SKILL.md`. When a user asks to build a slideshow, a gallery, an album or a curated set from their photos, follow that skill. Do not improvise a different process.

## How to behave here

- **Ask first, then run.** The skill opens with an intake. Ask every intake question before touching any file, in one message, with the defaults shown. Record the answers in the project folder. Do not assume the source, the machine or the taste.
- **One project folder, one ledger.** Every stage reads and writes the project folder. Every change to the set goes through the apply tool and is appended to the change log. Nothing in the user's sources is ever modified, renamed, converted or deleted.
- **Hard rules are not suggestions.** They are listed in the skill and explained in `references/08-lessons.md`. The ones people are most tempted to skip: never join two files by camera number without a second witness; reject dates that are impossible for the file; a fallback that can mask a failure must fail loudly; watch the final video once, all the way through.
- **Owner checkpoints are real stops.** Contact sheets, one live-player round, the full watch. Do not proceed past a checkpoint on your own judgment about the photos. Never guess what a photo shows; the owner's eyes decide.
- **If a stage script is missing or breaks on this machine, implement or repair it from the references.** `references/01-stages.md` and `references/04-selection-lenses.md` are complete enough to rebuild any stage. Keep the contracts in `references/02-index-contract.md` exact, because the build side depends on them.
- **Write the decided brief and keep its changelog.** Before building, fill `references/07-decided-brief-template.md` into the project folder from the intake and the environment check. Every later decision gets a dated line there, with what it superseded.
- **Dry-run before mutating.** Every mutating command has a dry-run mode. Use it.

## Layout

```
.claude/skills/slideshow-builder/SKILL.md   the procedure
references/00-intake.md                     what to ask, and what to detect instead of asking
references/01-stages.md                     the nine stages, inputs and outputs, benchmarks
references/02-index-contract.md             media.csv and the other files the stages exchange
references/03-validation-gates.md           the checks that run before any date or pair is written
references/04-selection-lenses.md           the four selection passes, consensus, theme presets
references/05-review-loop.md                sheets, flags, replacement rounds
references/06-layout-motion-render.md       the mosaic, the scheduler, the deterministic render
references/07-decided-brief-template.md     the brief the build runs from, with its changelog
references/08-lessons.md                    what went wrong on the first run, and the rules that came from it
references/09-runbook.md                    day-of checklist, backups, after the event
curate/                                     Python stages
build/                                      JavaScript build, player, render
```
