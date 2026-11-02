@echo off
REM Spock AI Helper launcher.
REM Tries .venv python, then py -3, then python on PATH.
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0helper_main.py" %*
  goto :done
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 "%~dp0helper_main.py" %*
  goto :done
)

python "%~dp0helper_main.py" %*

:done
if errorlevel 1 (
  echo.
  echo Spock AI Helper exited with an error.
  echo Make sure Python 3.12+ and PyQt6 are installed.
  echo If using a virtual environment, ensure .venv exists in %~dp0
  echo.
  pause
)
