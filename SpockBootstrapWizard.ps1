# bootstrap.ps1
# Spock first-time setup for Windows 11 (hybrid: Phase A console → Phase B GUI control).
#
# Double-click Setup-Spock.bat (ExecutionPolicy Bypass).
#
# Phase A (console): Python 3.15 → install root → acquire → folders → db → venv → pip wizard deps
# Phase B (default): hand off to SpockBootstrapWizard.py for live log / progress / optional steps
#
# Machine control:
#   -NonInteractive -EmitEvents -InstallRoot <path> -OnlyStep venv
#   -HeavyDeps / -Validate / -SkipHeavyDeps / -SkipValidate / -SkipWizard
#   -HandOffGui (default when SpockBootstrapWizard.py exists) / -NoHandOffGui
#
# Events (when -EmitEvents): one JSON object per stdout line
#   step_start | log | step_end | progress | done | error | need_elevation

param(
    [switch]$Elevated,
    [switch]$NonInteractive,
    [switch]$EmitEvents,
    [string]$InstallRoot = "",
    [switch]$SkipAcquire,
    [switch]$SkipWizard,
    [switch]$SkipHeavyDeps,
    [switch]$SkipValidate,
    [switch]$HeavyDeps,
    [switch]$Validate,
    [switch]$HandOffGui,
    [switch]$NoHandOffGui,
    [string]$FromStep = "",
    [string]$OnlyStep = ""
)

$ErrorActionPreference = "Stop"

# --- Configuration ------------------------------------------------------------
$PY_MAJOR_MINOR  = "3.15"
$PY_FULL         = "3.15.6"
$WINGET_PY_ID    = "Python.Python.3.15"
$PY_INSTALLER_URL = "https://www.python.org/ftp/python/$PY_FULL/python-$PY_FULL-amd64.exe"
$PY_INSTALLER    = "python-$PY_FULL-amd64.exe"

$GITHUB_OWNER    = "kimmlombard"
$GITHUB_REPO     = "Spock-Universal-AI-Wiki"
$GITHUB_BRANCH   = "cursor/nav-station-suite-ux"
$REPO_ZIP_URL    = "https://github.com/$GITHUB_OWNER/$GITHUB_REPO/archive/refs/heads/$GITHUB_BRANCH.zip"
$REPO_EXTRACT    = "$GITHUB_REPO-$($GITHUB_BRANCH.Replace('/','-'))"

$DEFAULT_INSTALL_ROOT = Join-Path $env:LOCALAPPDATA "Spock-Universal-AI-Wiki"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$LOG_FILE   = Join-Path $SCRIPT_DIR "bootstrap.log"

$FOLDER_TREE = @(
    "backups", "captured_files", "data", "data\blobs", "data\quarantine",
    "logs", "models", "promoted_research", "quarantine", "research_raw",
    "scripts", "templates", "wiki", "wiki\synthesis", "wiki\architecture",
    "wiki\howto", "wiki\security"
)

$WIZARD_DEPS = @("PyQt6", "requests", "psutil", "huggingface_hub")

$STEP_ORDER = @(
    "python", "install_root", "acquire", "folders", "database",
    "venv", "pip_wizard", "handoff_gui", "onboarding", "pip_full", "validate"
)
$script:StepTotal = $STEP_ORDER.Count
$script:pythonExe = $null
$script:venvPython = $null
$script:installRoot = $null
$script:appHere = $false

