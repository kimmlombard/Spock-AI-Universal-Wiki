# bootstrap.ps1 — Spock-Onboarding Phase A (Python + venv + PyQt6 deps)
#
# Events (-EmitEvents): one JSON object per stdout line
#   step_start | log | step_end | progress | done | error

param(
    [switch]$NonInteractive,
    [switch]$EmitEvents,
    [string]$InstallRoot = "",
    [Alias("SkipHeavyDeps")][switch]$SkipFullDeps,
    [Alias("HeavyDeps")][switch]$FullDeps,
    [switch]$SkipValidate,
    [switch]$Validate,
    [switch]$NoHandOffGui,
    [string]$FromStep = "",
    [string]$OnlyStep = ""
)

$ErrorActionPreference = "Stop"

$PY_MAJOR_MINOR = "3.12"
$WINGET_PY_ID = "Python.Python.3.12"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$LOG_FILE = Join-Path $SCRIPT_DIR "bootstrap.log"

# Fallback for the UI tier when requirements-ui.txt is missing (partial clone).
$WIZARD_DEPS = @("PyQt6", "requests", "psutil", "huggingface_hub")

# Shared pip flags: no interactive prompts, no version-check round trip, and
# never build from source when a wheel exists.
$PIP_FLAGS = @("--disable-pip-version-check", "--prefer-binary", "--no-input")

$STEP_ORDER = @(
    "python", "install_root", "folders", "venv", "pip_wizard", "pip_full", "validate"
)
$script:StepTotal = $STEP_ORDER.Count
$script:pythonExe = $null
$script:venvPython = $null
$script:installRoot = $null

if ($InstallRoot -and $InstallRoot.Trim()) {
    $script:installRoot = $InstallRoot.Trim().TrimEnd('\', '/')
} elseif ($env:SPOCK_INSTALL_ROOT -and $env:SPOCK_INSTALL_ROOT.Trim()) {
    $script:installRoot = $env:SPOCK_INSTALL_ROOT.Trim().TrimEnd('\', '/')
} else {
    $script:installRoot = $SCRIPT_DIR
}

function Write-Event {
    param([Parameter(Mandatory = $true)][string]$Type, [hashtable]$Fields = @{})
    if (-not $EmitEvents) { return }
    $obj = @{ event = $Type; ts = (Get-Date -Format "o") }
    foreach ($k in $Fields.Keys) { $obj[$k] = $Fields[$k] }
    Write-Output ($obj | ConvertTo-Json -Compress)
}

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Add-Content -LiteralPath $LOG_FILE -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($EmitEvents) {
        Write-Event -Type "log" -Fields @{ level = $Level; message = $Message }
    } else {
        Write-Host $line
    }
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
        Write-Log "Skipping step '$Id' (FromStep/OnlyStep filter)"
        return
    }
    $i = [array]::IndexOf($STEP_ORDER, $Id)
    $pct = [int]((($i) / [math]::Max(1, $script:StepTotal)) * 100)
    Write-Event -Type "step_start" -Fields @{ id = $Id; index = $i; total = $script:StepTotal; title = $Title }
    Write-Event -Type "progress" -Fields @{ percent = $pct; id = $Id }
    Write-Log ">>> $Title"
    try {
        & $Block
        Write-Event -Type "step_end" -Fields @{ id = $Id; ok = $true }
        Write-Event -Type "progress" -Fields @{ percent = [int]((($i + 1) / $script:StepTotal) * 100); id = $Id }
    } catch {
        $msg = "$_"
        Write-Log $msg -Level "ERROR"
        Write-Event -Type "step_end" -Fields @{ id = $Id; ok = $false; message = $msg }
        Write-Event -Type "error" -Fields @{ id = $Id; message = $msg }
        throw
    }
}

