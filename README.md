# slideshow-builder

A Claude skill that turns a photo export into a looping photo-mosaic slideshow for an event, or a curated set you can use for a gallery or album. Claude does the heavy work: ingesting and indexing the export, dating and de-duplicating, selecting the strongest moments with several complementary selection passes, laying them out as a scrolling mosaic, and rendering a video that loops on any screen. You do the part only you can do: answer a short set of questions at the start, approve contact sheets, and watch the result once before the event.

It was built for one family's milestone celebration and run once, start to finish, from about 20,000 candidate files to a 15-minute loop of roughly 470 moments that played unattended for an afternoon. Everything learned on that run is written into the skill as rules, so your run should be shorter and smoother than the first one was.

## If you are Claude and someone pointed you at this page

A person has asked you to help them get started with this. Do this, in order:

1. **If you can run commands on their machine** (you are Claude Code, or another agent with a shell): check that `python` (3.11 or newer; `python3` on macOS), `node` (20 or newer) and Google Chrome are installed, and tell them what is missing with the download links in "Getting started" below. Clone this repository into a plain local folder that is not inside a synced drive (OneDrive, iCloud Drive, Google Drive, Dropbox), or download and unzip it if `git` is absent. Run `python curate/setup.py` inside the folder, install whatever it reports missing, and re-run it until it prints "everything found". Then read `CLAUDE.md` and `.claude/skills/slideshow-builder/SKILL.md` in the clone and follow the skill, beginning with the intake questions in one message. If your session cannot pick up a skill from a folder it was not started in, ask the person to open a terminal inside the folder, run `claude`, and say "Let's build a slideshow from my photos."
2. **If you cannot run commands on their machine** (you are a chat window): explain that this needs Claude Code on the computer that holds the photos, with a Pro or higher subscription. Walk them through "Getting started, step by step" below, or have them install Claude Code and paste the paragraph under "If you would rather hand the setup to Claude" into it.

Do not skip the intake, do not touch their photos before it is answered, never upload a photo anywhere, and never open a photo, a tile, a frame or a contact sheet with an image-reading tool. The rules in `CLAUDE.md` apply to you.

## What you need

- A **Claude subscription** (Pro, Max, Team or Enterprise) and **Claude Code** on the machine that holds your photos. The skill runs scripts, so a chat-only setup is not enough. The free plan does not include Claude Code.
- **Python 3.11 or newer**, **Node.js 20 or newer**, and **Google Chrome** on the build machine. **ffmpeg** too; on Windows the setup step downloads it for you.
- **VLC** on the machine that will show the slideshow, if it is a different machine; or a TV that plays an mp4 from a USB stick; or only Chrome, for the browser player.
- Free disk space of at least twice the size of your export.
- Your photos as a **Google Takeout** (best, because its metadata sidecars carry capture times, places and people; zipped or unzipped), an **Apple Photos** export (File > Export > Export Unmodified Originals, with "Export IPTC as XMP" ticked, so dates, places and the names of people travel with the files), or a folder tree. Accepted files: JPEG, HEIC/HEIF, PNG and WebP stills; MOV, MP4, M4V, AVI, MKV, MTS/M2TS, 3GP, WebM, WMV and MPEG videos; animated GIFs. Anything else is set aside and listed, never lost.
- Music, if you want it: the files in play order (mp3, m4a, aac, wav, flac, ogg or opus); the render lays them under the video with fades, and they run across the loop seams.
- Words for a title card and an end card, if you want them, and a decision about whether the show loops all evening or plays through once and stops. Both are questions at the intake, and both have defaults.
- Git is optional. You can download the code as a zip instead.

## Getting started, step by step

Budget about an hour for steps 1 to 3, most of it downloads: roughly a gigabyte on Windows, and more on a Mac, where Homebrew installs Apple's command line tools before it installs ffmpeg. A slow connection makes it longer. Your photos never leave your machine; what Claude reads while it works is a different matter, and "Privacy" below says exactly what that is.

### 1. Install the tools, once

