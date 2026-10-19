$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonPath)) {
    Write-Host "Python virtual environment was not found." -ForegroundColor Yellow
    Write-Host "Run: py -3.12 -m venv .venv"
    Write-Host "Then: .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

Set-Location -LiteralPath $ProjectRoot
& $PythonPath -m uvicorn app.main:app --host 0.0.0.0 --port 8000