function Update-PipIfStale {
    # A pip self-upgrade costs a network round trip on every Phase A re-run;
    # only pay it when the venv's pip is older than the floor we rely on.
    $minPip = [version]"24.0"
    try {
        $raw = & $script:venvPython -m pip --version 2>$null
        if ("$raw" -match 'pip\s+(\d+\.\d+(\.\d+)?)') {
            if ([version]$Matches[1] -ge $minPip) {
                Write-Log "pip $($Matches[1]) is current; skipping self-upgrade"
                return
            }
            Write-Log "pip $($Matches[1]) is older than $minPip; upgrading"
        }
    } catch { }
    & $script:venvPython -m pip install --disable-pip-version-check --no-input --upgrade pip
}

function Get-VenvLockHolders {
    # Other python.exe processes whose path is this venv — they hold DLLs/.pyi
    # open and cause WinError 32 when pip tries to replace packages.
    param([string]$VenvPython)
    $holders = @()
    if (-not $VenvPython) { return $holders }
    $norm = [IO.Path]::GetFullPath($VenvPython).ToLowerInvariant()
    try {
        Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
            ForEach-Object {
                $exe = [string]$_.ExecutablePath
                if (-not $exe) { return }
                try {
                    $full = [IO.Path]::GetFullPath($exe).ToLowerInvariant()
                } catch { return }
                if ($full -eq $norm -and [int]$_.ProcessId -ne $PID) {
                    $holders += [pscustomobject]@{
                        Pid     = [int]$_.ProcessId
                        Command = [string]$_.CommandLine
                    }
                }
            }
    } catch { }
    return $holders
}

function Write-VenvLockWarning {
    param([string]$VenvPython)
    $holders = @(Get-VenvLockHolders -VenvPython $VenvPython)
    if ($holders.Count -eq 0) { return }
    Write-Log (
        "WARNING: $($holders.Count) other process(es) are using this venv " +
        "and may lock files during pip install (WinError 32). " +
        "Close other Spock windows if install fails, then re-run Phase B."
    ) -Level "WARN"
    foreach ($h in $holders) {
        $cmd = $h.Command
        if ($cmd -and $cmd.Length -gt 160) { $cmd = $cmd.Substring(0, 160) + "..." }
        Write-Log ("  PID {0}: {1}" -f $h.Pid, $cmd) -Level "WARN"
    }
}

function Invoke-PipInstall {
    # Windows Defender / Explorer / a live GUI often lock a just-written file for
    # a few seconds (WinError 32). Retry instead of failing the whole Phase B.
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string[]]$PipArgs,
        [int]$Attempts = 4,
        [int]$DelaySec = 5
    )
    if (-not $script:venvPython) {
        throw "venv python is not set before pip install ($Label)"
    }
    $lastCode = 1
    for ($n = 1; $n -le $Attempts; $n++) {
        Write-Log "pip install ($Label) attempt $n/$Attempts"
        & $script:venvPython -m pip install @PIP_FLAGS --find-links (Join-Path $script:installRoot "wheels") @PipArgs
        $lastCode = $LASTEXITCODE
        if ($lastCode -eq 0) { return }
        if ($n -lt $Attempts) {
            Write-Log (
                "pip install ($Label) failed (exit $lastCode). " +
                "If this is WinError 32, a file in site-packages is locked " +
                "(Bringup menu, antivirus, or Explorer). Retrying in ${DelaySec}s..."
            ) -Level "WARN"
            Start-Sleep -Seconds $DelaySec
            $DelaySec = [Math]::Min(30, $DelaySec * 2)
        }
    }
    Write-VenvLockWarning -VenvPython $script:venvPython
    throw (
        "pip install of $Label failed (exit $lastCode) after $Attempts attempts. " +
        "Close other Spock / Python windows using this .venv, then re-run Phase B."
    )
}

