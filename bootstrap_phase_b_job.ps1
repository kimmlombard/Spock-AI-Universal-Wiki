# bootstrap_phase_b_job.ps1 — full dependency tier, installed outside any GUI process

param(
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [Alias("HeavyDeps")][switch]$FullDeps,
    [switch]$Validate
)

$ErrorActionPreference = "Continue"
$InstallRoot = $InstallRoot.TrimEnd('\', '/')
$bootstrap = Join-Path $InstallRoot "bootstrap.ps1"
$resultFile = Join-Path $InstallRoot "bootstrap_phase_b_result.txt"
$venvPy = Join-Path $InstallRoot ".venv\Scripts\python.exe"

function Write-Result([string]$Text) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $resultFile -Value "[$stamp] $Text" -Encoding UTF8
}

Set-Content -LiteralPath $resultFile -Value "Spock Phase B job started." -Encoding UTF8
Write-Result "InstallRoot=$InstallRoot FullDeps=$FullDeps Validate=$Validate"

if (-not (Test-Path -LiteralPath $bootstrap)) {
    Write-Result "ERROR: missing $bootstrap"
    exit 1
}

# Install the full tier only. Do not re-enter pip_wizard — Phase A already
# installed the UI packages, and reinstalling them while the Bringup menu
# holds the venv open is a common WinError 32 on Windows.
$psArgs = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", $bootstrap,
    "-NonInteractive", "-EmitEvents", "-NoHandOffGui",
    "-InstallRoot", $InstallRoot,
    "-FromStep", "pip_full"
)
if ($FullDeps) { $psArgs += "-FullDeps" } else { $psArgs += "-SkipFullDeps" }
if ($Validate) { $psArgs += "-Validate" } else { $psArgs += "-SkipValidate" }

Write-Host "Running Phase B job. Install root: $InstallRoot"
$p = Start-Process -FilePath "powershell.exe" -ArgumentList $psArgs `
    -WorkingDirectory $InstallRoot -Wait -PassThru -NoNewWindow
$code = if ($p) { [int]$p.ExitCode } else { 1 }
Write-Result "bootstrap.ps1 exit code: $code"

if ($code -eq 0 -and $FullDeps -and (Test-Path -LiteralPath $venvPy)) {
    Set-Content -LiteralPath (Join-Path $InstallRoot "bootstrap_full_deps.ok") `
        -Value "ok`nsource=phase_b_job`n" -Encoding UTF8
    Write-Result "PHASE_B_OK"
} elseif ($code -eq 0) {
    Write-Result "PHASE_B_OK (no full deps requested)"
} else {
    Write-Result "PHASE_B_FAILED"
}

Write-Host "Phase B finished (exit $code). Result: $resultFile"
exit $code