# Resolve install root EARLY so -FromStep / -OnlyStep can skip the install_root
# step without leaving $script:installRoot empty (Join-Path would crash later).
if ($InstallRoot -and $InstallRoot.Trim()) {
    $script:installRoot = $InstallRoot.Trim().TrimEnd('\', '/')
} elseif ($env:SPOCK_INSTALL_ROOT -and $env:SPOCK_INSTALL_ROOT.Trim()) {
    $script:installRoot = $env:SPOCK_INSTALL_ROOT.Trim().TrimEnd('\', '/')
} else {
    $script:installRoot = $SCRIPT_DIR
}
$seedVenv = Join-Path $script:installRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $seedVenv) {
    $script:venvPython = $seedVenv
}
$script:appHere = Test-Path -LiteralPath (Join-Path $script:installRoot "SpockOnboardingWizard.py")
if (-not $script:appHere) {
    $script:appHere = Test-Path -LiteralPath (Join-Path $SCRIPT_DIR "SpockOnboardingWizard.py")
}

# --- Event / log helpers ------------------------------------------------------
function Write-Event {
    param(
        [Parameter(Mandatory = $true)][string]$Type,
        [hashtable]$Fields = @{}
    )
    if (-not $EmitEvents) { return }
    $obj = @{ event = $Type; ts = (Get-Date -Format "o") }
    foreach ($k in $Fields.Keys) { $obj[$k] = $Fields[$k] }
    $json = ($obj | ConvertTo-Json -Compress -Depth 6)
    [Console]::Out.WriteLine($json)
}

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "[$stamp] [$Level] $Message"
    # When emitting JSON events for the GUI, skip Write-Host to avoid duplicate lines.
    if ($EmitEvents) {
        Write-Event -Type "log" -Fields @{ level = $Level; message = $Message }
    } else {
        Write-Host $entry
    }
    Add-Content -LiteralPath $LOG_FILE -Value $entry -Encoding UTF8
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Pause-Exit {
    param([int]$Code = 1)
    if ($NonInteractive) { exit $Code }
    Write-Host "`nPress any key to close this window..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit $Code
}

function Get-StepIndex {
    param([string]$Id)
    $i = [array]::IndexOf($STEP_ORDER, $Id)
    if ($i -lt 0) { return 0 }
    return ($i + 1)
}

function Test-ShouldRunStep {
    param([string]$Id)
    if ($OnlyStep) { return ($OnlyStep -eq $Id) }
    if ($FromStep) {
        $fromIdx = [array]::IndexOf($STEP_ORDER, $FromStep)
        $curIdx = [array]::IndexOf($STEP_ORDER, $Id)
        if ($fromIdx -lt 0) { return $true }
        return ($curIdx -ge $fromIdx)
    }
    return $true
}

function Invoke-NamedStep {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][scriptblock]$Block
    )
    if (-not (Test-ShouldRunStep -Id $Id)) {
        Write-Log "Skipping step '$Id' (FromStep/OnlyStep filter)" -Level "INFO"
        return
    }
    $idx = Get-StepIndex -Id $Id
    $pct = [int]([math]::Floor((($idx - 1) / [double]$script:StepTotal) * 100))
    Write-Event -Type "step_start" -Fields @{
        id = $Id; index = $idx; total = $script:StepTotal; title = $Title
    }
    Write-Event -Type "progress" -Fields @{ percent = $pct; id = $Id }
    Write-Log ">> $Title ($Id)" -Level "INFO"
    try {
        & $Block
        Write-Event -Type "step_end" -Fields @{ id = $Id; ok = $true }
        $pctDone = [int]([math]::Floor(($idx / [double]$script:StepTotal) * 100))
        Write-Event -Type "progress" -Fields @{ percent = $pctDone; id = $Id }
    } catch {
        $msg = $_.Exception.Message
        Write-Log "FAILED at step '$Title' ($Id): $msg" -Level "ERROR"
        Write-Event -Type "step_end" -Fields @{ id = $Id; ok = $false; message = $msg }
        Write-Event -Type "error" -Fields @{ id = $Id; message = $msg }
        Pause-Exit -Code 1
    }
}

function Find-Python314 {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")

    $candidates = @()
    $py = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($py) { $candidates += ,@("py.exe", "-3.15") }
    $candidates += ,@("python3.15.exe", $null)
    $candidates += ,@("python.exe", $null)

    foreach ($spec in $candidates) {
        try {
            $exeName = $spec[0]
            if ($spec[1]) {
                $ver = & $exeName $spec[1] -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            } else {
                $ver = & $exeName -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            }
            if ($LASTEXITCODE -eq 0 -and $ver -and $ver.Trim() -eq $PY_MAJOR_MINOR) {
                if ($spec[1]) {
                    $exe = & $exeName $spec[1] -c "import sys; print(sys.executable)" 2>$null
                } else {
                    $exe = & $exeName -c "import sys; print(sys.executable)" 2>$null
                }
                if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
            }
        } catch { }
    }
    $known = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python$($PY_MAJOR_MINOR.Replace('.',''))\python.exe"),
        "C:\Program Files\Python$($PY_MAJOR_MINOR.Replace('.',''))\python.exe",
        "C:\Python$($PY_MAJOR_MINOR.Replace('.',''))\python.exe"
    )
    foreach ($p in $known) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}

