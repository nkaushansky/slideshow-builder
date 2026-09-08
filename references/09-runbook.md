# Runbook: before, during and after the event

## Before the hard stop

- Additions cutoff the evening before the last render; one final render that night; the hard stop at least two days before the event so a found bug can be fixed and re-rendered (about two hours per render on older hardware).
- Test the launcher by double-clicking it on the display machine. It opens a terminal that must stay open, kills any running player, and starts the file fullscreen under the keep-awake tool, with a fallback to a copy on a USB stick.
- Backups: the final file on the display machine, on a USB stick, and on one more machine. Two launchers on the stick, one per operating system, that play the file from their own folder.
- The owner's full watch of the final video, all the way through, on the display machine.

## Day-of checklist

- Display sleep off; screen saver off; notifications and focus modes silenced; automatic updates off; volume muted.
- Player: VLC, repeat one, fullscreen, on-screen display off, no audio track.
- Outlet confirmed, cable taped, glare checked at the viewing angle, screen height and distance as planned.
- Who transports the machine, who sets up, who to call if it stops; a printed card with the launcher steps.
- Dry run on the actual machine in the actual room if at all possible, by the hard stop.

## If it stops during the event

1. Relaunch from the desktop launcher.
2. If the file is missing, the launcher looks for the copy on any mounted USB stick.
3. If the player fails, open the browser player fullscreen on the same machine.
4. Nobody needs to watch it; check on it once an hour.

## After the event

- Archive: sources untouched, the working folder's records, the handoff, the change log, the brief with its changelog, the final video, the render logs. Delete derived copies (tiles, clips, frames) if the owner asked for that at intake, never the index or the log.
- Reconcile: if any records exist outside the project folder, regenerate them from the final index and the change log.
- Write the retrospective, in the same shape as the first run's so runs can be compared: what was built, timeline by date, what worked, what did not, numbers, answers to the standing questions (where the owner's time went; which checks caught what; what the intake missed), questions for the next run.
- Record the owner's hours and the elapsed days in an issue on the repository. That measurement is the project's next decision.
- Encore: the same file plays from a laptop over HDMI from a stick with the two launchers.
