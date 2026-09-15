#!/bin/sh
# Slideshow launcher for macOS, browser edition: for [machines] player = "browser", or the fallback when VLC is not there.
# Double-click to start. Opens the live player (player.html, written by bin/build) in Google Chrome's kiosk mode: fullscreen,
# no browser chrome, sound allowed without a click (so the music the build put in the manifest starts at once), and keeps
# the Mac awake for as long as this window is open. LEAVE THIS TERMINAL WINDOW OPEN. To stop: Cmd+Q in Chrome.
# Keys in the player: space pauses, [ and ] change the speed, M mutes the music, F leaves fullscreen.
#
# Where the page comes from, in order: $SLIDESHOW_PAGE if set; player.html next to this script; <project>/build/player.html
# when this script sits in the project's build folder. Chrome is found the way bin/live finds it: the app in /Applications
# or ~/Applications, else google-chrome on the PATH. It runs on its own profile folder, so a Chrome that is already open
# with the owner's tabs is left alone and the kiosk flags take effect.
DIR=$(cd "$(dirname "$0")" && pwd)
PAGE="${SLIDESHOW_PAGE:-}"
[ -n "$PAGE" ] && [ ! -f "$PAGE" ] && PAGE=""
[ -z "$PAGE" ] && [ -f "$DIR/player.html" ] && PAGE="$DIR/player.html"
[ -z "$PAGE" ] && [ -f "$DIR/../build/player.html" ] && PAGE="$(cd "$DIR/../build" && pwd)/player.html"
if [ -z "$PAGE" ]; then
  echo "player.html not found next to this script or in ../build (run bin/build in the project first, or set SLIDESHOW_PAGE to its path)."
  echo "Press Return to close."; read -r _; exit 1
fi
CHROME=""
for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" "$HOME/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; do
  [ -x "$c" ] && CHROME="$c" && break
done
[ -z "$CHROME" ] && command -v google-chrome >/dev/null 2>&1 && CHROME=$(command -v google-chrome)
if [ -z "$CHROME" ]; then
  echo "Google Chrome is not installed on this Mac. Install it from https://www.google.com/chrome/ then run this again."
  echo "Press Return to close."; read -r _; exit 1
fi
PROFILE="${TMPDIR:-/tmp}/slideshow-kiosk-profile"
echo "Opening $PAGE in Chrome kiosk mode"; echo "Keep this window open (it holds the Mac awake). Cmd+Q in Chrome to stop."
set -- --kiosk --autoplay-policy=no-user-gesture-required --disable-features=TranslateUI --no-first-run --user-data-dir="$PROFILE" "file://$PAGE"
if command -v caffeinate >/dev/null 2>&1; then exec caffeinate -dis "$CHROME" "$@"; fi
exec "$CHROME" "$@"
