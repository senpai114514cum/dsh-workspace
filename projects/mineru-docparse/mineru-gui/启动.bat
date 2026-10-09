@echo off
rem ============================================================
rem  MinerU batch converter - normal launch (no console window)
rem
rem  Uses the BASE python's pythonw.exe on purpose: the venv's
rem  pythonw.exe is a uv trampoline that spawns the console-subsystem
rem  python.exe, which pops up a black window. run.py adds the venv's
rem  site-packages itself.
rem  (Assumes the base python path contains no spaces, which holds here.)
rem ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not defined MINERU_ROOT set "MINERU_ROOT=%MINERU_ROOT%"
set "VENV=%MINERU_ROOT%\.venv"
set "PY="

if exist "%VENV%\pyvenv.cfg" (
  for /f "usebackq tokens=2 delims==" %%a in ("%VENV%\pyvenv.cfg") do (
    if not defined HOMEDIR (
      echo %%a | findstr /i /c:"python" >nul && set "HOMEDIR=%%a"
    )
  )
)
if defined HOMEDIR set "PY=%HOMEDIR: =%\pythonw.exe"
if defined PY if not exist "%PY%" set "PY="

if not defined PY set "PY=%VENV%\Scripts\pythonw.exe"
if not exist "%PY%" set "PY=pythonw"

start "" "%PY%" "%~dp0run.py"
endlocal
