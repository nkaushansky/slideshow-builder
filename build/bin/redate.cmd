@echo off
REM bin\redate.cmd -- Windows wrapper: move one item (and its Live Photo companion) to a new date.
REM Puts the optional local toolchain (tools\node, tools\ffmpeg under the repo) on PATH and runs lib\redate.js.
REM Point it at a project with --project <folder>, SLIDESHOW_PROJECT, or by running inside the project folder.
setlocal
set "ROOT=%~dp0.."
if exist "%ROOT%\..\tools\node\node.exe" set "PATH=%ROOT%\..\tools\node;%PATH%"
if exist "%ROOT%\..\tools\ffmpeg\ffmpeg.exe" set "PATH=%ROOT%\..\tools\ffmpeg;%PATH%"
node "%ROOT%\lib\redate.js" %*
exit /b %ERRORLEVEL%
