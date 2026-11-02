@echo off
REM Lite Spock-Universal-AI-Wiki orchestrator (Navigation / UIEG / Maintenance).
REM Prefer this over:  .\spock.ps1 - for first launch
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0SpockBootstrapWizard.ps1"

:done
if errorlevel 1 (
  echo.
  echo Spock exited with an error.
  echo If PowerShell blocked .\spock.ps1, use this .bat, or:
  echo   powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0SpockBootstrapWizard.ps1"
  echo.
  pause
)
