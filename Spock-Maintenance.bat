@echo off
REM Launch Spock Engineering Maintenance without requiring PowerShell ExecutionPolicy changes.
REM Prefer this over:  .\spock_maintenance.ps1
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0spock_maintenance.py" %*
  goto :done
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 "%~dp0spock_maintenance.py" %*
  goto :done
)

python "%~dp0spock_maintenance.py" %*

:done
if errorlevel 1 (
  echo.
  echo Spock Engineering Maintenance exited with an error.
  echo If PowerShell blocked .\spock_maintenance.ps1, use this .bat instead, or run:
  echo   powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0spock_maintenance.ps1"
  echo Or permanently for your user:
  echo   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  echo.
  pause
)
