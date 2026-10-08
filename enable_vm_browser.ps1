# One-time browser access setup for an installed Ubuntu VirtualBox VM.
# Example: enable_vm_browser.bat -VmName "My Ubuntu VM" -GuestUser myuser
# It gracefully reboots the VM to attach adapter 2, builds the dashboard,
# installs its boot network service, and prints the permanent browser address.
# See OWN_VM_SETUP.md for installation on your own PC. Supply your VM name and
# Ubuntu username; the defaults below refer to the original development host.
param(
    [string]$VmName = 'LinuxVm1',
    [string]$GuestUser = 'rat',
    [string]$GuestProjectPath,
    [string]$Address,
    [string]$PasswordFile,
    [switch]$PrepareTemplate,
    [string]$SnapshotName = 'dsfst-browser-ready'
)
$ErrorActionPreference = 'Stop'
$script:DsfstVBox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
. (Join-Path $PSScriptRoot 'dsfst_network_common.ps1')
function Quote-Guest([string]$Value) { return "'" + $Value.Replace("'", ("'" + [char]34 + "'" + [char]34 + "'")) + "'" }
function Invoke-Guest([string]$Command, [int]$Timeout = 120000) {
    Invoke-DsfstVBox (@('guestcontrol', $VmName, 'run', '--exe=/bin/bash', '--username', $GuestUser, "--passwordfile=$activePasswordFile", '--wait-stdout', '--wait-stderr', "--timeout=$Timeout", '--', '-lc', $Command))
}
function Wait-VMState([string]$State) {
    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-DsfstVMInfo $VmName)['VMState'] -ne $State) {
        if ((Get-Date) -gt $deadline) { throw "Timed out waiting for $VmName to become $State." }
        Start-Sleep -Seconds 2
    }
}
function Wait-Guest {
    $deadline = (Get-Date).AddSeconds(180)
    do {
        $probe = Invoke-DsfstVBox @('guestcontrol', $VmName, 'run', '--exe=/bin/true', '--username', $GuestUser, "--passwordfile=$activePasswordFile", '--wait-stdout', '--wait-stderr', '--timeout=5000', '--') -AllowFailure
        if ($probe.ExitCode -eq 0) { return }
        if ((Get-Date) -gt $deadline) { throw 'Guest Additions did not become ready.' }
        Start-Sleep -Seconds 3
    } while ($true)
}
function Invoke-GuestRoot([string]$Command) {
    $guestDir = '/tmp/dsfst-browser-' + [guid]::NewGuid().ToString('N')
    $quotedDir = Quote-Guest $guestDir
    Invoke-Guest "mkdir -m 700 $quotedDir" | Out-Null
    try {
        Invoke-DsfstVBox @('guestcontrol', $VmName, 'copyto', '--username', $GuestUser, "--passwordfile=$activePasswordFile", $activePasswordFile, "$guestDir/password") | Out-Null
        $pwPath = Quote-Guest "$guestDir/password"
        $rootCommand = Quote-Guest "rm -f $pwPath; $Command"
        Invoke-Guest "sudo -S -p '' /bin/bash -c $rootCommand < $pwPath" | ForEach-Object { $_.Lines | Write-Output }
    } finally {
        Invoke-Guest "rm -rf -- $quotedDir" | Out-Null
    }
}

