param(
    [ValidateSet("Auto", "Docker", "Local")]
    [string]$Mode = "Auto",
    [string]$Database = "common_platform",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 5432,
    [string]$AdminUser = "postgres",
    [switch]$Rebuild,
    [switch]$IncludeTestData
)

$ErrorActionPreference = "Stop"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom

function Get-DockerPath {
    $command = Get-Command docker -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $desktopPath = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    if (Test-Path -LiteralPath $desktopPath) { return $desktopPath }
    return $null
}

function Get-PsqlPath {
    $command = Get-Command psql -ErrorAction SilentlyContinue
    if ($command -and (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $command.Source) "createdb.exe"))) {
        return $command.Source
    }
    $versions = Get-ChildItem -LiteralPath "C:\Program Files\PostgreSQL" -Directory -ErrorAction SilentlyContinue |
        Sort-Object { [int](($_.Name -split '\.')[0]) } -Descending
    foreach ($version in $versions) {
        $candidate = Join-Path $version.FullName "bin\psql.exe"
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

$dockerPath = Get-DockerPath
$dockerReady = $false
if ($Mode -ne "Local" -and $dockerPath) {
    $savedErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $dockerPath info --format '{{.ServerVersion}}' 2>$null | Out-Null
    $dockerReady = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $savedErrorPreference
}

if ($Mode -eq "Docker" -and -not $dockerReady) {
    throw "Docker Desktop Linux engine is unavailable. Start it or specify -Mode Local."
}
if ($Mode -eq "Auto") {
    $Mode = if ($dockerReady) { "Docker" } else { "Local" }
}

$sqlFiles = @("001_schema.sql", "002_seed.sql")
if ($IncludeTestData) { $sqlFiles += @("003_test_data.sql", "004_verify.sql") }
foreach ($file in $sqlFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $file))) {
        throw "SQL file was not found: $file"
    }
}

if ($Mode -eq "Docker") {
    if (-not $env:COMMON_PLATFORM_PASSWORD -and -not (Test-Path -LiteralPath (Join-Path $PSScriptRoot ".env"))) {
        throw "Copy .env.example to .env and set COMMON_PLATFORM_PASSWORD."
    }
    Push-Location $PSScriptRoot
    try {
        & $dockerPath compose up -d
        if ($LASTEXITCODE -ne 0) { throw "Could not start the PostgreSQL container." }
        for ($i = 0; $i -lt 30; $i++) {
            & $dockerPath compose exec -T db pg_isready -U platform -d common_platform *> $null
            if ($LASTEXITCODE -eq 0) { break }
            Start-Sleep -Seconds 2
        }
        if ($LASTEXITCODE -ne 0) { throw "PostgreSQL did not become ready." }
        if ($Rebuild) {
            & $dockerPath compose exec -T db psql -v ON_ERROR_STOP=1 -U platform -d common_platform `
                -c "DROP SCHEMA IF EXISTS platform CASCADE;"
            if ($LASTEXITCODE -ne 0) { throw "Could not remove the existing platform schema." }
        }
        foreach ($file in $sqlFiles) {
            Write-Host "Applying $file ..."
            Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot $file) |
                & $dockerPath compose exec -T db psql -X -v ON_ERROR_STOP=1 -U platform -d common_platform
            if ($LASTEXITCODE -ne 0) { throw "Failed to apply $file." }
        }
    } finally {
        Pop-Location
    }
} else {
    $psqlPath = Get-PsqlPath
    if (-not $psqlPath) { throw "psql was not found. Install PostgreSQL 15 or later." }
    $binDir = Split-Path -Parent $psqlPath
    $createdbPath = Join-Path $binDir "createdb.exe"
    $dropdbPath = Join-Path $binDir "dropdb.exe"

    $dbExistsResult = & $psqlPath -X -h $HostName -p $Port -U $AdminUser -d postgres `
        -tAc "SELECT 1 FROM pg_database WHERE datname='$Database'"
    if ($LASTEXITCODE -ne 0) { throw "Could not connect to PostgreSQL." }
    $databaseExists = [bool]($dbExistsResult -match "1")
    if ($databaseExists -and -not $Rebuild) {
        throw "Database $Database already exists. Specify -Rebuild only when replacement is intended."
    }
    if ($databaseExists) {
        & $dropdbPath -h $HostName -p $Port -U $AdminUser --force $Database
        if ($LASTEXITCODE -ne 0) { throw "Could not drop database $Database." }
    }
    & $createdbPath -h $HostName -p $Port -U $AdminUser $Database
    if ($LASTEXITCODE -ne 0) { throw "Could not create database $Database." }
    foreach ($file in $sqlFiles) {
        Write-Host "Applying $file ..."
        & $psqlPath -X -v ON_ERROR_STOP=1 -h $HostName -p $Port -U $AdminUser -d $Database `
            -f (Join-Path $PSScriptRoot $file)
        if ($LASTEXITCODE -ne 0) { throw "Failed to apply $file." }
    }
}

Write-Host "Common platform database build completed. Mode=$Mode Database=$Database"
