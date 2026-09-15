@echo off
REM Slideshow launcher for Windows. Double-click to start.
REM Plays the rendered file from this same folder in VLC: fullscreen, looping, no OSD, sound on (a silent render plays
REM nothing; a render with music plays it, so set the venue's volume first). The concatenated render
REM slideshow-x<N>.mp4 (bin\render --concat; the first in name order) is preferred, then the single loop slideshow.mp4.
REM Set SLIDESHOW_FILE to play a different file. To stop: press Esc in VLC, then close VLC (Ctrl+Q).
REM Turn off screen sleep in Windows power settings, or run this from a session that holds a
REM powercfg display request; the render and prep wrappers do that for their own runs.
setlocal
set "FILE="
if defined SLIDESHOW_FILE if exist "%SLIDESHOW_FILE%" set "FILE=%SLIDESHOW_FILE%"
if not defined FILE for /f "delims=" %%f in ('dir /b /on "%~dp0slideshow-x*.mp4" 2^>nul') do if not defined FILE set "FILE=%~dp0%%f"
if not defined FILE if exist "%~dp0slideshow.mp4" set "FILE=%~dp0slideshow.mp4"
if not defined FILE (
  echo slideshow-x^<N^>.mp4 or slideshow.mp4 not found next to this script in %~dp0 ^(or SLIDESHOW_FILE does not exist^)
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
start "" "%VLC%" --fullscreen --repeat --no-osd --no-video-title-show "%FILE%"
