# Clone a prepared Ubuntu VirtualBox VM on this Windows computer.
# On a new computer, install VirtualBox, copy the full D.S.F.S.T project into
# your Ubuntu VM, then run these commands inside the VM as its normal user:
#   bash install_dsfst.sh
#   bash enable_dsfst_autostart.sh
# Test with: sudo systemctl start dsfst.service
# Shut down the VM. In Windows Command Prompt, mark it and take a snapshot:
#   "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" setextradata "My Ubuntu VM" dsfst/template-ready 1
#   "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" snapshot "My Ubuntu VM" take dsfst-ready
# Then run: create_dsfst_vms.bat 2 -TemplateVm "My Ubuntu VM"
# The Ubuntu password is needed for one-time setup, not for cloning or boot.
# See VM_FACTORY_README.txt for prerequisites and further details.
param(
    [Parameter(Position = 0)]
    [ValidateRange(1, 16)]
    [int]$Count,
    [switch]$NoStart,
    [switch]$DryRun,
    [ValidateNotNullOrEmpty()]
    [string]$TemplateVm = 'LinuxVm1',
    [ValidateNotNullOrEmpty()]
    [string]$SnapshotName = 'dsfst-ready'
)

$ErrorActionPreference = 'Stop'
if ($Count -lt 1) { throw 'Supply the number of VMs: create_dsfst_vms.bat 2' }

$vbox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
if (-not (Test-Path -LiteralPath $vbox)) { throw 'Oracle VirtualBox is not installed.' }
$template = $TemplateVm
$snapshot = $SnapshotName
$memoryMB = 4096
$hostReserveMB = 4096

function Invoke-VBox([string[]]$vboxArgs) {
    # VirtualBox writes successful progress to stderr. PowerShell 5 treats
    # that as an error when ErrorActionPreference is Stop.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $result = & $vbox @vboxArgs 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    $lines = @($result | ForEach-Object { $_.ToString() })
    if ($exitCode -ne 0) { throw "VBoxManage $($vboxArgs -join ' ') failed: $($lines -join ' ')" }
    return $lines
}

function Get-VMInfo([string]$name) {
    $info = @{}
    foreach ($line in (Invoke-VBox @('showvminfo', $name, '--machinereadable'))) {
        if ($line -match '^([^=]+)=(.*)$') {
            $info[$Matches[1].Trim('"')] = $Matches[2].Trim('"').Replace('\\', '\')
        }
    }
    return $info
}

function Get-Extra([string]$name, [string]$key) {
    $value = Invoke-VBox @('getextradata', $name, $key)
    if ($value -match '^Value: (.*)$') { return $Matches[1] }
    return $null
}

$templateInfo = Get-VMInfo $template
if ((Get-Extra $template 'dsfst/template-ready') -ne '1') {
    throw "Template $template is not prepared. Run enable_dsfst_autostart.sh in it, mark it ready, then create the $snapshot snapshot. See VM_FACTORY_README.txt."
}
$snapshotLines = Invoke-VBox @('snapshot', $template, 'list', '--machinereadable')
if (-not ($snapshotLines | Where-Object { $_ -match '^SnapshotName(?:-\d+)?="?(.+?)"?$' -and $Matches[1] -eq $snapshot })) {
    throw "Snapshot $snapshot is missing from $template."
}

$allVMs = @{}
foreach ($line in (Invoke-VBox @('list', 'vms'))) {
    if ($line -match '^"(.+)" \{[0-9a-fA-F-]+\}$') { $allVMs[$Matches[1]] = $true }
}
$runningVMs = @{}
$allocatedMB = 0
foreach ($line in (Invoke-VBox @('list', 'runningvms'))) {
    if ($line -match '^"(.+)" \{[0-9a-fA-F-]+\}$') {
        $name = $Matches[1]
        $runningVMs[$name] = $true
        $allocatedMB += [int](Get-VMInfo $name)['memory']
    }
}

$names = @(1..$Count | ForEach-Object { 'DSFST-User-{0:D3}' -f $_ })
$newCount = 0
$startCount = 0
foreach ($name in $names) {
    if ($allVMs.ContainsKey($name)) {
        if ((Get-Extra $name 'dsfst/managed') -ne '1') {
            throw "VM $name already exists and was not created by this script."
        }
    } else {
        $newCount++
    }
    if (-not $NoStart -and -not $runningVMs.ContainsKey($name)) { $startCount++ }
}

if (-not $NoStart) {
    $hostMB = [math]::Floor((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1MB)
    if ($allocatedMB + $startCount * $memoryMB + $hostReserveMB -gt $hostMB) {
        throw "Not enough host RAM for $startCount more VMs. Running VMs use $allocatedMB MB; each clone uses $memoryMB MB; $hostReserveMB MB is reserved for Windows."
    }
}
if ($newCount -gt 0) {
    $templateDir = Split-Path -Path $templateInfo['CfgFile'] -Parent
    $disks = @(Get-ChildItem -LiteralPath $templateDir -Filter '*.vdi' -File -Recurse)
    if ($disks.Count -eq 0) { throw "Cannot find template disks in $templateDir" }
    $cloneBytes = ($disks | Measure-Object -Property Length -Sum).Sum
    $drive = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($templateDir))
    if ($drive.AvailableFreeSpace -lt ($cloneBytes * $newCount + 8GB)) {
        throw "Not enough free disk space for $newCount full clones and an 8 GB reserve."
    }
}

foreach ($name in $names) {
    if (-not $allVMs.ContainsKey($name)) {
        Write-Host "Creating $name from $template snapshot $snapshot..."
        if (-not $DryRun) {
            Invoke-VBox @('clonevm', $template, "--snapshot=$snapshot", "--name=$name", '--mode=machine', '--register') | Out-Host
            Invoke-VBox @('modifyvm', $name, "--memory=$memoryMB", '--cpus=1', '--nic1=nat') | Out-Host
            Invoke-VBox @('setextradata', $name, 'dsfst/managed', '1') | Out-Host
        }
    } else {
        Write-Host "$name already exists."
    }
    if (-not $NoStart -and -not $runningVMs.ContainsKey($name)) {
        Write-Host "Starting $name..."
        if (-not $DryRun) {
            $state = (Get-VMInfo $name)['VMState']
            if ($state -eq 'saved') { Invoke-VBox @('discardstate', $name) | Out-Host }
            Invoke-VBox @('startvm', $name, '--type=gui') | Out-Host
        }
    }
}
if ($DryRun) { Write-Host 'Dry run complete; no VM was changed.' }
