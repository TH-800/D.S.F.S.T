# Live registry and metrics checks. Creates only a temporary VM registration.
param(
    [string]$CoordinatorUrl = 'http://192.168.56.10:3000',
    [string]$RemoteUrl = 'http://192.168.56.11:3000',
    [string]$OutputFile
)
$ErrorActionPreference = 'Stop'
$coordinator = $CoordinatorUrl.TrimEnd('/')
$remote = $RemoteUrl.TrimEnd('/')
foreach ($url in @($coordinator, $remote)) {
    if ($url -notmatch '^http://192\.168\.56\.[1-9][0-9]:3000$') { throw 'Use private VM gateway addresses.' }
}
if ($coordinator -eq $remote) { throw 'Use two different VMs.' }
function Api([string]$Base, [string]$Path, [string]$Method = 'GET', $Body = $null) {
    $arguments = @{ Uri="$Base$Path"; Method=$Method; TimeoutSec=45 }
    if ($null -ne $Body) { $arguments.ContentType='application/json'; $arguments.Body=ConvertTo-Json -InputObject $Body -Depth 12 }
    Invoke-RestMethod @arguments
}
function Expect-Error([int]$Status, [string]$Path, [string]$Method = 'GET', $Body = $null) {
    try { Api $coordinator $Path $Method $Body | Out-Null }
    catch {
        if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq $Status) { return }
        throw
    }
    throw "Expected HTTP $Status for $Path"
}
$created = $false
$registration = $null
try {
    $known = @(Api $coordinator '/api/8009/vms')
    $registration = $known | Where-Object { $_.base_url -eq $remote } | Select-Object -First 1
    if (-not $registration) {
        $registration = Api $coordinator '/api/8009/vms' 'POST' @{name=('Registry live smoke ' + [guid]::NewGuid().ToString('N'));base_url=$remote}
        $created = $true
    }
    $known = @(Api $coordinator '/api/8009/vms')
    if ('local' -notin $known.vm_id -or $registration.vm_id -notin $known.vm_id) { throw 'VM registration was not persisted.' }
    Expect-Error 409 '/api/8009/vms' 'POST' @{name='duplicate';base_url=$remote}
    Expect-Error 409 '/api/8009/vms/local' 'DELETE'
    Expect-Error 422 '/api/8009/vms' 'POST' @{name='invalid';base_url='http://example.org:3000'}
    Expect-Error 404 '/api/8008/vms/missing-vm/metrics/latest'
    Expect-Error 422 '/api/8008/metrics/history?measurement=invalid'
    Expect-Error 422 '/api/8008/metrics/history?minutes=0'
    $before = Api $remote '/api/8008/metrics/latest'
    $scoped = Api $coordinator "/api/8008/vms/$($registration.vm_id)/metrics/latest"
    $after = Api $remote '/api/8008/metrics/latest'
    if ($scoped.vm_id -ne $registration.vm_id -or $scoped.vm_name -ne $registration.name) { throw 'Metrics have the wrong VM identity.' }
    $matching = @($before.cpu, $after.cpu) | Where-Object {
        $_.timestamp -eq $scoped.cpu.timestamp -and $_.cpu_usage_percent -eq $scoped.cpu.cpu_usage_percent
    }
    if (-not $matching) { throw 'Scoped CPU readings do not match the selected remote VM.' }
    $historyResults = @()
    foreach ($measurement in @('cpu','memory','network')) {
        $sample = $scoped.$measurement
        if (-not $sample.timestamp) { throw "Missing $measurement reading." }
        $age = ([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($sample.timestamp)).TotalSeconds
        if ($age -gt 60 -or $age -lt -10) { throw "Stale $measurement reading." }
        $history = Api $coordinator "/api/8008/vms/$($registration.vm_id)/metrics/history?measurement=$measurement&minutes=5"
        if ($history.vm_id -ne $registration.vm_id -or $history.measurement -ne $measurement -or $history.minutes -ne 5) { throw 'History has the wrong VM or query parameters.' }
        if (-not @($history.series.PSObject.Properties | Where-Object { @($_.Value).Count -gt 0 }).Count) { throw "Missing $measurement history." }
        $historyResults += $history
    }
    $local = Api $coordinator '/api/8008/metrics/latest?vm_id=local'
    if ($local.vm_id -ne 'local') { throw 'Local metrics lost their VM identity.' }
    $result = @{ok=$true;checked_at=[DateTimeOffset]::UtcNow.ToString('o');coordinator=$coordinator;remote=$remote;
        registration=$registration;created_temporary_registration=$created;local_metrics=$local;remote_metrics=$scoped;history=$historyResults}
} finally {
    if ($created -and $registration) {
        Api $coordinator "/api/8009/vms/$($registration.vm_id)" 'DELETE' | Out-Null
        $remaining = @(Api $coordinator '/api/8009/vms')
        if ($registration.vm_id -in $remaining.vm_id) { throw 'Temporary registration remained after cleanup.' }
    }
}
$json = $result | ConvertTo-Json -Depth 24
if ($OutputFile) { [IO.File]::WriteAllText($OutputFile, $json, (New-Object Text.UTF8Encoding($false))) }
Write-Output $json
