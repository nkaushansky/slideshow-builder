@echo off
REM bin\live.cmd -- open the live player in Google Chrome on Windows.
REM usage: bin\live [speed] [--labels] [--review] [--t 3m10s] [--project <folder>]
REM   --review : click tiles to flag them; the panel on the right lists flags (Copy list / Download flags.txt)
REM   --labels : filename and date on every tile, row/chapter/time per row
REM   --t 3m10s: start at that point in the loop
REM Keys in the player: F fullscreen, space pause, [ and ] speed -/+ 10 px/s.
setlocal
set "ROOT=%~dp0.."
if exist "%ROOT%\..\tools\node\node.exe" set "PATH=%ROOT%\..\tools\node;%PATH%"
set "SPEED="
set "LABELS="
set "START="
set "REVIEW="
:parse
if "%~1"=="" goto parsed
if "%~1"=="--labels" (set "LABELS=1") else if "%~1"=="--review" (set "REVIEW=1") else if "%~1"=="--t" (set "START=%~2" & shift) else if "%~1"=="--project" (set "SLIDESHOW_PROJECT=%~2" & shift) else set "SPEED=%~1"
shift
goto parse
:parsed
set "BUILD="
for /f "delims=" %%b in ('node "%ROOT%\lib\common.js" --print build') do set "BUILD=%%b"
if not defined BUILD (
  echo could not resolve the project folder; pass --project ^<folder^> or set SLIDESHOW_PROJECT
  exit /b 1
)
REM review mode uses its own file so nothing depends on the ?review=1 query surviving the launch
if defined REVIEW (set "PAGE=%BUILD%\player-review.html") else set "PAGE=%BUILD%\player.html"
if not exist "%PAGE%" (
  echo %PAGE% missing; run bin\build first
  exit /b 1
)
set "Q="
if defined SPEED set "Q=%Q%&speed=%SPEED%"
if defined LABELS set "Q=%Q%&labels=1"
if defined START set "Q=%Q%&t=%START%"
set "URL=file:///%PAGE:\=/%"
if defined Q set "URL=%URL%?%Q:~1%"
echo opening %URL%
if defined REVIEW echo review mode: click a tile to flag it, shift-click to add a note, then use "Download flags.txt" (lands in your Downloads folder).
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if defined CHROME (start "" "%CHROME%" "%URL%") else (start "" chrome "%URL%")
exit /b 0
