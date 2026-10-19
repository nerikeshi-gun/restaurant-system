$ErrorActionPreference = "Stop"

$CertPath = Join-Path $env:LOCALAPPDATA "GreitRestaurantOrder\certs\restaurant-local-ca.crt"
if (-not (Test-Path -LiteralPath $CertPath)) {
    Write-Host "Local CA certificate was not found." -ForegroundColor Yellow
    Write-Host "Run: .\setup-https.ps1 -IpAddress YOUR_PC_IP"
    exit 1
}

$Certificate = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CertPath)
$Existing = Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Thumbprint -eq $Certificate.Thumbprint }
if (-not $Existing) {
    Import-Certificate -FilePath $CertPath -CertStoreLocation Cert:\CurrentUser\Root | Out-Null
}

Write-Host "The local CA is trusted for the current Windows user." -ForegroundColor Green
Write-Host "Thumbprint: $($Certificate.Thumbprint)"
Write-Host "Close all Chrome windows, reopen Chrome, then use:"
Write-Host "https://192.168.11.2:8443/"