$temporaryPassword = $null
try {
    if ($PrepareTemplate) {
        $snapshotLines = (Invoke-DsfstVBox @('snapshot', $VmName, 'list', '--machinereadable')).Lines
        if ($snapshotLines | Where-Object { $_ -match '^SnapshotName(?:-\d+)?="?(.+?)"?$' -and $Matches[1] -eq $SnapshotName }) {
            throw "Snapshot $SnapshotName already exists. Supply a new -SnapshotName to prepare an updated version."
        }
    }
    if ($PasswordFile) { $activePasswordFile = (Resolve-Path -LiteralPath $PasswordFile).Path }
    else {
        $secure = Read-Host "Ubuntu password for $GuestUser in $VmName" -AsSecureString
        $credential = New-Object Management.Automation.PSCredential($GuestUser, $secure)
        $temporaryPassword = Join-Path $env:TEMP ('dsfst-browser-' + [guid]::NewGuid().ToString('N') + '.txt')
        [IO.File]::WriteAllText($temporaryPassword, $credential.GetNetworkCredential().Password, (New-Object Text.UTF8Encoding($false)))
        $activePasswordFile = $temporaryPassword
    }
    $adapter = Get-DsfstHostOnlyAdapter -Create
    $ip = Get-DsfstAddress $VmName $Address
    $info = Get-DsfstVMInfo $VmName
    if ($info['VMState'] -eq 'poweroff') { Invoke-DsfstVBox @('startvm', $VmName, '--type=gui') | Out-Null }
    elseif ($info['VMState'] -ne 'running') { throw 'Resume or fully shut down this VM first.' }
    Wait-Guest
    if (-not $GuestProjectPath) {
        $GuestProjectPath = (Invoke-Guest 'systemctl show dsfst.service -p WorkingDirectory --value').Lines |
            Where-Object { $_.StartsWith('/') } | Select-Object -Last 1
    }
    if (-not $GuestProjectPath -or -not $GuestProjectPath.StartsWith('/') -or $GuestProjectPath.Contains("`n") -or $GuestProjectPath.Contains(' ')) { throw 'Supply an absolute -GuestProjectPath without spaces.' }
    $root = Quote-Guest $GuestProjectPath
    # Refuse to restart while an injection is active; preserve the user's test.
    $stateDeadline = (Get-Date).AddSeconds(180)
    do {
        $stateResult = Invoke-DsfstVBox @('guestcontrol', $VmName, 'run', '--exe=/usr/bin/curl', '--username', $GuestUser, "--passwordfile=$activePasswordFile", '--wait-stdout', '--wait-stderr', '--timeout=10000', '--', '-fsS', '--max-time', '5', 'http://127.0.0.1:8009/state') -AllowFailure
        if ($stateResult.ExitCode -eq 0) { break }
        if ((Get-Date) -gt $stateDeadline) { throw 'The app did not become ready. Start dsfst.service before retrying.' }
        Start-Sleep -Seconds 3
    } while ($true)
    $state = ($stateResult.Lines -join "`n") | ConvertFrom-Json
    if ($state.state -notin @('idle','complete') -or $state.active_experiment_id) { throw 'An experiment is active. Finish or stop it before browser setup.' }
    $batchGuard = @'
import json
import urllib.request
import urllib.error
try:
    batches = json.load(urllib.request.urlopen('http://127.0.0.1:8009/experiment-batches?active_only=true&limit=50', timeout=60))
except urllib.error.HTTPError as error:
    if error.code != 404:
        raise
else:
    if any(b['status'] in ('starting', 'running', 'partial_failure', 'stopping') for b in batches):
        raise SystemExit('Finish or stop active multi-VM batches before browser setup.')
'@
    # PowerShell 5 native argument passing can strip quotes inside Python.
    # Send the guard as base64 data, with a runner that contains no nested quotes.
    $guardData = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($batchGuard))
    $guardRunner = 'import base64, sys; exec(base64.b64decode(sys.argv[1]))'
    Invoke-Guest ("python3 -c " + (Quote-Guest $guardRunner) + " " + (Quote-Guest $guardData)) | Out-Null
    Write-Output 'Updating browser access files and building the dashboard...'
    $files = @('RunALL.py', 'install_dsfst.sh', 'start_dsfst.sh', 'stop_dsfst.sh', 'configure_dsfst_network.sh', 'dsfst_probe.py',
        'dsft-frontend/server/index.ts', 'dsft-frontend/server/api-proxy.ts', 'dsft-frontend/client/src/lib/api.ts',
        'vm_registry.py', 'vm_metrics.py', 'multi_vm.py', 'metrics_api.py', 'experiment_orchestrator.py',
        'database/mongo_setup.py', 'setup_dsfst.sh', 'enable_dsfst_autostart.sh',
        'dsft-frontend/client/src/App.tsx', 'dsft-frontend/client/src/components/Sidebar.tsx',
        'dsft-frontend/client/src/pages/VMs.tsx', 'dsft-frontend/client/src/lib/vm-api.ts')
    foreach ($file in $files) {
        Invoke-DsfstVBox @('guestcontrol', $VmName, 'copyto', '--username', $GuestUser, "--passwordfile=$activePasswordFile", (Join-Path $PSScriptRoot $file), "$GuestProjectPath/$file") | Out-Null
    }
    Invoke-Guest "cd $root/dsft-frontend && npm run check && npm run build" 300000 | ForEach-Object { $_.Lines | Write-Output }
    $currentInfo = Get-DsfstVMInfo $VmName
    if ($currentInfo['nic2'] -eq 'hostonly' -and $currentInfo['hostonlyadapter2'] -eq $adapter) {
        Set-DsfstVMProperties $VmName $ip
    } else {
        Write-Output 'Shutting down gracefully to attach the host-only network adapter...'
        Invoke-GuestRoot 'systemctl stop dsfst.service'
        Invoke-DsfstVBox @('controlvm', $VmName, 'acpipowerbutton') | Out-Null
        Wait-VMState 'poweroff'
        Set-DsfstVMNetwork $VmName $adapter $ip
        Invoke-DsfstVBox @('startvm', $VmName, '--type=gui') | Out-Null
        Wait-Guest
    }
    Write-Output 'Installing the guest network service...'
    Invoke-GuestRoot "bash $root/configure_dsfst_network.sh --install && systemctl restart dsfst.service"
    Invoke-DsfstVBox @('setextradata', $VmName, 'dsfst/browser-ready', '1') | Out-Null
    if ($PrepareTemplate) {
        Write-Output "Preparing template snapshot $SnapshotName..."
        Invoke-GuestRoot 'systemctl stop dsfst.service'
        Invoke-DsfstVBox @('controlvm', $VmName, 'acpipowerbutton') | Out-Null
        Wait-VMState 'poweroff'
        Invoke-DsfstVBox @('snapshot', $VmName, 'take', $SnapshotName) | Out-Null
        Invoke-DsfstVBox @('setextradata', $VmName, 'dsfst/browser-snapshot', $SnapshotName) | Out-Null
        Invoke-DsfstVBox @('setextradata', $VmName, 'dsfst/template-ready', '1') | Out-Null
        Invoke-DsfstVBox @('startvm', $VmName, '--type=gui') | Out-Null
        Wait-Guest
    }
    Save-DsfstVMAddresses
    $deadline = (Get-Date).AddSeconds(180)
    do {
        try {
            $state = Invoke-RestMethod -Uri "http://${ip}:3000/api/8009/state" -TimeoutSec 5
            Write-Output "Browser access ready: http://${ip}:3000/#/ (state: $($state.state))"
            break
        } catch {
            if ((Get-Date) -gt $deadline) { throw "Browser access did not start: $($_.Exception.Message)" }
            Start-Sleep -Seconds 3
        }
    } while ($true)
} finally {
    if ($temporaryPassword) { Remove-Item -LiteralPath $temporaryPassword -Force -ErrorAction SilentlyContinue }
}
