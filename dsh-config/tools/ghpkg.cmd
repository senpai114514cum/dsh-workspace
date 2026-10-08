@echo off
setlocal
if "%~1"=="" goto usage
set "SPEC=%~1"
set "REF=%~2"
if "%REF%"=="" set "REF=main"
set "OUT=%~3"
if "%OUT%"=="" set "OUT=%CD%\vendor"
if not exist "%OUT%" mkdir "%OUT%"
for %%R in ("%SPEC%") do set "NAME=%%~nxR"
set "FILE=%OUT%\%NAME%-%REF%.tar.gz"
echo [ghpkg] %SPEC% @ %REF%
echo [ghpkg] trying tag ...
call "%~dp0ghdl.cmd" "https://github.com/%SPEC%/archive/refs/tags/%REF%.tar.gz" "%FILE%"
if not errorlevel 1 goto done
echo [ghpkg] tag not found, trying branch ...
call "%~dp0ghdl.cmd" "https://github.com/%SPEC%/archive/refs/heads/%REF%.tar.gz" "%FILE%"
if errorlevel 1 goto failed
:done
echo.
echo [ghpkg] saved: %FILE%
echo [ghpkg] install with:
echo     npm i "%FILE%"
echo [ghpkg] or in package.json:
echo     "dep": "file:%FILE%"
exit /b 0
:failed
echo [ghpkg] failed: %SPEC% @ %REF% (neither tag nor branch)
exit /b 1
:usage
echo Usage: ghpkg ^<owner/repo^> [tag-or-branch] [output-dir]
echo   ghpkg MeteorNOX/DeepSeek-Balance-Whale-Widget v0.3.18
echo   ghpkg someuser/somerepo main D:\proj\vendor
exit /b 2
