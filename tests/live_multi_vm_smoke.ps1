# Live Windows-to-Ubuntu multi-VM test. Creates short 10% CPU experiments.
# Both VM apps must already be running and idle. Existing registrations are kept.
param(
    [string]$CoordinatorUrl = 'http://192.168.56.10:3000',
    [string]$RemoteUrl = 'http://192.168.56.11:3000',
    [string]$OutputFile
)
$ErrorActionPreference = 'Stop'
$coordinator = $CoordinatorUrl.TrimEnd('/')
$remote = $RemoteUrl.TrimEnd('/')
foreach ($url in @($coordinator, $remote)) {
    if ($url -notmatch '^http://192\.168\.56\.[1-9][0-9]:3000$') {
        throw 'Use the host-only VM URLs printed by browser setup.'
    }
}
if ($coordinator -eq $remote) { throw 'Use two different VMs.' }
function Api([string]$Base, [string]$Path, [string]$Method = 'GET', $Body = $null) {
    $arguments = @{ Uri="$Base$Path"; Method=$Method; TimeoutSec=90 }
    if ($null -ne $Body) {
        $arguments.ContentType = 'application/json'
        $arguments.Body = ConvertTo-Json -InputObject $Body -Depth 12
    }
    Invoke-RestMethod @arguments
}
function Assert-Idle([string]$Base) {
    $state = Api $Base '/api/8009/state'
    if ($state.state -notin @('idle','complete') -or $state.active_experiment_id) {
        throw "An experiment is active or its state is unknown on $Base."
    }
}
function Assert-Http409([string]$Path) {
    try {
        Invoke-WebRequest -Uri "$coordinator$Path" -Method Delete -UseBasicParsing -TimeoutSec 15 | Out-Null
    } catch {
        if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 409) { return }
        throw
    }
    throw "Expected HTTP 409 for $Path"
}
function Assert-Running($Batch) {
    if ($Batch.status -ne 'running' -or $Batch.members.Count -ne 2) {
        throw 'Both VM children did not confirm startup.'
    }
    if (@($Batch.members.experiment_id | Select-Object -Unique).Count -ne 2) {
        throw 'Child experiment IDs are missing or duplicated.'
    }
    foreach ($member in $Batch.members) {
        $node = if ($member.vm.is_local) { $coordinator } else { $member.vm.base_url }
        $state = Api $node '/api/8009/state'
        if ($state.state -ne 'running' -or $state.active_experiment_id -ne $member.experiment_id) {
            throw "Wrong active child on $($member.vm_name)."
        }
    }
}
function Assert-Finished($Batch) {
    foreach ($member in $Batch.members) {
        $node = if ($member.vm.is_local) { $coordinator } else { $member.vm.base_url }
        Assert-Idle $node
        $record = Api $node "/api/8008/experiments/$($member.experiment_id)"
        if ($record.status -ne 'completed') { throw 'Child completion was not stored.' }
    }
}
$prefix = 'Multi-VM live smoke ' + [guid]::NewGuid().ToString('N')
$created = $false
$registration = $null
$cleanupErrors = New-Object 'System.Collections.Generic.List[string]'
$result = $null
try {
    Assert-Idle $coordinator
    Assert-Idle $remote
    $known = @(Api $coordinator '/api/8009/vms')
    $registration = $known | Where-Object { $_.base_url -eq $remote } | Select-Object -First 1
    if (-not $registration) {
        $registration = Api $coordinator '/api/8009/vms' 'POST' @{ name=$prefix; base_url=$remote }
        $created = $true
    }
    $known = @(Api $coordinator '/api/8009/vms')
    if ('local' -notin $known.vm_id -or $registration.vm_id -notin $known.vm_id) {
        throw 'Registered VM did not appear in the known-VM list.'
    }
    $readings = @()
    foreach ($vmId in @('local', $registration.vm_id)) {
        $latest = Api $coordinator "/api/8008/vms/$vmId/metrics/latest"
        if ($latest.vm_id -ne $vmId) { throw 'Metrics were assigned to the wrong VM.' }
        foreach ($measurement in @('cpu','memory','network')) {
            if (-not $latest.$measurement.timestamp) { throw "Missing $measurement reading." }
            $age = ([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($latest.$measurement.timestamp)).TotalSeconds
            if ($age -gt 60 -or $age -lt -10) { throw "Invalid/stale $measurement timestamp on $vmId." }
            $history = Api $coordinator "/api/8008/vms/$vmId/metrics/history?measurement=$measurement&minutes=5"
            if ($history.vm_id -ne $vmId -or $history.measurement -ne $measurement) {
                throw 'Historical metrics were assigned to the wrong VM or measurement.'
            }
            if (-not @($history.series.PSObject.Properties | Where-Object { @($_.Value).Count -gt 0 }).Count) {
                throw "Missing stored $measurement history on $vmId."
            }
        }
        $readings += $latest
    }
    $natural = Api $coordinator '/api/8009/experiments/launch' 'POST' @{
        name="$prefix natural"; failure_type='cpu'; vm_ids=@('local',$registration.vm_id)
        parameters=@{cpu_percent=10;duration_seconds=15}
    }
    Assert-Running $natural
    Assert-Http409 "/api/8009/vms/$($registration.vm_id)"
    $deadline = (Get-Date).AddSeconds(100)
    do {
        Start-Sleep -Seconds 3
        $natural = Api $coordinator "/api/8009/experiment-batches/$($natural.batch_id)"
        if ($natural.status -eq 'completed') { break }
        if ($natural.status -ne 'running' -or (Get-Date) -gt $deadline) {
            throw "Natural completion failed: $($natural.status)."
        }
    } while ($true)
    Assert-Finished $natural
    $reports = @()
    foreach ($member in $natural.members) {
        $node = if ($member.vm.is_local) { $coordinator } else { $member.vm.base_url }
        $report = Api $node "/api/8008/experiments/$($member.experiment_id)/report"
        $series = Api $node "/api/8008/experiments/$($member.experiment_id)/metrics"
        if (-not $series.labels -or -not $series.datasets) { throw 'Missing child time-series metrics.' }
        $reports += @{vm_id=$member.vm_id;report=$report}
    }
    $manual = Api $coordinator '/api/8009/experiments/launch' 'POST' @{
        name="$prefix manual stop"; failure_type='cpu'; vm_ids=@('local',$registration.vm_id)
        parameters=@{cpu_percent=10;duration_seconds=60}
    }
    Assert-Running $manual
    $manual = Api $coordinator "/api/8009/experiment-batches/$($manual.batch_id)/stop" 'POST' @{}
    if ($manual.status -ne 'stopped') { throw "Batch did not reset: $($manual.status)." }
    Assert-Finished $manual
    $result = @{
        ok=$true;checked_at=[DateTimeOffset]::UtcNow.ToString('o')
        coordinator_url=$coordinator;remote_url=$remote;metrics=$readings
        natural_batch=$natural;stopped_batch=$manual;reports=$reports
        temporary_registration=$created
    }
} finally {
    # Find only this test's batches, including a launch whose HTTP reply was lost.
    try {
        $batches = @(Api $coordinator '/api/8009/experiment-batches?active_only=true&limit=50')
        foreach ($batch in $batches | Where-Object { $_.name -like "$prefix*" }) {
            $stopped = Api $coordinator "/api/8009/experiment-batches/$($batch.batch_id)/stop" 'POST' @{}
            if ($stopped.status -notin @('stopped','completed','failed')) {
                $cleanupErrors.Add("Unconfirmed cleanup of $($batch.batch_id).")
            }
        }
    } catch { $cleanupErrors.Add($_.Exception.Message) }
    if ($created -and $registration) {
        try {
            Api $coordinator "/api/8009/vms/$($registration.vm_id)" 'DELETE' | Out-Null
            $remaining = @(Api $coordinator '/api/8009/vms')
            if ($registration.vm_id -in $remaining.vm_id) { throw 'Temporary registration remained.' }
        } catch { $cleanupErrors.Add($_.Exception.Message) }
    }
    foreach ($problem in $cleanupErrors) { Write-Warning $problem }
}
if ($cleanupErrors.Count) { throw 'Live test cleanup is incomplete; inspect the warnings and batch states.' }
$json = $result | ConvertTo-Json -Depth 24
if ($OutputFile) { [IO.File]::WriteAllText($OutputFile,$json,(New-Object Text.UTF8Encoding($false))) }
Write-Output $json
