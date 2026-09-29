@echo off
setlocal
if "%~1"=="" (
  echo Usage: dsfst_vm_access.bat -Action status^|db^|mongo^|influx^|redis^|api [-VmName VM] [options]
  echo See VM_ACCESS_README.md for examples.
  exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0dsfst_vm_access.ps1" %*
exit /b %ERRORLEVEL%
