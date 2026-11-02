@echo off
REM Spock first-time setup: Phase A (console) then hand off to Bootstrap Control Wizard.
REM cd so relative paths work; keep the window open on failure.
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1"
if errorlevel 1 (
  echo.
  echo Setup exited with an error. See bootstrap.log in this folder.
  pause
)
