#D:

#cd D:\Spock-AI-Universal-Wiki

#.\.venv\scripts\activate.ps1

# Spock-Onboarding MkDocs launcher (PowerShell).
#
# Ensures the llama-server chat model is up on :8081 (start it if needed),
# then presents a menu:
#   1) Build .\docs (.md)   - LLM-enhance and save the markdown sources
#   2) Build .\site (.html) - full mkdocs build (docs/*.md -> site/*.html)
#   3) Build both           - enhance sources, then build the site
#   4) mkdocs serve         - live preview at http://127.0.0.1:8000
#   5) Exit
#
# All output is also tee'd to .\logs\mkdocs.log.
#
# If you see "running scripts is disabled", use:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\spock-onboarding-mkdocs.ps1

[CmdletBinding()]
param(
    [int]$Port = 8081
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

Set-Location -LiteralPath $PSScriptRoot

$LogsDir = Join-Path $PSScriptRoot "logs"
$null = New-Item -ItemType Directory -Force -Path $LogsDir

$ModelGguf = "C:\Users\kimml\.lmstudio\models\JackAgentLead\Jack-3.8-27B-Coder-16GB-VRAM\Jack-3.8-27B-Coder-16GB-VRAM.gguf"

$LocalLlama = Join-Path $PSScriptRoot "tools\llama-server\llama-server.exe"
$SysMkdocs = Join-Path $PSScriptRoot ".venv\Scripts\mkdocs.exe"
$SysPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

$env:DISABLE_MKDOCS_2_WARNING = "true"  # small plugin warning
$env:NO_MKDOCS_2_WARNING = "true"       # Material-for-MkDocs 2.0 banner

# ---- Helpers ------------------------------------------------

function Test-PortOpen {
    param([int]$PortNumber)
    $tcp = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $tcp.BeginConnect("127.0.0.1", $PortNumber, $null, $null)
        return $iar.AsyncWaitHandle.WaitOne(300, $false) -and $tcp.Connected
    }
    catch {
        return $false
    }
    finally {
        $tcp.Dispose()
    }
}

function Resolve-Command {
    param([string]$Path, [string]$CommandName, [string]$Hint)
    if (Test-Path -LiteralPath $Path) { return $Path }
    $cmd = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    Write-Error $Hint
    exit 1
}

function Resolve-LlamaServer {
    if ($env:LLAMA_SERVER_PATH -and (Test-Path -LiteralPath $env:LLAMA_SERVER_PATH)) {
        return $env:LLAMA_SERVER_PATH
    }
    if (Test-Path -LiteralPath $LocalLlama) { return $LocalLlama }
    $cmd = Get-Command llama-server.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "llama-server.exe not found. Install under tools\llama-server\ or set LLAMA_SERVER_PATH."
}