function Install-Python {
    Write-Log "Installing Python $PY_MAJOR_MINOR via winget..." -Level "INFO"
    if (-not $Elevated) {
        Write-Log "Elevation required for winget Python install." -Level "WARN"
        return $null
    }
    try {
        & winget install --id $WINGET_PY_ID --exact --silent --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Log "winget install failed (exit $LASTEXITCODE). Falling back to python.org installer." -Level "WARN"
        }
    } catch {
        Write-Log "winget error: $($_.Exception.Message). Falling back to python.org installer." -Level "WARN"
    }

    $py = Find-Python314
    if ($py) { return $py }

    Write-Log "Downloading Python installer from python.org..." -Level "INFO"
    $installerPath = Join-Path $env:TEMP $PY_INSTALLER
    try {
        Invoke-WebRequest -Uri $PY_INSTALLER_URL -OutFile $installerPath -UseBasicParsing
    } catch {
        Write-Log "Failed to download Python installer: $($_.Exception.Message)" -Level "ERROR"
        return $null
    }

    $installArgs = "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1 Include_test=0 Include_doc=0 Include_debug=0"
    Write-Log "Running silent Python installer..." -Level "INFO"
    try {
        Start-Process -FilePath $installerPath -ArgumentList $installArgs -Wait -PassThru | Out-Null
    } catch {
        Write-Log "Failed to start Python installer: $($_.Exception.Message)" -Level "ERROR"
        return $null
    }

    $py = Find-Python314
    if (-not $py) {
        Write-Log "Python $PY_MAJOR_MINOR could not be verified after install." -Level "ERROR"
        return $null
    }
    return $py
}

function Ask-YesNo {
    param([string]$Prompt, [bool]$DefaultYes = $true)
    if ($NonInteractive) { return $DefaultYes }
    Write-Host $Prompt -ForegroundColor Yellow
    $answer = Read-Host
    if ($DefaultYes) {
        return -not ($answer -eq "n" -or $answer -eq "N")
    }
    return ($answer -eq "y" -or $answer -eq "Y")
}

# --- Welcome ------------------------------------------------------------------
Write-Host ""
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "  Spock-Universal-AI-Wiki  -  First-Time Setup (hybrid)" -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "Log file: $LOG_FILE" -ForegroundColor Gray
Write-Host ""