function Find-Python314 {
    $local = $env:LOCALAPPDATA
    $candidates = @(
        # python.org / Store-style installs (common on Windows 10/11)
        "$local\Python\pythoncore-3.12-64\python.exe",
        "$local\Python\pythoncore-3.12-32\python.exe",
        "$local\Python\bin\python.exe",
        "$local\Programs\Python\Python314\python.exe",
        "$local\Programs\Python\Python3.12\python.exe",
        "C:\Python314\python.exe"
    )
    # Glob any pythoncore-3.12* tree under Local\Python
    $coreGlob = Join-Path $local "Python\pythoncore-3.12*\python.exe"
    try {
        Get-Item -Path $coreGlob -ErrorAction SilentlyContinue | ForEach-Object {
            $candidates = @($_.FullName) + $candidates
        }
    } catch { }

    $pyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try {
            $path = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
            if ($path -and (Test-Path -LiteralPath $path.Trim())) {
                return $path.Trim()
            }
        } catch { }
    }
    $pythonCmd = Get-Command "python" -ErrorAction SilentlyContinue
    if ($pythonCmd -and $pythonCmd.Source -and (Test-Path -LiteralPath $pythonCmd.Source)) {
        # Prefer real installs over WindowsApps stubs
        if ($pythonCmd.Source -notmatch '\\WindowsApps\\') {
            $candidates = @($pythonCmd.Source) + $candidates
        }
    }
    foreach ($c in $candidates) {
        if (-not $c -or -not (Test-Path -LiteralPath $c)) { continue }
        try {
            $ver = & $c -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if (("$ver").Trim() -eq $PY_MAJOR_MINOR) { return $c }
        } catch { }
    }
    return $null
}

Invoke-NamedStep -Id "python" -Title "Locate or install Python $PY_MAJOR_MINOR" -Block {
    # If onboarding .venv already exists, reuse it (Phase A re-runs from GUI/menu).
    $existingVenv = Join-Path $script:installRoot ".venv\Scripts\python.exe"
    if ($script:installRoot -and (Test-Path -LiteralPath $existingVenv)) {
        try {
            $ver = & $existingVenv -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if (("$ver").Trim()) {
                $script:venvPython = $existingVenv
                $script:pythonExe = $existingVenv
                Write-Log "Using existing venv Python: $existingVenv ($ver)"
                return
            }
        } catch { }
    }

    $found = Find-Python314
    if ($found) {
        $script:pythonExe = $found
        Write-Log "Python: $found"
        return
    }
    Write-Log "Python $PY_MAJOR_MINOR not found; attempting winget..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        & winget install -e --id $WINGET_PY_ID --accept-package-agreements --accept-source-agreements
        $found = Find-Python314
        if ($found) {
            $script:pythonExe = $found
            Write-Log "Python after winget: $found"
            return
        }
    }
    throw "Python $PY_MAJOR_MINOR is required. Install from https://www.python.org/downloads/ and re-run."
}

Invoke-NamedStep -Id "install_root" -Title "Confirm install root" -Block {
    if (-not (Test-Path -LiteralPath $script:installRoot)) {
        New-Item -ItemType Directory -Path $script:installRoot | Out-Null
    }
    Write-Log "Install root: $($script:installRoot)"
    $env:SPOCK_INSTALL_ROOT = $script:installRoot
}

Invoke-NamedStep -Id "folders" -Title "Create onboarding folders" -Block {
    foreach ($d in @("models", "tools", "tools\llama-server", "tools\llmfit", "logs", "data")) {
        $p = Join-Path $script:installRoot $d
        if (-not (Test-Path -LiteralPath $p)) {
            New-Item -ItemType Directory -Path $p | Out-Null
        }
    }
    Write-Log "Folder tree ready"
}

