# Spock Engineering Maintenance launcher (PowerShell).
#
# If you see "running scripts is disabled", use Spock-Maintenance.bat instead, or:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\spock_maintenance.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

Set-Location -LiteralPath $PSScriptRoot

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$script = Join-Path $PSScriptRoot "spock_maintenance.py"

if (-not (Test-Path -LiteralPath $script)) {
    Write-Error "Missing spock_maintenance.py in $PSScriptRoot"
}

# Prefer venv python (skip activate.ps1 — same ExecutionPolicy footgun).
if (Test-Path -LiteralPath $venvPy) {
    & $venvPy $script @args
    exit $LASTEXITCODE
}

Write-Host "No .venv Python found; using PATH python." -ForegroundColor Yellow
python $script @args
exit $LASTEXITCODE
