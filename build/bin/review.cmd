@echo off
REM bin\review.cmd -- write <project>/build/review.html (the sequence with names) and open it in Chrome.
setlocal
set "ROOT=%~dp0.."
if exist "%ROOT%\..\tools\node\node.exe" set "PATH=%ROOT%\..\tools\node;%PATH%"
node "%ROOT%\lib\review.js" %*
if errorlevel 1 exit /b %ERRORLEVEL%
set "BUILD="
for /f "delims=" %%b in ('node "%ROOT%\lib\common.js" --print build %*') do set "BUILD=%%b"
set "URL=file:///%BUILD:\=/%/review.html"
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if defined CHROME (start "" "%CHROME%" "%URL%") else (start "" chrome "%URL%")
exit /b 0
