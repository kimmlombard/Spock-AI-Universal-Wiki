@echo off
REM Console Spock Onboarding Menu (power users / recovery).
REM Prefer Spock-Menu.bat for the PyQt6 bringup UI.
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0spock_menu.ps1" %*

if errorlevel 1 (
  echo.
  echo Spock console menu exited with an error.
  echo.
  pause
)
