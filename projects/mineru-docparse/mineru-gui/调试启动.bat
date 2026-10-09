@echo off
rem ============================================================
rem  MinerU batch converter - DEBUG launch (keeps console, shows errors)
rem  Runs with the venv's python.exe so that tracebacks are visible.
rem ============================================================
setlocal
cd /d "%~dp0"
if not defined MINERU_ROOT set "MINERU_ROOT=%MINERU_ROOT%"
set "PY=%MINERU_ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0run.py"
echo.
echo ---- exited with code %ERRORLEVEL% ----
pause
endlocal
