param(
    [ValidateSet("Auto", "Docker", "Local")]
    [string]$Mode = "Auto",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 5432,
    [string]$AdminUser = "postgres",
    [string]$Database = "common_platform_verify"
)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "initialize.ps1") -Mode $Mode -HostName $HostName -Port $Port `
    -AdminUser $AdminUser -Database $Database -Rebuild -IncludeTestData
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
