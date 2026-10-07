$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

& "$ScriptDir\stop_dsfst.ps1"

Start-Sleep -Seconds 5

& "$ScriptDir\start_dsfst.ps1"