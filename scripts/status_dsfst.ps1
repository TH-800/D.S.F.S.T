Write-Output ""
Write-Output "===== D.S.F.S.T STATUS ====="
Write-Output ""

Write-Output "Docker containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

Write-Output ""
Write-Output "Metrics API:"

try {
    $response = Invoke-RestMethod `
        -Uri "http://127.0.0.1:8008/health" `
        -TimeoutSec 5

    $response | ConvertTo-Json
}
catch {
    Write-Output "Metrics API unavailable."
}

Write-Output ""
Write-Output "Python services:"

Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -match "RunALL.py" -or
        $_.CommandLine -match "metrics_writer.py"
    } |
    Select-Object ProcessId, CommandLine