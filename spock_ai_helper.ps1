# Spock AI Helper launcher (PowerShell).
#
# If you see "running scripts is disabled", use Spock-AI-Helper.bat instead, or:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\spock_ai_helper.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

Set-Location -LiteralPath $PSScriptRoot

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$script = Join-Path $PSScriptRoot "helper_main.py"

if (-not (Test-Path -LiteralPath $script)) {
    Write-Error "Missing helper_main.py in $PSScriptRoot"
    exit 1
}

# Prefer venv python (skip activate.ps1 — same ExecutionPolicy footgun).
if (Test-Path -LiteralPath $venvPy) {
    & $venvPy $script @args
    exit $LASTEXITCODE
}

Write-Host "No .venv Python found; using PATH python." -ForegroundColor Yellow
python $script @args
exit $LASTEXITCODE
