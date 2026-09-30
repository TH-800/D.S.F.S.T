# Run from Windows against a prepared VM. -RunExperiment adds a 15-second,
# 10% CPU experiment, checks natural completion, and reads its stored report.
param(
    [string]$BaseUrl = 'http://192.168.56.10:3000',
    [switch]$RunExperiment,
    [string]$OutputFile
)
$ErrorActionPreference = 'Stop'
$base = $BaseUrl.TrimEnd('/')
if ($base -notmatch '^http://192\.168\.56\.[1-9][0-9]:3000$') { throw 'Use the host-only VM URL printed by browser setup.' }
function Read-Api([string]$Path) { Invoke-RestMethod -Uri "$base$Path" -TimeoutSec 25 }
function Post-Api([string]$Path, $Body) { Invoke-RestMethod -Uri "$base$Path" -Method Post -ContentType 'application/json' -Body (ConvertTo-Json -InputObject $Body -Depth 8) -TimeoutSec 30 }
function Expect-HttpError([int]$Status, [string]$Path, [string]$Method, $Headers, [string]$Body) {
    try {
        $arguments = @{ Uri="$base$Path"; Method=$Method; UseBasicParsing=$true; TimeoutSec=10 }
        if ($Headers) { $arguments.Headers=$Headers }
        if ($Body) { $arguments.Body=$Body; $arguments.ContentType='application/json' }
        Invoke-WebRequest @arguments | Out-Null
    } catch {
        if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq $Status) { return }
        throw
    }
    throw "Expected HTTP $Status for $Path"
}
$dashboard = Invoke-WebRequest -Uri "$base/" -UseBasicParsing -TimeoutSec 10
if ($dashboard.StatusCode -ne 200 -or $dashboard.Content -notmatch '<div id="root">') { throw 'Dashboard HTML is missing.' }
$directory = Read-Api '/api'
if ($directory.services.Count -ne 11) { throw 'API directory is incomplete.' }
$state = Read-Api '/api/8009/state'
$cpu = Read-Api '/api/8002/cpu'
$memory = Read-Api '/api/8003/memory'
$network = Read-Api '/api/8001/network'
$openapi = Read-Api '/api/8009/openapi.json'
if ($openapi.servers[0].url -ne '/api/8009') { throw 'OpenAPI points outside this VM gateway.' }
$docs = Invoke-WebRequest -Uri "$base/api/8009/docs" -UseBasicParsing -TimeoutSec 10
if ($docs.Content -notmatch '/api/8009/openapi.json') { throw 'Swagger documentation has an incorrect API path.' }
Expect-HttpError 403 '/api/8009/state' 'GET' @{ Origin='https://example.org' } $null
Expect-HttpError 422 '/api/8009/experiments' 'POST' @{ Origin=$base } '{}'
$experiment = $null
$report = $null
if ($RunExperiment) {
    if ($state.state -notin @('idle','complete') -or $state.active_experiment_id) { throw 'An experiment is already active.' }
    $experiment = Post-Api '/api/8009/experiments' @{
        name='Windows browser gateway smoke'; failure_type='cpu'; target_container='host';
        parameters=@{ cpu_percent=10; duration_seconds=15 }
    }
    $id = $experiment.experiment_id
    if (-not $id) { throw 'Created experiment has no ID.' }
    try {
        Post-Api "/api/8009/experiments/$id/start" @{} | Out-Null
        $running = Read-Api '/api/8009/state'
        if ($running.state -ne 'running' -or $running.active_experiment_id -ne $id) { throw 'Experiment did not start.' }
        $deadline = (Get-Date).AddSeconds(75)
        do {
            Start-Sleep -Seconds 3
            $record = Read-Api "/api/8008/experiments/$id"
            if ($record.status -eq 'completed') { break }
            if ((Get-Date) -gt $deadline) { throw 'Experiment failed to complete naturally.' }
        } while ($true)
        $report = Read-Api "/api/8008/experiments/$id/report"
        $series = Read-Api "/api/8008/experiments/$id/metrics"
        if (-not $series.labels -or -not $series.datasets) { throw 'The experiment has no stored time-series metrics.' }
        $state = Read-Api '/api/8009/state'
        if ($state.state -notin @('idle','complete') -or $state.active_experiment_id) { throw 'Orchestrator did not finish the experiment.' }
    } finally {
        $current = Read-Api '/api/8009/state'
        if ($current.active_experiment_id -eq $id) { Post-Api "/api/8009/experiments/$id/stop" @{} | Out-Null }
    }
}
$latest = Read-Api '/api/8008/metrics/latest'
foreach ($name in @('cpu','memory','network')) {
    if (-not $latest.$name.timestamp) { throw "Missing stored $name metrics." }
    if (([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($latest.$name.timestamp)).TotalSeconds -gt 60) { throw "Stored $name metrics are stale." }
}
$result = [pscustomobject]@{
    ok=$true; checked_at=[DateTimeOffset]::UtcNow.ToString('o'); base_url=$base;
    state=$state.state; live_cpu=$cpu; live_memory=$memory; live_network=$network;
    stored_metrics=$latest; experiment_id=$experiment.experiment_id; experiment_report=$report
}
$json = $result | ConvertTo-Json -Depth 10
if ($OutputFile) { $json | Set-Content -LiteralPath $OutputFile -Encoding UTF8 }
Write-Output $json
