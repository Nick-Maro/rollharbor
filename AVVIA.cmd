@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0AVVIA.ps1" %*
exit /b %errorlevel%
