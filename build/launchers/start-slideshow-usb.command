#!/bin/sh
# Slideshow launcher for macOS, USB-stick edition. Double-click to start.
# Plays slideshow-x3.mp4 from this same folder in VLC: fullscreen, looping, no OSD, no audio.
# Keeps the Mac awake for as long as this window is open. LEAVE THIS TERMINAL WINDOW OPEN.
# To stop: press Esc in VLC, then Cmd+Q. Set SLIDESHOW_FILE to play a different file.
DIR=$(cd "$(dirname "$0")" && pwd)
FILE="${SLIDESHOW_FILE:-$DIR/slideshow-x3.mp4}"
if [ ! -f "$FILE" ]; then
  echo "slideshow-x3.mp4 not found next to this script in: $DIR"; echo "Press Return to close."; read -r _; exit 1
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
echo "Playing $FILE"
echo "Keep this window open (it holds the Mac awake). Esc then Cmd+Q in VLC to stop."
exec caffeinate -dis "$VLC" --fullscreen --repeat --no-osd --no-video-title-show --no-audio "$FILE"
