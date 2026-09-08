@echo off
REM bin\simsched.cmd -- Windows wrapper: scheduler statistics over whole loops, no drawing.
REM Puts the optional local toolchain (tools\node, tools\ffmpeg under the repo) on PATH and runs lib\simsched.js.
REM Point it at a project with --project <folder>, SLIDESHOW_PROJECT, or by running inside the project folder.
setlocal
set "ROOT=%~dp0.."
if exist "%ROOT%\..\tools\node\node.exe" set "PATH=%ROOT%\..\tools\node;%PATH%"
if exist "%ROOT%\..\tools\ffmpeg\ffmpeg.exe" set "PATH=%ROOT%\..\tools\ffmpeg;%PATH%"
set "NODE_PATH=%ROOT%\node_modules"
node "%ROOT%\lib\simsched.js" %*
exit /b %ERRORLEVEL%
