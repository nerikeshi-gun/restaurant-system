$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$CertDir = Join-Path $env:LOCALAPPDATA "GreitRestaurantOrder\certs"
$ServerKey = Join-Path $CertDir "restaurant-server.key"
$ServerCert = Join-Path $CertDir "restaurant-server.crt"

if (-not (Test-Path -LiteralPath $PythonPath)) {
    Write-Host "Python virtual environment was not found. Run the README setup first." -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path -LiteralPath $ServerKey) -or -not (Test-Path -LiteralPath $ServerCert)) {
    Write-Host "HTTPS certificate was not found." -ForegroundColor Yellow
    Write-Host "Run: .\setup-https.ps1 -IpAddress YOUR_PC_IP"
    exit 1
}

$HttpsPort = 8443
$ExistingListener = Get-NetTCPConnection -LocalPort $HttpsPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($ExistingListener) {
    $ExistingProcess = Get-Process -Id $ExistingListener.OwningProcess -ErrorAction SilentlyContinue
    $ProcessLabel = if ($ExistingProcess) { "$($ExistingProcess.ProcessName) (PID $($ExistingProcess.Id))" } else { "PID $($ExistingListener.OwningProcess)" }
    Write-Host "Port $HttpsPort is already in use by $ProcessLabel." -ForegroundColor Yellow
    Write-Host "If the restaurant system is already open, use https://localhost:$HttpsPort/ without starting it again."
    Write-Host "Otherwise, close that process and run .\start-https.ps1 again."
    exit 1
}

Set-Location -LiteralPath $ProjectRoot
& $PythonPath -m uvicorn app.main:app --host 0.0.0.0 --port $HttpsPort --ssl-keyfile $ServerKey --ssl-certfile $ServerCert
