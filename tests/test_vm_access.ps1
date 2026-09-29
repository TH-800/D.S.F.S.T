$ErrorActionPreference = 'Stop'
$folder = Join-Path ([IO.Path]::GetTempPath()) ('dsfst-vm-access-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $folder | Out-Null
$fake = Join-Path $folder 'VBoxManage.ps1'
$password = Join-Path $folder 'password.txt'
$json = Join-Path $folder 'request.json'
$log = Join-Path $folder 'calls.txt'
$env:DSFST_FAKE_LOG = $log
try {
    @'
Add-Content -LiteralPath $env:DSFST_FAKE_LOG -Value ($args -join '|')
if ($args[0] -eq 'showvminfo') { 'VMState="running"'; exit 0 }
if ($args[0] -eq 'guestcontrol' -and $args[2] -eq 'run') {
    if ($args -contains 'systemctl show dsfst.service -p WorkingDirectory --value') {
        '/home/rat/project'
    } else {
        '{"ok":true,"status":200,"data":{"state":"idle"}}'
    }
    exit 0
}
if ($args[0] -eq 'guestcontrol' -and $args[2] -in @('copyto', 'rm')) { exit 0 }
exit 1
'@ | Set-Content -LiteralPath $fake -Encoding UTF8
    'dummy' | Set-Content -LiteralPath $password -NoNewline -Encoding Ascii
    '{"hello":"world"}' | Set-Content -LiteralPath $json -Encoding Ascii
    $launcher = Join-Path (Split-Path $PSScriptRoot -Parent) 'dsfst_vm_access.ps1'
    $output = & $launcher -Action api -VmName FakeVm -GuestUser rat -PasswordFile $password `
        -VBoxManagePath $fake -Method POST -Port 8009 -ApiPath /experiments -JsonFile $json
    if ($LASTEXITCODE -ne 0) { throw "Launcher exited with $LASTEXITCODE" }
    $reply = ($output -join "`n") | ConvertFrom-Json
    if (-not $reply.ok -or $reply.status -ne 200) { throw 'Unexpected guest API reply.' }
    $calls = Get-Content -LiteralPath $log
    if (-not ($calls | Where-Object { $_ -match 'copyto.*dsfst_probe.py' })) { throw 'Probe was not copied.' }
    if (-not ($calls | Where-Object { $_ -match 'copyto.*request.json.*dsfst-api-' })) { throw 'JSON body was not copied.' }
    if (-not ($calls | Where-Object { $_ -match 'run.*dsfst_probe.py\|api\|POST\|8009\|/experiments\|--json-file' })) {
        throw 'POST request did not reach the guest probe.'
    }
    if (-not ($calls | Where-Object { $_ -match '\|rm\|.*dsfst-api-' })) { throw 'Guest JSON file was not removed.' }
    'Windows VM access wrapper smoke OK'
} finally {
    Remove-Item Env:DSFST_FAKE_LOG -ErrorAction SilentlyContinue
    foreach ($file in @($fake, $password, $json, $log)) {
        if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file -Force }
    }
    if (Test-Path -LiteralPath $folder) { Remove-Item -LiteralPath $folder }
}
