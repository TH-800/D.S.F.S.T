@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0enable_vm_browser.ps1" %*
exit /b %errorlevel%
