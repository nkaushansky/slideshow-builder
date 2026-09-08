@echo off
REM Slideshow launcher for Windows. Double-click to start.
REM Plays slideshow-x3.mp4 from this same folder in VLC: fullscreen, looping, no OSD, no audio.
REM Set SLIDESHOW_FILE to play a different file. To stop: press Esc in VLC, then close VLC (Ctrl+Q).
REM Turn off screen sleep in Windows power settings, or run this from a session that holds a
REM powercfg display request; the render and prep wrappers do that for their own runs.
setlocal
if defined SLIDESHOW_FILE (set "FILE=%SLIDESHOW_FILE%") else (set "FILE=%~dp0slideshow-x3.mp4")
if not exist "%FILE%" (
  echo slideshow-x3.mp4 not found next to this script in %~dp0 ^(or SLIDESHOW_FILE does not exist^)
  pause
  exit /b 1
)
set "VLC="
if exist "%ProgramFiles%\VideoLAN\VLC\vlc.exe" set "VLC=%ProgramFiles%\VideoLAN\VLC\vlc.exe"
if not defined VLC if exist "%ProgramFiles(x86)%\VideoLAN\VLC\vlc.exe" set "VLC=%ProgramFiles(x86)%\VideoLAN\VLC\vlc.exe"
if not defined VLC (
  echo VLC is not installed. Install it from https://www.videolan.org/ then run this again.
  pause
  exit /b 1
)
taskkill /IM vlc.exe /F >nul 2>&1
start "" "%VLC%" --fullscreen --repeat --no-osd --no-video-title-show --no-audio "%FILE%"
