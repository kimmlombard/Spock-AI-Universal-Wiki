@echo off
REM Spock Bringup Menu (PyQt6). Avoids PowerShell ExecutionPolicy blocks.
REM If PyQt6 is missing, runs Phase A (bootstrap) then opens the GUI.
cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "BOOTSTRAP=%~dp0bootstrap.ps1"

if not exist "%VENV_PY%" goto :need_phase_a

"%VENV_PY%" -c "import PyQt6" >nul 2>&1
if errorlevel 1 goto :need_phase_a

:launch_gui
echo Opening Spock Bringup Menu...
set PYTHONPATH=%~dp0
"%VENV_PY%" -m spock_bringup_menu %*
if errorlevel 1 (
  echo.
  echo Bringup Menu exited with an error.
  pause
)
goto :eof

:need_phase_a
echo PyQt6 / venv not ready — running Phase A (bootstrap)...
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BOOTSTRAP%" -NonInteractive -EmitEvents -NoHandOffGui -InstallRoot "%~dp0"
if errorlevel 1 (
  echo.
  echo Phase A failed. Fix errors above, then run Spock-Menu.bat again.
  echo Or use Spock-Menu-Console.bat for the text menu.
  pause
  exit /b 1
)

if not exist "%VENV_PY%" (
  echo Phase A finished but .venv python is still missing.
  pause
  exit /b 1
)

"%VENV_PY%" -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
  echo Phase A finished but PyQt6 still not importable.
  pause
  exit /b 1
)

goto :launch_gui