# --- Elevation if Python missing ----------------------------------------------
$script:pythonExe = Find-Python314
if (-not $script:pythonExe) {
    if (-not $Elevated) {
        Write-Event -Type "need_elevation" -Fields @{
            reason = "Python $PY_MAJOR_MINOR install requires administrator permission"
        }
        Write-Host ""
        Write-Host "Python $PY_MAJOR_MINOR was not found on this computer." -ForegroundColor Yellow
        Write-Host "Installing it requires administrator permission (UAC)." -ForegroundColor Yellow
        Write-Host ""
        if (-not $NonInteractive) {
            Write-Host "Press any key to continue (a UAC prompt will appear)..." -ForegroundColor Yellow
            $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        }
        $relaunchArgs = @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", "`"$PSCommandPath`"", "-Elevated"
        )
        if ($NonInteractive) { $relaunchArgs += "-NonInteractive" }
        if ($EmitEvents) { $relaunchArgs += "-EmitEvents" }
        if ($InstallRoot) { $relaunchArgs += @("-InstallRoot", "`"$InstallRoot`"") }
        if ($HandOffGui) { $relaunchArgs += "-HandOffGui" }
        if ($NoHandOffGui) { $relaunchArgs += "-NoHandOffGui" }
        try {
            Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $relaunchArgs
        } catch {
            Write-Log "Elevation was cancelled: $($_.Exception.Message)" -Level "ERROR"
            Pause-Exit -Code 1
        }
        exit 0
    }
    if (-not (Test-Admin)) {
        Write-Log "Elevated mode requested but not running as admin." -Level "ERROR"
        Pause-Exit -Code 1
    }
}

# --- Steps --------------------------------------------------------------------
Invoke-NamedStep -Id "python" -Title "Python $PY_MAJOR_MINOR" -Block {
    if (-not $script:pythonExe) {
        $script:pythonExe = Install-Python
        if (-not $script:pythonExe) {
            throw "Python $PY_MAJOR_MINOR is required and could not be installed."
        }
    }
    Write-Log "Python $PY_MAJOR_MINOR found: $script:pythonExe" -Level "INFO"
}

Invoke-NamedStep -Id "install_root" -Title "Resolve install root" -Block {
    $script:appHere = Test-Path -LiteralPath (Join-Path $SCRIPT_DIR "SpockOnboardingWizard.py")
    if ($InstallRoot -and $InstallRoot.Trim()) {
        $script:installRoot = $InstallRoot.Trim().TrimEnd('\', '/')
        Write-Log "Install root (param): $script:installRoot" -Level "INFO"
        return
    }
    if ($env:SPOCK_INSTALL_ROOT -and $env:SPOCK_INSTALL_ROOT.Trim()) {
        $script:installRoot = $env:SPOCK_INSTALL_ROOT.Trim().TrimEnd('\', '/')
        Write-Log "Install root (env SPOCK_INSTALL_ROOT): $script:installRoot" -Level "INFO"
        return
    }
    if ($script:appHere) {
        # Full tree already beside bootstrap — install in place.
        $script:installRoot = $SCRIPT_DIR
        Write-Log "App detected beside bootstrap script: $script:installRoot" -Level "INFO"
        return
    }

    # Staging folder (Setup-Spock.bat + bootstrap.ps1 only): always use THIS folder.
    # Do NOT use Read-Host here — when launched via double-click .bat, Read-Host often
    # never returns on Enter (console stdin quirk). Override with -InstallRoot or
    # env SPOCK_INSTALL_ROOT if you need a different destination.
    $script:installRoot = $SCRIPT_DIR
    Write-Host ""
    Write-Host "Installing into the Setup-Spock.bat folder:" -ForegroundColor White
    Write-Host "  $script:installRoot" -ForegroundColor Green
    Write-Host "(Override: powershell -File bootstrap.ps1 -InstallRoot D:\OtherPath)" -ForegroundColor Gray
    Write-Host ""
    Write-Log "Install root (Setup folder, no prompt): $script:installRoot" -Level "INFO"
}

Invoke-NamedStep -Id "acquire" -Title "Acquire app source" -Block {
    if ($SkipAcquire -or $script:appHere) {
        Write-Log "Acquire skipped (app already present or -SkipAcquire)." -Level "INFO"
        return
    }
    $extractRoot = Join-Path $env:TEMP "$GITHUB_REPO-extract"
    if (Test-Path -LiteralPath $extractRoot) {
        Remove-Item -LiteralPath $extractRoot -Recurse -Force
    }
    $innerDir = Join-Path $extractRoot $GITHUB_REPO
    $gitExe = Get-Command "git.exe" -ErrorAction SilentlyContinue
    if ($gitExe) {
        Write-Log "Cloning $GITHUB_OWNER/$GITHUB_REPO (branch $GITHUB_BRANCH) ..." -Level "INFO"
        & git clone --depth 1 --single-branch --branch $GITHUB_BRANCH `
            "https://github.com/$GITHUB_OWNER/$GITHUB_REPO.git" $innerDir
        if ($LASTEXITCODE -ne 0) { throw "git clone failed (exit $LASTEXITCODE)" }
    } else {
        $zipPath = Join-Path $env:TEMP "$GITHUB_REPO.zip"
        Write-Log "git not found; downloading $REPO_ZIP_URL ..." -Level "INFO"
        try {
            Invoke-WebRequest -Uri $REPO_ZIP_URL -OutFile $zipPath -UseBasicParsing
        } catch {
            throw "Could not download the app. Install git from https://git-scm.com if the repo is private: $($_.Exception.Message)"
        }
        Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force
        $innerDir = Join-Path $extractRoot $REPO_EXTRACT
        if (-not (Test-Path -LiteralPath $innerDir)) {
            $kids = Get-ChildItem -LiteralPath $extractRoot -Directory -ErrorAction SilentlyContinue
            if ($kids.Count -eq 1) { $innerDir = $kids[0].FullName }
            if (-not (Test-Path -LiteralPath $innerDir)) {
                throw "Unexpected zip layout: expected $innerDir"
            }
        }
    }
    New-Item -ItemType Directory -Force -Path $script:installRoot | Out-Null
    Copy-Item -Path (Join-Path $innerDir "*") -Destination $script:installRoot -Recurse -Force
    Write-Log "App copied to $script:installRoot" -Level "INFO"
}

Invoke-NamedStep -Id "folders" -Title "Creating folder tree" -Block {
    foreach ($dir in $FOLDER_TREE) {
        $full = Join-Path $script:installRoot $dir
        if (-not (Test-Path -LiteralPath $full)) {
            New-Item -ItemType Directory -Force -Path $full | Out-Null
        }
    }
    foreach ($file in @(".env", "AGENTS.md", "index.md", "captains_log.md", "lint_report.md")) {
        $fp = Join-Path $script:installRoot $file
        if (-not (Test-Path -LiteralPath $fp)) {
            New-Item -ItemType File -Force -Path $fp | Out-Null
        }
    }
    Write-Log "Folder tree ready under $script:installRoot" -Level "INFO"
}

Invoke-NamedStep -Id "database" -Title "Empty database check" -Block {
    function New-SqliteFromSchema {
        param([string]$DbPath, [string]$SchemaPath, [string]$Label)
        if (-not (Test-Path -LiteralPath $SchemaPath)) {
            Write-Log "No schema for ${Label}: $SchemaPath" -Level "WARN"
            return
        }
        if (Test-Path -LiteralPath $DbPath) {
            Write-Log "${Label} already exists: $DbPath" -Level "INFO"
            return
        }
        Write-Log "Creating empty ${Label} from schema..." -Level "INFO"
        & $script:pythonExe -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.executescript(open(sys.argv[2], encoding='utf-8').read()); c.commit(); c.close()" $DbPath $SchemaPath
        if ($LASTEXITCODE -ne 0) { throw "Failed to create $Label" }
        Write-Log "${Label} created: $DbPath" -Level "INFO"
    }

    New-SqliteFromSchema `
        -DbPath (Join-Path $script:installRoot "ship_computer.db") `
        -SchemaPath (Join-Path $script:installRoot "ship_computer_schema.sql") `
        -Label "ship_computer.db"

    New-SqliteFromSchema `
        -DbPath (Join-Path $script:installRoot "uieg_capture.db") `
        -SchemaPath (Join-Path $script:installRoot "uieg_capture.sql") `
        -Label "uieg_capture.db"
}

Invoke-NamedStep -Id "venv" -Title "Creating Python virtual environment" -Block {
    $venvDir = Join-Path $script:installRoot ".venv"
    if (-not (Test-Path -LiteralPath (Join-Path $venvDir "Scripts\python.exe"))) {
        Write-Log "Running: $($script:pythonExe) -m venv $venvDir" -Level "INFO"
        & $script:pythonExe -m venv $venvDir
        if ($LASTEXITCODE -ne 0) { throw "venv creation failed (exit $LASTEXITCODE)" }
    }
    $script:venvPython = Join-Path $venvDir "Scripts\python.exe"
    Write-Log "venv python: $script:venvPython" -Level "INFO"
}

Invoke-NamedStep -Id "pip_wizard" -Title "Installing onboarding / bootstrap wizard dependencies" -Block {
    & $script:venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
    & $script:venvPython -m pip install --find-links (Join-Path $script:installRoot "wheels") @WIZARD_DEPS
    if ($LASTEXITCODE -ne 0) { throw "wizard deps install failed" }
    & $script:venvPython -c "import PyQt6, requests, psutil, huggingface_hub; print('wizard deps OK')"
    if ($LASTEXITCODE -ne 0) { throw "wizard deps import check failed" }
}

$controlWizard = Join-Path $script:installRoot "SpockBootstrapWizard.py"
if (-not $script:venvPython) {
    $maybeVenv = Join-Path $script:installRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $maybeVenv) { $script:venvPython = $maybeVenv }
}
$doHandOff = $false
if (-not $NoHandOffGui) {
    if ($HandOffGui -or (Test-Path -LiteralPath $controlWizard)) {
        $doHandOff = $true
    } else {
        Write-Log "SpockBootstrapWizard.py not found at $controlWizard." -Level "WARN"
        Write-Log "Phase B control UI requires branch cursor/nav-station-suite-ux (commit with SpockBootstrapWizard.py). Falling back to Onboarding Wizard." -Level "WARN"
        Write-Host ""
        Write-Host "NOTE: Bootstrap Control Wizard missing - you likely cloned an older commit." -ForegroundColor Yellow
        Write-Host "  git fetch origin && git checkout cursor/nav-station-suite-ux && git pull" -ForegroundColor Cyan
        Write-Host "Then re-run Setup-Spock.bat (or: python SpockBootstrapWizard.py)" -ForegroundColor Cyan
        Write-Host ""
    }
}
if ($OnlyStep -and $OnlyStep -ne "handoff_gui") { $doHandOff = $false }

