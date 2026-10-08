@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ghclone.ps1" %*
exit /b %errorlevel%