function Wait-ForLlamaReady {
    param([int]$PortNumber)
    $url = "http://localhost:$PortNumber/health"
    for ($i = 0; $i -lt 180; $i++) {
        try {
            $r = Invoke-RestMethod -Uri $url -TimeoutSec 2
            if ($r.status -eq "ok") { return $true }
        }
        catch {
            # still loading: /health returns 503 until the model is ready
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Ensure-LlamaServer {
    if (Test-PortOpen -PortNumber $Port) {
        $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
            Select-Object -First 1
        Write-Host "llama-server already listening on :$Port (pid $($listener.OwningProcess))." -ForegroundColor Green
        return
    }
    Write-Host "No listener on :$Port - starting llama-server..." -ForegroundColor Yellow
    if (-not (Test-Path -LiteralPath $ModelGguf)) {
        Write-Error "Model GGUF not found: $ModelGguf"
        exit 1
    }
    $exe = Resolve-LlamaServer
    $llamaOut = Join-Path $LogsDir "llama-server-$Port.out.log"
    $llamaErr = Join-Path $LogsDir "llama-server-$Port.err.log"
    $llamaArgs = @("-m", $ModelGguf, "--host", "0.0.0.0", "--port", "$Port", "-c", "32768", "-ngl", "-1", "-b", "512", "-ub", "512")
    $proc = Start-Process -FilePath $exe -ArgumentList $llamaArgs -PassThru `
        -RedirectStandardOutput $llamaOut -RedirectStandardError $llamaErr -WindowStyle Hidden
    Write-Host "Started llama-server (pid $($proc.Id)). Waiting for model load..." -ForegroundColor Yellow
    if (-not (Wait-ForLlamaReady -PortNumber $Port)) {
        Write-Error "llama-server did not become ready within 180s. See $llamaOut"
        exit 1
    }
    Write-Host "Model loaded - llama-server ready on :$Port." -ForegroundColor Green
}

# ---- Actions -------------------------------------------------

function Write-LineAndLog {
    process {
        # mkdocs writes the banner/tracebacks to stderr, which PowerShell wraps
        # in ErrorRecords ("RemoteException") - unwrap so the log stays clean.
        $line = if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { "$_" }
        Write-Host $line
        Out-File -InputObject $line -FilePath $LogPath -Append -Encoding utf8
    }
}

function Start-LogSession {
    param([string]$ActionName)
    "" | Out-File -FilePath $LogPath -Append -Encoding utf8
    "==== mkdocs $ActionName $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ====" | Out-File -FilePath $LogPath -Append -Encoding utf8
}

function Invoke-EnhanceDocs {
    Start-LogSession "enhance-docs"
    Write-Host "Enhancing .\docs (.md) sources..." -ForegroundColor Cyan
    & $PythonScript enhance_docs.py 2>&1 | Write-LineAndLog
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Enhance step failed (exit $LASTEXITCODE)." -ForegroundColor Red
    }
    else {
        Write-Host "Enhance step done." -ForegroundColor Green
    }
}

function Invoke-MkdocsBuild {
    Start-LogSession "build"
    Write-Host "Running: mkdocs build (docs/*.md -> site/*.html)" -ForegroundColor Cyan
    & $mkdocs build 2>&1 | Write-LineAndLog
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Build failed (exit $LASTEXITCODE)." -ForegroundColor Red
    }
    else {
        Write-Host "Build done." -ForegroundColor Green
    }
}

function Invoke-MkdocsServe {
    Start-LogSession "serve"
    Write-Host "Running: mkdocs serve (Ctrl+C to stop)" -ForegroundColor Cyan
    & $mkdocs serve 2>&1 | Write-LineAndLog
    Write-Host "Serve stopped." -ForegroundColor Yellow
}

# ---- Resolve tooling -------------------------------------------

$mkdocs = Resolve-Command $SysMkdocs "mkdocs" "mkdocs not found. Run: .venv\Scripts\python.exe -m pip install -r requirements-docs.txt"
$pythonExe = Resolve-Command $SysPython "python" "Python not found. mkdocs/llm_enhance need Python 3.12 with openai installed."
$PythonScript = $pythonExe
$LogPath = Join-Path $LogsDir "mkdocs.log"

Ensure-LlamaServer

# ---- Menu -------------------------------------------------------

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   Spock-Onboarding MkDocs menu" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

do {
    Write-Host ""
    Write-Host "  1) Build .\docs (.md)   - LLM-enhance and save markdown sources"
    Write-Host "  2) Build .\site (.html) - full mkdocs build"
    Write-Host "  3) Build both"
    Write-Host "  4) mkdocs serve         - live preview at http://127.0.0.1:8000"
    Write-Host "  5) Exit"
    $choice = Read-Host "`nChoose [1-5]"

    switch ($choice) {
        "1" { Invoke-EnhanceDocs }
        "2" { Invoke-MkdocsBuild }
        "3" { Invoke-EnhanceDocs; Invoke-MkdocsBuild }
        "4" { Invoke-MkdocsServe }
        "5" { Write-Host "Goodbye." -ForegroundColor Green }
        default { Write-Host "Invalid choice: $choice" -ForegroundColor Yellow }
    }
} while ($choice -ne "5")