@echo off
REM bin\render.cmd -- Windows wrapper: deterministic mp4 through headless Chromium; needs ffmpeg and Playwright.
REM Puts the optional local toolchain (tools\node, tools\ffmpeg under the repo) on PATH and runs lib\render.js.
REM Point it at a project with --project <folder>, SLIDESHOW_PROJECT, or by running inside the project folder.
setlocal
set "ROOT=%~dp0.."
if exist "%ROOT%\..\tools\node\node.exe" set "PATH=%ROOT%\..\tools\node;%PATH%"
if exist "%ROOT%\..\tools\ffmpeg\ffmpeg.exe" set "PATH=%ROOT%\..\tools\ffmpeg;%PATH%"
set "NODE_PATH=%ROOT%\node_modules"
REM keepawake.ps1 holds the machine awake (like caffeinate on macOS) for as long as node runs
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0keepawake.ps1" -Display -- node "%ROOT%\lib\render.js" %*
exit /b %ERRORLEVEL%
