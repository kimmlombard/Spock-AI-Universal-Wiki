@echo off
REM Launch Spock UIEG KnowledgeBase without requiring PowerShell ExecutionPolicy changes.
REM Prefer this over:  .\spock_UIEG-KnowledgeBase.ps1
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0spock_UIEG_KnowledgeBase.py" %*
  goto :done
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 "%~dp0spock_UIEG_KnowledgeBase.py" %*
  goto :done
)

python "%~dp0spock_UIEG_KnowledgeBase.py" %*

:done
if errorlevel 1 (
  echo.
  echo Spock UIEG KnowledgeBase exited with an error.
  echo If PowerShell blocked .\spock_UIEG-KnowledgeBase.ps1, use this .bat instead, or run:
  echo   powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0spock_UIEG-KnowledgeBase.ps1"
  echo Or permanently for your user:
  echo   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  echo.
  pause
)
