$ErrorActionPreference = "Stop"

$ProjectRoot = "D:\Capstone\D.S.F.S.T"
$Python = Join-Path $ProjectRoot "venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "logs"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

Set-Location $ProjectRoot

Write-Output "Waiting for Docker Desktop..."

$dockerReady = $false

for ($i = 0; $i -lt 60; $i++) {
    try {
        docker info *> $null

        if ($LASTEXITCODE -eq 0) {
            $dockerReady = $true
            break
        }
    }
    catch {
    }

    Start-Sleep -Seconds 5
}

if (-not $dockerReady) {
    throw "Docker Engine was not ready after 5 minutes."
}

Write-Output "Starting Docker services..."

docker-compose up -d

if ($LASTEXITCODE -ne 0) {
    throw "docker-compose failed."
}

Write-Output "Starting D.S.F.S.T backend..."

Start-Process `
    -FilePath $Python `
    -ArgumentList "RunALL.py" `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput "$LogDir\runall.log" `
    -RedirectStandardError "$LogDir\runall-error.log" `
    -WindowStyle Hidden

Start-Sleep -Seconds 10

Write-Output "Starting metrics writer..."

Start-Process `
    -FilePath $Python `
    -ArgumentList "metrics_writer.py" `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput "$LogDir\metrics-writer.log" `
    -RedirectStandardError "$LogDir\metrics-writer-error.log" `
    -WindowStyle Hidden

Write-Output "D.S.F.S.T startup completed."