@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ARRESTA.ps1" %*
exit /b %errorlevel%
