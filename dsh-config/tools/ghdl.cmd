@echo off
setlocal
set "MODE=auto"
if "%~1"=="-m" goto usemirror
if "%~1"=="--mirror" goto usemirror
goto args
:usemirror
set "MODE=mirror"
shift
:args
if "%~1"=="" goto usage
set "ORIG=%~1"
set "OUT=%~2"
set "M=https://ghproxy.net/"
if "%MODE%"=="mirror" goto mirror
echo [ghdl] trying direct ...
if "%OUT%"=="" (curl.exe -L --fail --retry 1 --connect-timeout 8 --max-time 600 -O -J "%ORIG%") else (curl.exe -L --fail --retry 1 --connect-timeout 8 --max-time 600 -o "%OUT%" "%ORIG%")
if not errorlevel 1 goto ok
echo [ghdl] direct failed, falling back to mirror ...
:mirror
set "U=%ORIG%"
if not "%U%"=="%U:https://codeload.github.com/=%" goto codeload
if not "%U%"=="%U:https://github.com/=%" goto prefix
if not "%U%"=="%U:https://raw.githubusercontent.com/=%" goto prefix
if not "%U%"=="%U:https://objects.githubusercontent.com/=%" goto prefix
if not "%U%"=="%U:https://gist.githubusercontent.com/=%" goto prefix
goto prefix
:codeload
set "U=%U:https://codeload.github.com/=%"
set "Z=%U:/zip/=/archive/%"
if not "%Z%"=="%U%" goto codezip
set "T=%U:/tar.gz/=/archive/%"
if not "%T%"=="%U%" goto codetar
set "U=%M%https://codeload.github.com/%U%"
goto do
:codezip
set "U=%M%https://github.com/%Z%.zip"
goto do
:codetar
set "U=%M%https://github.com/%T%.tar.gz"
goto do
:prefix
set "U=%M%%U%"
:do
echo [ghdl] %U%
if "%OUT%"=="" (curl.exe -L --fail --retry 3 --connect-timeout 25 --max-time 900 -O -J "%U%") else (curl.exe -L --fail --retry 3 --connect-timeout 25 --max-time 900 -o "%OUT%" "%U%")
exit /b %errorlevel%
:ok
echo [ghdl] done (direct)
exit /b 0
:usage
echo Usage: ghdl [-m] ^<github-url^> [output-file]
echo   ghdl https://github.com/user/repo/releases/download/v1/app.zip
echo   ghdl -m https://codeload.github.com/user/repo/zip/refs/heads/main out.zip
echo Tries direct first; -m or a failed direct attempt uses the ghproxy.net mirror.
exit /b 2