if ($doHandOff -and (Test-ShouldRunStep -Id "handoff_gui")) {
    Invoke-NamedStep -Id "handoff_gui" -Title "Hand off to Bootstrap Control Wizard" -Block {
        if (-not (Test-Path -LiteralPath $controlWizard)) {
            throw "SpockBootstrapWizard.py not found at $controlWizard"
        }
        Write-Log "Launching Bootstrap Control Wizard (Phase B)..." -Level "INFO"
        Write-Event -Type "done" -Fields @{
            ok = $true
            phase = "A"
            handoff = $true
            installRoot = $script:installRoot
            venvPython = $script:venvPython
        }
        $argList = @(
            "`"$controlWizard`"",
            "--install-root", "`"$($script:installRoot)`""
        )
        Start-Process -FilePath $script:venvPython -ArgumentList $argList -WorkingDirectory $script:installRoot
        Write-Log "Phase A complete - GUI control wizard started. Console can close." -Level "INFO"
    }
    if (-not $NonInteractive) {
        Write-Host ""
        Write-Host "Bootstrap Control Wizard launched. You can close this console." -ForegroundColor Green
        Write-Host "Log file: $LOG_FILE" -ForegroundColor Gray
        Write-Host "Press any key to close..." -ForegroundColor Yellow
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    }
    exit 0
}

