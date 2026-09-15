#!/bin/sh
# Slideshow launcher for macOS, USB-stick edition. Double-click to start.
# Plays the rendered file from this same folder in VLC: fullscreen, looping, no OSD, no audio. The concatenated render
# slideshow-x<N>.mp4 (bin/render --concat; the first in name order) is preferred, then the single loop slideshow.mp4.
# Keeps the Mac awake for as long as this window is open. LEAVE THIS TERMINAL WINDOW OPEN.
# To stop: press Esc in VLC, then Cmd+Q. Set SLIDESHOW_FILE to play a different file.
DIR=$(cd "$(dirname "$0")" && pwd)
find_show() {   # prints the first slideshow-x*.mp4 (name order) in the folder given, else its slideshow.mp4; fails with neither
  for f in "$1"/slideshow-x*.mp4; do [ -f "$f" ] && { echo "$f"; return 0; }; done
  [ -f "$1/slideshow.mp4" ] && { echo "$1/slideshow.mp4"; return 0; }
  return 1
}
FILE="${SLIDESHOW_FILE:-}"
[ -n "$FILE" ] && [ ! -f "$FILE" ] && FILE=""
[ -z "$FILE" ] && FILE=$(find_show "$DIR")
if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  echo "slideshow-x<N>.mp4 or slideshow.mp4 not found next to this script in: $DIR (or SLIDESHOW_FILE does not exist)"; echo "Press Return to close."; read -r _; exit 1
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
