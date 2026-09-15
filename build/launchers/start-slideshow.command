#!/bin/sh
# Slideshow launcher for macOS. Double-click to start.
# Opens VLC fullscreen on the rendered file, looping, no OSD, sound on (a silent render plays nothing; a render with
# music plays it, so set the venue's volume first), and keeps the Mac awake for as long as this window is open.
# LEAVE THIS TERMINAL WINDOW OPEN. To stop: press Esc in VLC, then Cmd+Q.
#
# Where the file comes from, in order: $SLIDESHOW_FILE if set; next to this script; <project>/build when this script
# sits in the project's build folder; any mounted USB stick. In each place the concatenated render slideshow-x<N>.mp4
# (bin/render --concat; the first in name order when there are several) is preferred, then the single loop slideshow.mp4.
DIR=$(cd "$(dirname "$0")" && pwd)
find_show() {   # prints the first slideshow-x*.mp4 (name order) in the folder given, else its slideshow.mp4; fails with neither
  for f in "$1"/slideshow-x*.mp4; do [ -f "$f" ] && { echo "$f"; return 0; }; done
  [ -f "$1/slideshow.mp4" ] && { echo "$1/slideshow.mp4"; return 0; }
  return 1
}
# A show that plays once must not be told to repeat. bin/build writes playback.txt (loop | once) into the build
# folder; copy it to the stick beside the video. Without it the show loops, as it always has.
repeat_flag() {
  for d in "$(dirname "$1")" "$DIR" "$DIR/../build"; do
    [ -f "$d/playback.txt" ] && { [ "$(tr -d " \t\r\n" < "$d/playback.txt")" = "once" ] && echo "" || echo "--repeat"; return 0; }
  done
  echo "--repeat"
}
FILE="${SLIDESHOW_FILE:-}"
[ -n "$FILE" ] && [ ! -f "$FILE" ] && FILE=""
[ -z "$FILE" ] && FILE=$(find_show "$DIR")
[ -z "$FILE" ] && FILE=$(find_show "$DIR/../build")
if [ -z "$FILE" ]; then for v in /Volumes/*; do FILE=$(find_show "$v") && break; done; fi     # USB stick fallback
if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  echo "slideshow-x<N>.mp4 or slideshow.mp4 not found next to this script, in ../build, or on any USB stick. Set SLIDESHOW_FILE to its path."
  echo "Press Return to close."; read -r _; exit 1
fi
VLC=""
for c in /Applications/VLC.app/Contents/MacOS/VLC "$HOME/Applications/VLC.app/Contents/MacOS/VLC"; do
  [ -x "$c" ] && VLC="$c" && break
done
if [ -z "$VLC" ]; then
  echo "VLC is not installed on this Mac. Install it from https://www.videolan.org/ then run this again."
  echo "Press Return to close."; read -r _; exit 1
fi
pkill -x VLC 2>/dev/null; sleep 1
echo "Playing $FILE"; echo "Keep this window open (it holds the Mac awake). Esc then Cmd+Q in VLC to stop."
REPEAT=$(repeat_flag "$FILE")
[ -z "$REPEAT" ] && echo "playback.txt says once: VLC will play the show through and stop."
# shellcheck disable=SC2086
exec caffeinate -dis "$VLC" --fullscreen $REPEAT --no-osd --no-video-title-show "$FILE"
