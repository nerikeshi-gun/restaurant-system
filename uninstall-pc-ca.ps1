$ErrorActionPreference = "Stop"

$CertPath = Join-Path $env:LOCALAPPDATA "GreitRestaurantOrder\certs\restaurant-local-ca.crt"
if (-not (Test-Path -LiteralPath $CertPath)) {
    Write-Host "Local CA certificate file was not found." -ForegroundColor Yellow
    exit 1
}

$Certificate = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CertPath)
$Installed = Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Thumbprint -eq $Certificate.Thumbprint }
if ($Installed) {
    $Installed | Remove-Item
    Write-Host "The local CA was removed from the current Windows user." -ForegroundColor Green
} else {
    Write-Host "The local CA is not installed for the current Windows user."
}