1. **Python.** Download from https://www.python.org/downloads/ and run the installer. On Windows, tick **"Add python.exe to PATH"** on the first screen. On macOS the python.org installer is fine, or `brew install python` if you use Homebrew.
2. **Node.js.** Download the LTS version from https://nodejs.org/ and run the installer with the defaults.
3. **Google Chrome**, if it is not already installed: https://www.google.com/chrome/
4. **ffmpeg** on macOS: `brew install ffmpeg` (Homebrew is at https://brew.sh/). On Windows, skip this; setup fetches a static build into the repository's `tools/` folder.
5. **VLC** on the machine that will play the show: https://www.videolan.org/
6. **Claude Code.** Open a terminal (Windows: PowerShell; macOS: Terminal) and run the installer for your system, then sign in with your Claude account when it asks:
   - Windows PowerShell: `irm https://claude.ai/install.ps1 | iex`
   - macOS: `curl -fsSL https://claude.ai/install.sh | bash`
   - Other options (WinGet, Homebrew, npm) and troubleshooting: https://code.claude.com/docs/en/setup

Close and reopen the terminal after installing so the new commands are found. `python --version` (macOS: `python3 --version`), `node --version` and `claude --version` should each print a version. On Windows, if `python` opens the Microsoft Store instead of printing a version, the "Add python.exe to PATH" box was missed: either re-run the Python installer and tick it, or use `py -3` in place of `python` in every command on this page, which works whether or not the box was ticked.

### 2. Get this repository

Put it in a plain local folder. On Windows 11 the Documents folder is usually synced to OneDrive, so pick somewhere outside it, such as `C:\slideshow-builder`; on a Mac `~/slideshow-builder` is fine. Not inside OneDrive, iCloud Drive, Google Drive or Dropbox: synced folders fight the build and the cleanup.

- **With Git:** `git clone https://github.com/nkaushansky/slideshow-builder.git`
- **Without Git:** open https://github.com/nkaushansky/slideshow-builder in a browser, click the green **Code** button, choose **Download ZIP**, unzip it, and rename the folder from `slideshow-builder-main` to `slideshow-builder`.

### 3. Run setup, once

Open a terminal **inside that folder** (Windows: in File Explorer, right-click the folder and choose "Open in Terminal", or type `cd C:\slideshow-builder`; macOS: `cd ~/slideshow-builder`) and run:

```
Windows:   python curate\setup.py
macOS:     python3 curate/setup.py
```

Setup refuses to run on Python older than 3.11 and says so in one sentence, and warns on 3.14 or newer, which is past the versions its pinned dependencies and its model export were tested against. It then creates a private Python environment in the folder, installs those dependencies, on Windows downloads ffmpeg (about 170 MB), installs the browser automation the render uses (a few hundred MB), and last of all fetches the two detection models, a person detector and a face detector. Only about 13 MB of model stays on disk, but making the person detector downloads the ultralytics package and torch into a throwaway environment first: several hundred megabytes, and a few minutes on a good connection. That step runs last on purpose and can no longer end setup. A pip or download failure there is a warning naming the model, everything else is already installed, the table still prints, and the pipeline runs without the models, because `identify --tags-only` reads the people tags your export already carries and the family gate works from those; only the gate that counts people in the frame needs the detector. `--skip-models` leaves them out from the start. Setup ends with either `everything found` or a `missing:` line that says what to install. A missing Playwright package counts as missing, because the render cannot start without it; VLC is a note with its download link instead, because it is needed only on the machine that shows the slideshow. Re-run setup after installing anything; it skips what is already done.

### 4. Start Claude Code in the folder and ask

In the same terminal, still inside the folder, run:

```
claude
```

Then type:

> Let's build a slideshow from my photos.

Because you started it inside the folder, Claude reads the skill in this repository, and starts with the intake: one message of questions about where the photos are, what machine builds and what machine shows the slideshow, the event and the room, who the show is about, the scope, and a few taste questions with sensible defaults in brackets. Answer them in one reply; "default" is a fine answer for any of them. Claude then writes the project folder, checks the machine (it detects your timezone and your screen's resolution and records them, and asks only for what it could not detect), and works through the stages.

If you would rather not use a terminal for this part, the Claude Code desktop app does the same thing: choose **Local** as the environment and this folder as the project folder, then type the same sentence.

### 5. What happens next

You will be asked to look at things three times, and each one is a real stop:

1. **Contact sheets** of the proposed cut, one per year, numbered, so you can approve or swap by number. About an hour of your time. If you are not at the machine, Claude bundles them into one PDF; it is written on the build machine like everything else, so moving it to wherever you are is your step, and the answers come back through the session.
2. **The live player**, one round: it opens in Chrome, you click any tile you want swapped, and the swaps go through a change log. If you are not at the machine, a short labelled test render stands in: every tile carries its name and date, so you can name what to swap from the video.
3. **The final video**, watched once all the way through before the event.

Everything lands in a `project/` folder beside your export: the index, the sheets, the frozen set, the build and the render. A full render writes `slideshow.mp4`, one loop; asking for the concatenated copies as well writes `slideshow-x3.mp4`, three copies of the loop back to back so the player's own seam comes rarely, and the count is a setting. A show that plays through once and stops is never concatenated: the render refuses that combination, because copies of a show that ends are not a show. Getting a launcher next to the video is a step you or Claude take by hand; nothing copies one for you. The launchers live in `build/launchers/`, and `references/09-runbook.md` says which to copy where. On a Mac, `start-slideshow.command` plays the file fullscreen and looping in VLC and holds the Mac awake while it runs; it looks for the video beside itself, then in the project's `build/`, then on any mounted USB stick. Windows has a USB-stick edition that plays whatever sits in its own folder and a browser edition that opens the player in Chrome kiosk mode, and no plain edition; neither Windows launcher holds the machine awake, so turn screen sleep off yourself. Wherever a launcher looks, it takes the first `slideshow-x*.mp4` in name order and falls back to `slideshow.mp4`. Copy `build/playback.txt` beside the video too: that is the marker the build writes, and it is what stops a launcher repeating a show that plays once. A launcher that came out of a downloaded zip is treated as untrusted the first time you double-click it, by Gatekeeper on a Mac and by SmartScreen on Windows; the runbook says how to get past each, and it is worth doing before the event rather than in front of the room. If you asked for a title card or an end card, they are in the file as their own segments at either end. If you gave music, it is on that file, fading in at the start and out at the end, and the launcher plays it at whatever volume the venue sets. For a TV playing from a USB stick, the render picks the H.264 level such sticks decode and warns when the file is too big for a FAT32 stick. After the event, the runbook says what to delete and what to keep.

### If you would rather hand the setup to Claude

Install Claude Code (step 1, item 6), open a terminal anywhere, run `claude`, and paste this:

> Clone https://github.com/nkaushansky/slideshow-builder into a plain local folder that is not synced to a cloud drive (or download and unzip it if git is missing). Run `python curate/setup.py` inside it (`python3` on macOS), install anything it reports missing, and re-run until it says everything is found. Then read the repository's CLAUDE.md and start the slideshow-builder skill by asking me the intake questions.

Claude will do steps 2 and 3, tell you what it could not install itself, and then begin the intake.

## What to expect

| | First run | Target for your run |
|---|---|---|
| Elapsed time | 7 days across three machines | 2 to 3 days on one machine |
| Your time | 9 to 16 hours | 3 to 4 hours |
| Contact sheets to approve | 74 | about 15, plus alternates on request |
| Render time for a 15-minute loop | about 100 minutes on 2017-era hardware | depends on your machine |

The second column is a target, not a measurement: it is the first run's numbers minus what the rules in the skill were meant to save, and no second run has been measured yet. If you finish one, those are the numbers to send back.

The loop length is an output, not a setting: it falls out of how many moments you keep and how fast the mosaic scrolls. The loop length you ask for at the intake sizes the cut the other way round, at about two seconds per moment at medium tiles.

## Privacy

Your photos and videos never leave your machine. There are no photos in this repository, the scripts make no network calls except setup's downloads, and the render is local. Claude is the part that is not local: what it reads while it works, which is file names, dates, places, people tags, captions, your intake answers and the output of the stages, goes to Anthropic like any other Claude conversation, under the data policy of the plan you are on. The pixels themselves stay here, because Claude is told never to open a photo, a tile, a frame or a contact sheet with an image-reading tool; the owner's eyes decide what a picture shows. Derived copies (tiles, clips, frames, the render) live in your project folder, and the skill tells you what to delete afterwards.

## Support and boundary

This is shared as-is, and Claude will adapt it to your machine as it goes; that is expected. What has actually been run: the first run's scripts went end to end once, on one real library, on the machines they were written for. Since the port, the whole path ran on Windows against a 50-file sample of a real library, and every version after that ran on Linux against synthetic exports, the build and the render included. A real Google Takeout zip has never been run end to end, on any platform, and neither has macOS. If something breaks or a rule turns out wrong, open an issue describing what happened and what Claude did about it. If you complete a run, please note your elapsed days and your own hours in an issue too: that measurement is what decides where this project goes next.

## Layout

```
CLAUDE.md                          how Claude should behave in this repo
.claude/skills/slideshow-builder/  the skill: intake, stages, checkpoints, hard rules
references/                        the contracts, algorithms, gates, templates and lessons
curate/                            the curation stages (Python); setup.py lives here
build/                             the mosaic build, player and render (JavaScript)
CHANGELOG.md                       what changed, by version
```

License: see `LICENSE`.
