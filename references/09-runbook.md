# Runbook: before, during and after the event

## Before the hard stop

- Additions cutoff the evening before the last render; one final render that night; the hard stop at least two days before the event so a found bug can be fixed and re-rendered (about two hours per render on older hardware).
- Test the launcher by double-clicking it on the display machine. It opens a terminal that must stay open, kills any running player, and starts the file fullscreen under the keep-awake tool, with a fallback to a copy on a USB stick. It does not mute: a silent file plays nothing, a file with music plays it, and the venue's volume is set by hand. In each place it searches (beside the script, the project's `build/`, any USB stick) it takes the first `slideshow-x*.mp4` in name order (the `--concat` output, `slideshow-x3.mp4` with the default copies), then `slideshow.mp4` (the single loop); a `-labels` test render and the `-silent` copy of a render with music are never picked. Keep one of those two names on the stick and delete stale copies, or the wrong one plays. Copy `build/playback.txt` (`loop` or `once`, written by `bin/build`) to the stick beside the video: the two `.command` launchers look for it beside the file they are about to play, then in the script's own folder, then in `../build`, and the Windows `.bat` in its own folder, which is where it plays the file from; each passes `--repeat` only when the marker says `loop`. Without it they repeat, as they always have - which is wrong for a show that ends, so a `once` show that is missing its marker plays its end card and starts again.
- Backups: the final file on the display machine, on a USB stick, and on one more machine. Two VLC launchers on the stick, one per operating system, that play the file from their own folder, and `playback.txt` beside them; if the browser is the fallback, a copy of the whole `build/` folder (`player.html` with its `tiles/`, `clips/` and `audio/`) with the browser pair inside it, since the page loads everything by relative path. The browser fallback needs no marker: `player.html` carries the playback mode and both cards in its own manifest, so it holds the title card, and under `once` it stops on the end card by itself.
- For a TV playing from a USB stick (`[machines] player = "tv-usb"`): the render used the H.264 profile and level such sticks decode, and it warns when a final file is 4 GiB or over, which a FAT32 stick refuses; use `[output] quality = "draft"`, fewer `concat_copies`, or an exFAT stick. Test the actual stick in the actual TV.
- With a title or an end card: play the file itself once, not only the loop, and read both cards on the screen from where the room will stand. They are their own segments at the two ends of the file, so a card that is wrong is a config change, a new `python curate/run.py show` and a re-render - budget for that before the hard stop.
- The owner's full watch of the final video, all the way through, on the display machine.

## Day-of checklist

- Display sleep off; screen saver off; notifications and focus modes silenced; automatic updates off; set the venue volume; a silent show makes no sound.
- Player: VLC, fullscreen, on-screen display off; repeat one, unless the show plays once, which is what `playback.txt` beside the video tells the launcher. The only audio track is the soundtrack the render muxed on, if any.
- A show that plays once ends on its end card and stays there. Agree with the owner who restarts it, and when.
- Outlet confirmed, cable taped, glare checked at the viewing angle, screen height and distance as planned.
- Who transports the machine, who sets up, who to call if it stops; a printed card with the launcher steps.
- Dry run on the actual machine in the actual room if at all possible, by the hard stop.

## If it stops during the event

1. Relaunch from the desktop launcher.
2. If the file is missing, the launcher looks for the copy on any mounted USB stick.
3. If VLC fails, double-click the browser launcher (`start-slideshow-browser.command` or `.bat`): it opens the live player in Chrome kiosk mode, music included; if the corner of the screen says "music: press any key", press one.
4. Nobody needs to watch it; check on it once an hour.

## After the event

- Archive: sources untouched, the working folder's records, the handoff, the change log, the brief with its changelog, the final video, the render logs. Delete derived copies (tiles, clips, frames) if the owner asked for that at intake, never the index or the log.
- Reconcile: if any records exist outside the project folder, regenerate them from the final index and the change log.
- Write the retrospective, in the same shape as the first run's so runs can be compared: what was built, timeline by date, what worked, what did not, numbers, answers to the standing questions (where the owner's time went; which checks caught what; what the intake missed), questions for the next run.
- Record the owner's hours and the elapsed days in an issue on the repository. That measurement is the project's next decision.
- Encore: the same file plays from a laptop over HDMI from a stick with the two launchers.
