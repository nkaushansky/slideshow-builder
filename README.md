# slideshow-builder

A Claude skill that turns a photo export into a looping photo-mosaic slideshow for an event, or a curated set you can use for a gallery or album. Claude does the heavy work: ingesting and indexing the export, dating and de-duplicating, selecting the strongest moments with several complementary selection passes, laying them out as a scrolling mosaic, and rendering a video that loops on any screen. You do the part only you can do: answer a short set of questions at the start, approve contact sheets, and watch the result once before the event.

It was built for one family's milestone celebration and run once, start to finish, from about 20,000 candidate files to a 15-minute loop of roughly 470 moments that played unattended for an afternoon. Everything learned on that run is written into the skill as rules, so your run should be shorter and smoother than the first one was.

## What you need

- A Claude subscription (Pro or higher) with **Claude Code** installed on the machine that holds your photos. The skill runs scripts, so a chat-only setup is not enough.
- **Python 3.11 or newer**, **Node 20 or newer**, **ffmpeg**, and **Google Chrome** on the build machine. The skill checks for these first and tells you exactly what is missing, with pinned versions.
- **VLC** on the machine that will show the slideshow, if it is a different machine.
- Free disk space of at least twice the size of your export.
- Your photos as a **Google Takeout** (best, because its metadata sidecars carry capture times, places and people), an **Apple Photos** export, or a folder tree.

## Quick start

1. Clone this repository, run `python curate/setup.py` once (it creates a virtual environment, installs the pinned dependencies, fetches the detection models, and reports which tools are missing), then open Claude Code inside the folder.
2. Say: `Let's build a slideshow from my photos.`
3. Answer the intake questions. The skill asks everything it needs in one go: where the photos are, what machine builds and what machine displays, the event and the room, who the show is about, the scope, and a few taste questions with sensible defaults.
4. Let it run. You will be asked to look at things three times: the contact sheets of the proposed cut, one round in the live player, and the final video once, all the way through.

## What to expect

| | First run | Your run, if the rules hold |
|---|---|---|
| Elapsed time | 7 days across three machines | 2 to 3 days on one machine |
| Your time | 9 to 16 hours | 3 to 4 hours |
| Contact sheets to approve | 74 | about 15, plus alternates on request |
| Render time for a 15-minute loop | about 100 minutes on 2017-era hardware | depends on your machine |

The loop length is an output, not a setting: it falls out of how many moments you keep and how fast the mosaic scrolls.

## Privacy

Nothing leaves your machine. There are no photos in this repository and there is no cloud step. Derived copies (tiles, clips, frames, the render) live in your project folder, and the skill tells you what to delete afterwards.

## Support and boundary

This is shared as-is. The scripts ran once, on one library, and Claude will adapt them to your machine as it goes; that is expected. If something breaks or a rule turns out wrong, open an issue describing what happened and what Claude did about it. If you complete a run, please note your elapsed days and your own hours in an issue too: that measurement is what decides where this project goes next.

## Layout

```
CLAUDE.md                          how Claude should behave in this repo
.claude/skills/slideshow-builder/  the skill: intake, stages, checkpoints, hard rules
references/                        the contracts, algorithms, gates, templates and lessons
curate/                            the curation stages (Python)
build/                             the mosaic build, player and render (JavaScript)
CHANGELOG.md                       what changed, by version
```

License: see `LICENSE`.
