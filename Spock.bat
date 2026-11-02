@echo off
REM Lite Spock-UIE-Wiki-KB orchestrator (Navigation / UIEG / Maintenance).
REM Prefer this over:  .\spock.ps1
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0main.py" %*
  goto :done
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 "%~dp0main.py" %*
  goto :done
)

python "%~dp0main.py" %*

:done
if errorlevel 1 (
  echo.
  echo Spock exited with an error.
  echo If PowerShell blocked .\spock.ps1, use this .bat, or:
  echo   powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0spock.ps1"
  echo.
  pause
)