$onboardScript = Join-Path $script:installRoot "SpockOnboardingWizard.py"
if (-not $SkipWizard -and (Test-ShouldRunStep -Id "onboarding")) {
    if (-not (Test-Path -LiteralPath $onboardScript)) {
        Write-Log "Onboarding wizard not found: $onboardScript" -Level "ERROR"
        Pause-Exit -Code 1
    }
    Invoke-NamedStep -Id "onboarding" -Title "Running onboarding wizard" -Block {
        Push-Location $script:installRoot
        try {
            & $script:venvPython $onboardScript
            if ($LASTEXITCODE -ne 0) {
                Write-Log "Wizard exited with code $LASTEXITCODE" -Level "WARN"
            }
        } finally {
            Pop-Location
        }
    }
}

$runHeavy = $false
if (-not $SkipHeavyDeps -and (Test-ShouldRunStep -Id "pip_full")) {
    if ($NonInteractive) {
        $runHeavy = [bool]$HeavyDeps
    } else {
        $runHeavy = Ask-YesNo "Install full requirements.txt now (torch etc., can take a long time)? [Y/n]" $true
    }
}
if ($runHeavy) {
    Invoke-NamedStep -Id "pip_full" -Title "Installing full requirements.txt" -Block {
        if (-not $script:venvPython -or -not (Test-Path -LiteralPath $script:venvPython)) {
            $script:venvPython = Join-Path $script:installRoot ".venv\Scripts\python.exe"
        }
        if (-not (Test-Path -LiteralPath $script:venvPython)) {
            throw "venv python not found at $($script:venvPython). Run Phase A (venv / pip_wizard) first."
        }
        $reqs = Join-Path $script:installRoot "requirements.txt"
        if (Test-Path -LiteralPath $reqs) {
            Write-Log "Running: $($script:venvPython) -m pip install -r $reqs" -Level "INFO"
            & $script:venvPython -m pip install --find-links (Join-Path $script:installRoot "wheels") -r $reqs
            if ($LASTEXITCODE -ne 0) { throw "requirements.txt install failed (exit $LASTEXITCODE)" }
        } else {
            Write-Log "requirements.txt not found; skipping." -Level "WARN"
        }
    }
} elseif (-not $SkipHeavyDeps) {
    Write-Log "Full dependencies skipped." -Level "INFO"
}

