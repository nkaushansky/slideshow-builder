@echo off
REM Slideshow launcher for Windows, browser edition: for [machines] player = "browser", or the fallback when VLC is not there.
REM Double-click to start. Opens the live player (player.html, written by bin\build) in Google Chrome's kiosk mode: fullscreen,
REM no browser chrome, sound allowed without a click (so the music the build put in the manifest starts at once).
REM To stop: Alt+F4 in Chrome. Keys in the player: space pauses, [ and ] change the speed, M mutes the music.
REM Turn off screen sleep in Windows power settings for the event; this launcher does not hold the display awake.
REM
REM Where the page comes from, in order: SLIDESHOW_PAGE if set; player.html next to this script; ..\build\player.html when
REM this script sits in the project's build folder. Chrome is found the way bin\live.cmd finds it (Program Files, Program
REM Files (x86), the per-user install). It runs on its own profile folder, so a Chrome that is already open with the owner's
REM tabs is left alone and the kiosk flags take effect.
setlocal
set "PAGE="
if defined SLIDESHOW_PAGE if exist "%SLIDESHOW_PAGE%" set "PAGE=%SLIDESHOW_PAGE%"
if not defined PAGE if exist "%~dp0player.html" set "PAGE=%~dp0player.html"
if not defined PAGE if exist "%~dp0..\build\player.html" for %%p in ("%~dp0..\build\player.html") do set "PAGE=%%~fp"
if not defined PAGE (
  echo player.html not found next to this script in %~dp0 or in ..\build ^(run bin\build in the project first, or set SLIDESHOW_PAGE to its path^)
  pause
  exit /b 1
)
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not defined CHROME (
  echo Google Chrome is not installed. Install it from https://www.google.com/chrome/ then run this again.
  pause
  exit /b 1
)
set "URL=file:///%PAGE:\=/%"
echo Opening %URL% in Chrome kiosk mode. Alt+F4 in Chrome to stop.
start "" "%CHROME%" --kiosk --autoplay-policy=no-user-gesture-required --disable-features=TranslateUI --no-first-run --user-data-dir="%TEMP%\slideshow-kiosk-profile" "%URL%"
exit /b 0
