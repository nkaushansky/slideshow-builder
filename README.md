# slideshow-builder

A Claude skill that turns a photo export into a looping photo-mosaic slideshow for an event, or a curated set you can use for a gallery or album. Claude does the heavy work: ingesting and indexing the export, dating and de-duplicating, selecting the strongest moments with several complementary selection passes, laying them out as a scrolling mosaic, and rendering a video that loops on any screen. You do the part only you can do: answer a short set of questions at the start, approve contact sheets, and watch the result once before the event.

It was built for one family's milestone celebration and run once, start to finish, from about 20,000 candidate files to a 15-minute loop of roughly 470 moments that played unattended for an afternoon. Everything learned on that run is written into the skill as rules, so your run should be shorter and smoother than the first one was.

## If you are Claude and someone pointed you at this page

A person has asked you to help them get started with this. Do this, in order:

1. **If you can run commands on their machine** (you are Claude Code, or another agent with a shell): check that `python` (3.11 or newer; `python3` on macOS), `node` (20 or newer) and Google Chrome are installed, and tell them what is missing with the download links in "Getting started" below. Clone this repository into a plain local folder that is not inside a synced drive (OneDrive, iCloud Drive, Google Drive, Dropbox), or download and unzip it if `git` is absent. Run `python curate/setup.py` inside the folder, install whatever it reports missing, and re-run it until it prints "everything found". Then read `CLAUDE.md` and `.claude/skills/slideshow-builder/SKILL.md` in the clone and follow the skill, beginning with the intake questions in one message. If your session cannot pick up a skill from a folder it was not started in, ask the person to open a terminal inside the folder, run `claude`, and say "Let's build a slideshow from my photos."
2. **If you cannot run commands on their machine** (you are a chat window): explain that this needs Claude Code on the computer that holds the photos, with a Pro or higher subscription. Walk them through "Getting started, step by step" below, or have them install Claude Code and paste the paragraph under "If you would rather hand the setup to Claude" into it.

Do not skip the intake, do not touch their photos before it is answered, and never upload a photo anywhere. The rules in `CLAUDE.md` apply to you.

## What you need

- A **Claude subscription** (Pro, Max, Team or Enterprise) and **Claude Code** on the machine that holds your photos. The skill runs scripts, so a chat-only setup is not enough. The free plan does not include Claude Code.
- **Python 3.11 or newer**, **Node.js 20 or newer**, and **Google Chrome** on the build machine. **ffmpeg** too; on Windows the setup step downloads it for you.
- **VLC** on the machine that will show the slideshow, if it is a different machine.
- Free disk space of at least twice the size of your export.
- Your photos as a **Google Takeout** (best, because its metadata sidecars carry capture times, places and people), an **Apple Photos** export, or a folder tree.
- Git is optional. You can download the code as a zip instead.

## Getting started, step by step

Budget about half an hour for steps 1 to 3, most of it downloads. Everything runs on your machine; no photo leaves it.

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

Close and reopen the terminal after installing so the new commands are found. `python --version` (macOS: `python3 --version`), `node --version` and `claude --version` should each print a version.

### 2. Get this repository

Put it in a plain local folder such as `C:\Users\<you>\slideshow-builder` or `~/slideshow-builder`. Not inside OneDrive, iCloud Drive, Google Drive or Dropbox: synced folders fight the build and the cleanup.

- **With Git:** `git clone https://github.com/nkaushansky/slideshow-builder.git`
- **Without Git:** open https://github.com/nkaushansky/slideshow-builder in a browser, click the green **Code** button, choose **Download ZIP**, unzip it, and rename the folder from `slideshow-builder-main` to `slideshow-builder`.

### 3. Run setup, once

Open a terminal **inside that folder** (Windows: in File Explorer, right-click the folder and choose "Open in Terminal", or type `cd C:\Users\<you>\slideshow-builder`; macOS: `cd ~/slideshow-builder`) and run:

```
Windows:   python curate\setup.py
macOS:     python3 curate/setup.py
```

Setup creates a private Python environment in the folder, installs the pinned dependencies, downloads the two detection models (a person detector and a face detector, about 13 MB), on Windows downloads ffmpeg (about 170 MB), installs the browser automation the render uses (a few hundred MB), and prints a table of every tool it found with its version. It ends with either `everything found` or a `missing:` line that says what to install. Re-run it after installing anything; it skips what is already done.

If Windows says `python` is not recognized after installing, try `py -3 curate\setup.py`, or re-run the Python installer and tick the PATH option.

### 4. Start Claude Code in the folder and ask

In the same terminal, still inside the folder, run:

```
claude
```

Then type:

> Let's build a slideshow from my photos.

Claude reads the skill in this repository and starts with the intake: one message of questions about where the photos are, what machine builds and what machine shows the slideshow, the event and the room, who the show is about, the scope, and a few taste questions with sensible defaults in brackets. Answer them in one reply; "default" is a fine answer for any of them. Claude then checks the machine, writes the project folder, and works through the stages.

### 5. What happens next

You will be asked to look at things three times, and each one is a real stop:

1. **Contact sheets** of the proposed cut, one per year, numbered, so you can approve or swap by number. About an hour of your time.
2. **The live player**, one round: it opens in Chrome, you click any tile you want swapped, and the swaps go through a change log.
3. **The final video**, watched once all the way through before the event.

Everything lands in a `project/` folder beside your export: the index, the sheets, the frozen set, the build and the render. The final file is `slideshow-x3.mp4`; a launcher script next to it plays it fullscreen and looping in VLC. After the event, the runbook in `references/09-runbook.md` says what to delete and what to keep.

### If you would rather hand the setup to Claude

Install Claude Code (step 1, item 6), open a terminal anywhere, run `claude`, and paste this:

> Clone https://github.com/nkaushansky/slideshow-builder into a plain local folder that is not synced to a cloud drive (or download and unzip it if git is missing). Run `python curate/setup.py` inside it (`python3` on macOS), install anything it reports missing, and re-run until it says everything is found. Then read the repository's CLAUDE.md and start the slideshow-builder skill by asking me the intake questions.

Claude will do steps 2 and 3, tell you what it could not install itself, and then begin the intake.

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

This is shared as-is. The scripts ran once on one library and once more on a small sample during the port, and Claude will adapt them to your machine as it goes; that is expected. If something breaks or a rule turns out wrong, open an issue describing what happened and what Claude did about it. If you complete a run, please note your elapsed days and your own hours in an issue too: that measurement is what decides where this project goes next.

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
