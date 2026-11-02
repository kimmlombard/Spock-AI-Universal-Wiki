# Pre-scan ShareX PNGs in .\assets → GitHub-sized JPG gallery via LM Studio vision.
#
# Does NOT modify .\assets. Uses C:\Spock-Images-Temp as workspace.
# Writes .\gallery\ (docs\images\, manifest.json, docs\, mkdocs.yml).
#
# Prerequisites:
#   - LM Studio running with a vision-capable model loaded (default port 1234)
#   - Project .venv with Pillow + requests (Phase B)
#
# Example:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\prescan-screenshots.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\prescan-screenshots.ps1 -Force -Limit 3

[CmdletBinding()]
param(
    [string]$AssetsRoot = "",
    [string]$TempRoot = "C:\Spock-Images-Temp",
    [string]$GalleryRoot = "",
    [string]$LmStudioUrl = "http://localhost:1234/v1",
    [string]$Model = "qwen/qwen3.8-27b",
    [int]$MaxWidth = 1280,
    [int]$JpegQuality = 82,
    [double]$TimeoutSec = 180,
    [switch]$Force,
    [int]$Limit = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $AssetsRoot) { $AssetsRoot = Join-Path $RepoRoot "assets" }
if (-not $GalleryRoot) { $GalleryRoot = Join-Path $RepoRoot "gallery" }

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing $Python — create the project venv / run Phase B first."
}

$Helper = Join-Path $RepoRoot "scripts\prescan_screenshots.py"
if (-not (Test-Path -LiteralPath $Helper)) {
    throw "Missing $Helper"
}

Write-Host "Pre-scan screenshots"
Write-Host "  assets : $AssetsRoot"
Write-Host "  temp   : $TempRoot"
Write-Host "  gallery: $GalleryRoot"
Write-Host "  LM     : $LmStudioUrl  model=$Model"

$pyArgs = @(
    $Helper,
    "--assets-root", $AssetsRoot,
    "--temp-root", $TempRoot,
    "--gallery-root", $GalleryRoot,
    "--lm-studio-url", $LmStudioUrl,
    "--model", $Model,
    "--max-width", "$MaxWidth",
    "--jpeg-quality", "$JpegQuality",
    "--timeout", "$TimeoutSec"
)
if ($Force) { $pyArgs += "--force" }
if ($Limit -gt 0) { $pyArgs += @("--limit", "$Limit") }

& $Python @pyArgs
$exit = $LASTEXITCODE

if ($exit -eq 0) {
    Write-Host ""
    Write-Host "Preview gallery (optional):"
    Write-Host "  cd `"$GalleryRoot`""
    Write-Host "  mkdocs serve -a 127.0.0.1:8001"
}

exit $exit
