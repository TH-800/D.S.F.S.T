@echo off
setlocal
if "%~1"=="" (
  echo Usage: create_dsfst_vms.bat COUNT [-NoStart] [-DryRun] [-TemplateVm "VM name"] [-SnapshotName "snapshot name"]
  exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_dsfst_vms.ps1" %*
exit /b %ERRORLEVEL%
