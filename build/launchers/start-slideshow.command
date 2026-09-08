#!/bin/sh
# Slideshow launcher for macOS. Double-click to start.
# Opens VLC fullscreen on the rendered file, looping, no OSD, no audio, and keeps the Mac awake for as
# long as this window is open. LEAVE THIS TERMINAL WINDOW OPEN. To stop: press Esc in VLC, then Cmd+Q.
#
# Where the file comes from, in order: $SLIDESHOW_FILE if set; slideshow-x3.mp4 next to this script;
# <project>/build/slideshow-x3.mp4 when this script sits in the project's build folder; any mounted USB stick.
DIR=$(cd "$(dirname "$0")" && pwd)
NAME="slideshow-x3.mp4"
FILE="${SLIDESHOW_FILE:-}"
[ -n "$FILE" ] && [ ! -f "$FILE" ] && FILE=""
[ -z "$FILE" ] && [ -f "$DIR/$NAME" ] && FILE="$DIR/$NAME"
[ -z "$FILE" ] && [ -f "$DIR/../build/$NAME" ] && FILE="$DIR/../build/$NAME"
[ -z "$FILE" ] && FILE=$(ls /Volumes/*/"$NAME" 2>/dev/null | head -1)     # USB stick fallback
if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  echo "$NAME not found next to this script, in ../build, or on any USB stick. Set SLIDESHOW_FILE to its path."
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
exec caffeinate -dis "$VLC" --fullscreen --repeat --no-osd --no-video-title-show --no-audio "$FILE"
