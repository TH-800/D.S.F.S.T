param(
    [ValidateSet('status', 'db', 'mongo', 'influx', 'redis', 'api')]
    [Parameter(Mandatory = $true)]
    [string]$Action,
    [string]$VmName = 'LinuxVm1',
    [string]$GuestUser = 'rat',
    [string]$GuestProjectPath,
    [string]$PasswordFile,
    [string]$VBoxManagePath,
    [ValidateSet('GET', 'POST')]
    [string]$Method = 'GET',
    [ValidateRange(8000, 8010)]
    [int]$Port = 8009,
    [string]$ApiPath = '/state',
    [string]$Collection = 'experiments',
    [ValidateRange(1, 50)]
    [int]$Limit = 10,
    [ValidateRange(1, 1440)]
    [int]$Minutes = 15,
    [string]$JsonFile
)

$ErrorActionPreference = 'Stop'
$vbox = if ($VBoxManagePath) { $VBoxManagePath } else { Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe' }
if (-not (Test-Path -LiteralPath $vbox)) { throw "VBoxManage was not found at $vbox." }
$localProbe = Join-Path $PSScriptRoot 'dsfst_probe.py'
if (-not (Test-Path -LiteralPath $localProbe)) { throw "Missing $localProbe" }
if ($Action -ne 'api' -and $JsonFile) { throw '-JsonFile is only valid with -Action api.' }
if ($Action -eq 'api' -and $Method -eq 'GET' -and $JsonFile) { throw 'GET cannot have a JSON request body.' }
if ($Action -eq 'db' -and $Limit -gt 20) { throw 'The db summary accepts -Limit 1 through 20.' }

function Invoke-VBox([string[]]$vboxArgs, [switch]$AllowFailure) {
    # VBoxManage sometimes writes successful progress to stderr.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $raw = & $vbox @vboxArgs 2>&1
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    $lines = @($raw | ForEach-Object { $_.ToString() })
    if ($code -ne 0 -and -not $AllowFailure) {
        throw "VBoxManage failed (exit $code): $($lines -join ' ')"
    }
    return [pscustomobject]@{ ExitCode = $code; Lines = $lines }
}

$vmInfo = Invoke-VBox @('showvminfo', $VmName, '--machinereadable')
if (-not ($vmInfo.Lines | Where-Object { $_ -eq 'VMState="running"' })) {
    throw "VM $VmName is not running. Start it in VirtualBox first."
}

$temporaryPasswordFile = $null
$guestJsonFile = $null
$resultCode = 1
try {
    if ($PasswordFile) {
        $activePasswordFile = (Resolve-Path -LiteralPath $PasswordFile).Path
    } else {
        $secure = Read-Host "Ubuntu password for $GuestUser in $VmName" -AsSecureString
        $credential = New-Object System.Management.Automation.PSCredential($GuestUser, $secure)
        $temporaryPasswordFile = Join-Path ([IO.Path]::GetTempPath()) ("dsfst-guest-" + [guid]::NewGuid().ToString('N') + '.txt')
        [IO.File]::WriteAllText($temporaryPasswordFile, $credential.GetNetworkCredential().Password,
            (New-Object System.Text.UTF8Encoding($false)))
        $activePasswordFile = $temporaryPasswordFile
    }

    $login = @('--username', $GuestUser, "--passwordfile=$activePasswordFile")
    if (-not $GuestProjectPath) {
        $findPath = Invoke-VBox (@('guestcontrol', $VmName, 'run', '--exe', '/bin/bash') +
            $login + @('--wait-stdout', '--wait-stderr', '--timeout=30000', '--',
                       '-lc', 'systemctl show dsfst.service -p WorkingDirectory --value'))
        $GuestProjectPath = ($findPath.Lines | Where-Object { $_.StartsWith('/') } | Select-Object -Last 1)
        if (-not $GuestProjectPath) {
            throw 'Cannot find the D.S.F.S.T service directory. Supply -GuestProjectPath.'
        }
    }
    $GuestProjectPath = $GuestProjectPath.TrimEnd('/')
    if (-not $GuestProjectPath.StartsWith('/')) { throw '-GuestProjectPath must be an absolute Ubuntu path.' }

    # Keep the guest-side probe in sync with this Windows launcher.
    Invoke-VBox (@('guestcontrol', $VmName, 'copyto') + $login +
        @($localProbe, "$GuestProjectPath/dsfst_probe.py")) | Out-Null

    $probeArgs = @(switch ($Action) {
        'status' { @('status') }
        'db' { @('db', '--limit', [string]$Limit, '--minutes', [string]$Minutes) }
        'mongo' { @('mongo', $Collection, '--limit', [string]$Limit) }
        'influx' { @('influx', '--limit', [string]$Limit, '--minutes', [string]$Minutes) }
        'redis' { @('redis', '--limit', [string]$Limit) }
        'api' { @('api', $Method, [string]$Port, $ApiPath) }
    })
    if ($JsonFile) {
        $sourceJson = (Resolve-Path -LiteralPath $JsonFile).Path
        $guestJsonFile = '/tmp/dsfst-api-' + [guid]::NewGuid().ToString('N') + '.json'
        Invoke-VBox (@('guestcontrol', $VmName, 'copyto') + $login + @($sourceJson, $guestJsonFile)) | Out-Null
        $probeArgs += @('--json-file', $guestJsonFile)
    }

    $python = "$GuestProjectPath/.venv/bin/python"
    $response = Invoke-VBox (@('guestcontrol', $VmName, 'run', '--exe', $python) +
        $login + @('--cwd', $GuestProjectPath, '--wait-stdout', '--wait-stderr',
                   '--timeout=120000', '--', 'dsfst_probe.py') + $probeArgs) -AllowFailure
    $response.Lines | ForEach-Object { Write-Output $_ }
    # VirtualBox maps a nonzero guest exit to its own code (often 33).
    $resultCode = if ($response.ExitCode -eq 0) { 0 } else { 1 }
} finally {
    if ($guestJsonFile -and $activePasswordFile) {
        Invoke-VBox (@('guestcontrol', $VmName, 'rm') + $login + @($guestJsonFile)) -AllowFailure | Out-Null
    }
    if ($temporaryPasswordFile -and (Test-Path -LiteralPath $temporaryPasswordFile)) {
        Remove-Item -LiteralPath $temporaryPasswordFile -Force
    }
}
exit $resultCode
