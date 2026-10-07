$ProjectRoot = "D:\Capstone\D.S.F.S.T"

Write-Output "Stopping D.S.F.S.T Python services..."

Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -match "RunALL.py" -or
        $_.CommandLine -match "metrics_writer.py"
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Set-Location $ProjectRoot

Write-Output "Stopping Docker services..."

docker-compose down

Write-Output "D.S.F.S.T stopped."