$runValidate = $false
if (-not $SkipValidate -and (Test-ShouldRunStep -Id "validate")) {
    if ($NonInteractive) {
        $runValidate = [bool]$Validate
    } else {
        $runValidate = Ask-YesNo "Run Spock health/status check now? [Y/n]" $true
    }
}
if ($runValidate) {
    Invoke-NamedStep -Id "validate" -Title "Validating Spock health" -Block {
        $healthMod = Join-Path $script:installRoot "spock_health_report.py"
        $healthOut = Join-Path $script:installRoot "bootstrap_health_last.txt"
        if (-not (Test-Path -LiteralPath $healthMod)) {
            Write-Log "spock_health_report.py not found; skipping validate." -Level "WARN"
            return
        }
        if (-not $script:venvPython -or -not (Test-Path -LiteralPath $script:venvPython)) {
            $script:venvPython = Join-Path $script:installRoot ".venv\Scripts\python.exe"
        }
        $probePy = Join-Path $env:TEMP "spock_bootstrap_health_probe.py"
        $probeCode = @(
            'import os, sys'
            'from pathlib import Path'
            'root = Path(os.environ["SPOCK_INSTALL_ROOT"]).resolve()'
            'sys.path.insert(0, str(root))'
            'os.chdir(root)'
            'from spock_health_report import format_spock_health_report, probe_spock_health'
            'data = probe_spock_health('
            '    api_base="http://127.0.0.1:8090",'
            '    db_path=str(root / "ship_computer.db"),'
            '    embeddings_url="http://localhost:8080/embeddings",'
            ')'
            'text = format_spock_health_report(data)'
            'print(text)'
            'out = root / "bootstrap_health_last.txt"'
            'out.write_text(text, encoding="utf-8")'
            'sys.exit(0)'
        ) -join "`n"
        # Avoid UTF-8 BOM (Windows PS 5.1 Set-Content -Encoding UTF8 adds BOM; breaks python).
        [System.IO.File]::WriteAllText($probePy, $probeCode)
        $env:SPOCK_INSTALL_ROOT = $script:installRoot
        $prevEap = $ErrorActionPreference
        try {
            Push-Location $script:installRoot
            try {
                # Native stderr must not become a terminating error under Stop.
                $ErrorActionPreference = "Continue"
                $output = & $script:venvPython $probePy 2>&1 | ForEach-Object { "$_" } | Out-String
                if ($output) {
                    foreach ($line in ($output -split "`r?`n")) {
                        if ($line.Trim()) { Write-Log $line.Trim() -Level "INFO" }
                    }
                }
                if ($LASTEXITCODE -ne 0) {
                    Write-Log "Health probe exited with code $LASTEXITCODE (report may be partial)." -Level "WARN"
                } elseif (Test-Path -LiteralPath $healthOut) {
                    Write-Log "Health report saved to $healthOut" -Level "INFO"
                }
            } finally {
                $ErrorActionPreference = $prevEap
                Pop-Location
            }
        } finally {
            Remove-Item Env:SPOCK_INSTALL_ROOT -ErrorAction SilentlyContinue
        }
    }
} elseif (-not $SkipValidate) {
    Write-Log "Status validation skipped." -Level "INFO"
}

Write-Event -Type "done" -Fields @{
    ok = $true
    phase = "console"
    installRoot = $script:installRoot
    venvPython = $script:venvPython
}
Write-Host ""
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "  Setup complete! Install root:" -ForegroundColor Green
Write-Host "    $script:installRoot" -ForegroundColor Cyan
Write-Host "  Log file: $LOG_FILE" -ForegroundColor Gray
Write-Host "================================================================================" -ForegroundColor Cyan
if (-not $NonInteractive) {
    Write-Host "Press any key to close this window..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}
