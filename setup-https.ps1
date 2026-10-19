param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(?:\d{1,3}\.){3}\d{1,3}$')]
    [string]$IpAddress
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$OpenSslCandidates = @(
    "C:\Program Files\Git\usr\bin\openssl.exe",
    "C:\Program Files\Git\mingw64\bin\openssl.exe"
)
$OpenSsl = $OpenSslCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $OpenSsl) {
    Write-Host "OpenSSL was not found. Install Git for Windows first." -ForegroundColor Red
    exit 1
}

$CertDir = Join-Path $env:LOCALAPPDATA "GreitRestaurantOrder\certs"
New-Item -ItemType Directory -Force -Path $CertDir | Out-Null

$CaKey = Join-Path $CertDir "restaurant-local-ca.key"
$CaCert = Join-Path $CertDir "restaurant-local-ca.crt"
$CaConfig = Join-Path $CertDir "restaurant-local-ca.cnf"
$ServerKey = Join-Path $CertDir "restaurant-server.key"
$ServerCsr = Join-Path $CertDir "restaurant-server.csr"
$ServerCert = Join-Path $CertDir "restaurant-server.crt"
$ServerExt = Join-Path $CertDir "restaurant-server.ext"

if (-not (Test-Path -LiteralPath $CaKey)) {
    & $OpenSsl genrsa -out $CaKey 2048
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the local CA key." }
}

$CaIsValid = $false
if (Test-Path -LiteralPath $CaCert) {
    $CaDetails = & $OpenSsl x509 -in $CaCert -noout -text
    $CaText = $CaDetails -join "`n"
    $CaIsValid = ($LASTEXITCODE -eq 0 -and $CaText -match "CA:TRUE" -and $CaText -match "Certificate Sign")
}
if (-not $CaIsValid) {
    @"
[req]
distinguished_name=dn
x509_extensions=v3_ca
prompt=no

[dn]
CN=Restaurant Order Local CA

[v3_ca]
basicConstraints=critical,CA:TRUE,pathlen:0
keyUsage=critical,keyCertSign,cRLSign
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always,issuer
"@ | Set-Content -LiteralPath $CaConfig -Encoding Ascii
    & $OpenSsl req -x509 -new -sha256 -days 3650 -key $CaKey -out $CaCert -config $CaConfig
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the local CA certificate." }
}

& $OpenSsl genrsa -out $ServerKey 2048
if ($LASTEXITCODE -ne 0) { throw "Failed to create the server key." }
& $OpenSsl req -new -key $ServerKey -out $ServerCsr -subj "/CN=$IpAddress"
if ($LASTEXITCODE -ne 0) { throw "Failed to create the server request." }

@"
subjectAltName=IP:$IpAddress,IP:127.0.0.1,DNS:localhost
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
"@ | Set-Content -LiteralPath $ServerExt -Encoding Ascii

& $OpenSsl x509 -req -in $ServerCsr -CA $CaCert -CAkey $CaKey -CAcreateserial -out $ServerCert -days 825 -sha256 -extfile $ServerExt
if ($LASTEXITCODE -ne 0) { throw "Failed to create the server certificate." }

Write-Host "HTTPS certificate was created." -ForegroundColor Green
Write-Host "1. Trust it on this PC with: .\install-pc-ca.ps1"
Write-Host "2. Start HTTP with: .\start.ps1"
Write-Host "3. On Android open: http://${IpAddress}:8000/setup/local-ca"
Write-Host "4. Install the downloaded certificate as a CA certificate."
Write-Host "5. Stop HTTP, then run: .\start-https.ps1"
Write-Host "6. On every device use: https://${IpAddress}:8443/"