Invoke-NamedStep -Id "venv" -Title "Create .venv" -Block {
    $venvDir = Join-Path $script:installRoot ".venv"
    $venvPy = Join-Path $venvDir "Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPy) {
        # An existing venv can go stale when its base interpreter is moved or
        # uninstalled (e.g. a Python 3.14 -> 3.12 migration). Running it then
        # fails with "did not find executable at ..." and exit 103. Verify the
        # venv actually works; if not, rebuild it from the base we located.
        $healthy = $false
        try {
            $probe = & $venvPy -c "print('ok')" 2>$null
            if ($LASTEXITCODE -eq 0 -and ("$probe").Trim() -eq "ok") { $healthy = $true }
        } catch { }
        if (-not $healthy) {
            Write-Log "Existing .venv is broken (stale base interpreter); recreating with $($script:pythonExe)" -Level "WARN"
            Remove-Item -LiteralPath $venvDir -Recurse -Force
        }
    }
    if (-not (Test-Path -LiteralPath $venvPy)) {
        & $script:pythonExe -m venv $venvDir
    }
    if (-not (Test-Path -LiteralPath $venvPy)) {
        throw "venv python missing at $venvPy"
    }
    $script:venvPython = $venvPy
    Write-Log "venv: $venvPy"
}

Invoke-NamedStep -Id "pip_wizard" -Title "Install UI tier (PyQt6 menu deps)" -Block {
    if (-not $script:venvPython) {
        $script:venvPython = Join-Path $script:installRoot ".venv\Scripts\python.exe"
    }
    Update-PipIfStale
    $reqUi = Join-Path $script:installRoot "requirements-ui.txt"
    if (Test-Path -LiteralPath $reqUi) {
        Invoke-PipInstall -Label "UI tier" -PipArgs @("-r", $reqUi)
    } else {
        Write-Log "requirements-ui.txt missing; falling back to inline wizard deps"
        Invoke-PipInstall -Label "UI tier (inline)" -PipArgs $WIZARD_DEPS
    }
    & $script:venvPython -c "import PyQt6, requests, psutil, huggingface_hub; print('wizard deps ok')"
}

Invoke-NamedStep -Id "pip_full" -Title "Install full tier (ingest / extractors / WebEngine)" -Block {
    if (-not $FullDeps -or $SkipFullDeps) {
        Write-Log "Skipping full tier (run Bringup step 2 / Phase B to install it)"
        return
    }
    if (-not $script:venvPython) {
        $script:venvPython = Join-Path $script:installRoot ".venv\Scripts\python.exe"
    }
    $reqFull = Join-Path $script:installRoot "requirements-full.txt"
    if (-not (Test-Path -LiteralPath $reqFull)) {
        throw "requirements-full.txt missing at $reqFull"
    }
    # Phase B is usually started from the Bringup menu, which already holds this
    # venv open. Do not reinstall UI packages here — only add the full tier.
    Write-VenvLockWarning -VenvPython $script:venvPython
    Invoke-PipInstall -Label "full tier" -PipArgs @("-r", $reqFull)
    # Import (not just pip metadata): PyQt6 6.12 + WebEngine 6.11 installs cleanly
    # then fails at runtime with "DLL load failed ... QtWebEngineWidgets".
    & $script:venvPython -c "from PyQt6.QtWebEngineWidgets import QWebEngineView; print('full tier: WebEngine OK')"
    if ($LASTEXITCODE -ne 0) {
        throw "PyQt6-WebEngine import failed after full-tier install (often a PyQt6 vs WebEngine version skew, or Spock windows locking Qt DLLs). Close suite apps, then re-run Phase B."
    }
    Write-Log "Full tier installed"
}

if (-not $SkipValidate) {
    Invoke-NamedStep -Id "validate" -Title "Validate Phase A" -Block {
        if (-not $script:venvPython) {
            $script:venvPython = Join-Path $script:installRoot ".venv\Scripts\python.exe"
        }
        & $script:venvPython -c "import PyQt6; print('ui_ready gate: PyQt6 OK')"
        Write-Log "Phase A validation passed"
    }
}

Write-Event -Type "done" -Fields @{
    ok          = $true
    phase       = "A"
    installRoot = $script:installRoot
    venvPython  = $script:venvPython
}
Write-Log "Phase A complete. Next: Spock-Menu.bat -> Acquire / Bring up servers."
exit 0
