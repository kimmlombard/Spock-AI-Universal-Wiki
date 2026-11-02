# spock_menu.ps1 - console launcher for Spock-Onboarding (aligned with Bringup Menu 1-16)
# ASCII-only strings for Windows PowerShell 5.x encoding safety.
# Prefer Spock-Menu.bat for the PyQt6 GUI; this script is the console fallback.
# Linux / WSL peer: ./spock_menu.sh (uses bootstrap.sh for Phase A/B).

param(
    [string]$Root = ""
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Root) { $Root = $ScriptDir }
$Root = (Resolve-Path -LiteralPath $Root).Path
Set-Location -LiteralPath $Root

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
$Bootstrap = Join-Path $Root "bootstrap.ps1"
$PhaseB = Join-Path $Root "bootstrap_phase_b_job.ps1"

function Get-VenvPython {
    if (Test-Path -LiteralPath $VenvPy) { return $VenvPy }
    return $null
}

function Test-PyQt6Ready {
    $py = Get-VenvPython
    if (-not $py) { return $false }
    & $py -c "import PyQt6" 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Show-Header {
    Write-Host ""
    Write-Host "=== Spock Onboarding Menu (console) ===" -ForegroundColor Cyan
    Write-Host "Root: $Root"
    Write-Host "Tip: Spock-Menu.bat opens the PyQt6 Bringup Menu when ready."
    $py = Get-VenvPython
    if ($py) {
        Write-Host "venv: $py" -ForegroundColor Green
        if (Test-PyQt6Ready) {
            Write-Host "log UI: PyQt6 progress modal available" -ForegroundColor Green
        }
        else {
            Write-Host "log UI: console only (PyQt6 not importable yet)" -ForegroundColor Yellow
        }
    }
    else {
        Write-Host "venv: (missing - run Phase A)" -ForegroundColor Yellow
    }
    Write-Host ""
}

function Show-Menu {
    Write-Host "1) Phase A - Python / venv / PyQt6 deps"
    Write-Host "2) Phase B - full deps (ingest / extractors / WebEngine)"
    Write-Host "3) Acquire runtime + models (llama-server + GGUFs)"
    Write-Host "4) Bring up servers (:8080 embed + :8081 chat)"
    Write-Host "5) Status / probe (write spock_ready_last.json)"
    Write-Host "6) MCP Adapter (stdio + HTTP tools for Cursor / llama.cpp)"
    Write-Host "7) Embedding Profile / RAG API"
    Write-Host "8) Open Live Monitor (Ship Status GUI)"
    Write-Host "9) Run Wiki Scan (wiki_agent.py + live log)"
    Write-Host "10) Ask AI / Deep Dive (Engineering Deck)"
    Write-Host "11) Spock Navigation Station (full left-nav GUI)"
    Write-Host "12) Spock Engineering Maintenance (wiki / DB console)"
    Write-Host "13) Spock UIEG KnowledgeBase (external capture)"
    Write-Host "14) Stop servers / kill all processes"
    Write-Host "15) Re-embed / switch embedding model (clear vectors, keep docs)"
    Write-Host "16) Exit"
    Write-Host ""
}

function Invoke-PhaseA {
    Write-Host "Running Phase A..." -ForegroundColor Cyan
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bootstrap `
        -NonInteractive -EmitEvents -NoHandOffGui -InstallRoot $Root
    Write-Host "Phase A exit: $LASTEXITCODE"
}

function Invoke-PhaseB {
    Write-Host "Running Phase B job..." -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $PhaseB)) {
        Write-Host "Missing $PhaseB" -ForegroundColor Red
        return
    }
    if (Test-PyQt6Ready) {
        $py = Get-VenvPython
        $env:PYTHONPATH = $Root
        & $py -m spock_progress_log --title "Phase B - full deps" --root "$Root" -- `
            powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PhaseB `
            -InstallRoot $Root -FullDeps -Validate
        Write-Host "Phase B exit: $LASTEXITCODE"
        return
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PhaseB `
        -InstallRoot $Root -FullDeps -Validate
    Write-Host "Phase B exit: $LASTEXITCODE"
}

function Invoke-PythonModule {
    param(
        [Parameter(Mandatory = $true)][string[]]$ModuleArgs,
        [string]$Title = ""
    )
    $py = Get-VenvPython
    if (-not $py) {
        Write-Host "No .venv - run Phase A first." -ForegroundColor Red
        return 2
    }
    $env:PYTHONPATH = $Root

    if ($Title -and (Test-PyQt6Ready)) {
        Write-Host "Opening progress log: $Title" -ForegroundColor Cyan
        & $py -m spock_progress_log --title $Title --root "$Root" -- `
            $py -u -m @ModuleArgs
        return [int]$LASTEXITCODE
    }

    Write-Host "---- $Title ----" -ForegroundColor DarkGray
    & $py -u -m @ModuleArgs 2>&1 | ForEach-Object { Write-Host $_ }
    $code = [int]$LASTEXITCODE
    Write-Host "---- exit: $code ----" -ForegroundColor DarkGray
    return $code
}

function Invoke-SuiteScript {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][string[]]$Args
    )
    $py = Get-VenvPython
    if (-not $py) {
        Write-Host "No .venv - run Phase A first." -ForegroundColor Red
        return
    }
    if (-not (Test-PyQt6Ready)) {
        Write-Host "PyQt6 required - run Phase A first." -ForegroundColor Red
        return
    }
    Write-Host "Opening $Title (close the window to return here)..." -ForegroundColor Cyan
    $env:PYTHONPATH = $Root
    & $py @Args
    Write-Host "$Title exit: $LASTEXITCODE"
}

Show-Header
$quit = $false
while (-not $quit) {
    Show-Menu
    $choice = (Read-Host "Select").Trim()
    switch -Regex ($choice) {
        "^1$" { Invoke-PhaseA }
        "^2$" { Invoke-PhaseB }
        "^3$" {
            $null = Invoke-PythonModule -Title "Acquire runtime + models" `
                -ModuleArgs @("spock_bringup", "--root", "$Root", "acquire")
        }
        "^4$" {
            $null = Invoke-PythonModule -Title "Bring up servers" `
                -ModuleArgs @("spock_bringup", "--root", "$Root", "up")
        }
        "^5$" {
            $null = Invoke-PythonModule -Title "Status / probe" `
                -ModuleArgs @("spock_bringup", "--root", "$Root", "status")
            $ready = Join-Path $Root "spock_ready_last.json"
            if (Test-Path -LiteralPath $ready) {
                Write-Host "Wrote $ready" -ForegroundColor Green
            }
        }
        "^6$" {
            Invoke-SuiteScript -Title "MCP Adapter" -Args @("-m", "spock_mcp_adapter", "--root", "$Root")
        }
        "^7$" {
            Invoke-SuiteScript -Title "Embedding / RAG" -Args @("-m", "spock_rag_adapter", "--root", "$Root")
        }
        "^8$" {
            Invoke-SuiteScript -Title "Live Monitor" -Args @("-m", "spock_live_monitor", "--root", "$Root")
        }
        "^9$" {
            Invoke-SuiteScript -Title "Wiki Scan" -Args @("-m", "spock_wiki_adapter", "--root", "$Root")
        }
        "^10$" {
            Invoke-SuiteScript -Title "Ask AI / Deep Dive" -Args @("-m", "EngineeringDeck")
        }
        "^11$" {
            Invoke-SuiteScript -Title "Navigation Station" -Args @("$Root\spock_navigation.py")
        }
        "^12$" {
            Invoke-SuiteScript -Title "Engineering Maintenance" -Args @("$Root\spock_maintenance.py")
        }
        "^13$" {
            Invoke-SuiteScript -Title "UIEG KnowledgeBase" -Args @("$Root\spock_UIEG_KnowledgeBase.py")
        }
        "^14$" {
            $null = Invoke-PythonModule -Title "Stop servers" `
                -ModuleArgs @("spock_bringup", "--root", "$Root", "down")
        }
        "^15$" {
            Write-Host ""
            Write-Host "Re-embed clears document vectors and kb_embedding_corpus." -ForegroundColor Yellow
            Write-Host "Documents/settings are kept; prior embeddings will be lost." -ForegroundColor Yellow
            $c1 = (Read-Host "Type Re-embed to continue, or Skip").Trim()
            if ($c1 -notin @("Re-embed", "re-embed", "RE-EMBED")) {
                Write-Host "Skipped." -ForegroundColor DarkGray
                break
            }
            $c2 = (Read-Host "Confirm: prior embedding data will be lost. Type YES").Trim()
            if ($c2 -ne "YES") {
                Write-Host "Cancelled." -ForegroundColor DarkGray
                break
            }
            $null = Invoke-PythonModule -Title "Re-embed / clear embeddings" `
                -ModuleArgs @("spock_bringup", "--root", "$Root", "reembed", "--yes")
        }
        "^(16|[Qq])$" {
            $quit = $true
        }
        default { Write-Host "Unknown choice." -ForegroundColor Yellow }
    }
    if (-not $quit) {
        Write-Host ""
    }
}

Write-Host "Bye."
