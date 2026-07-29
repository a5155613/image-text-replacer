@echo off
setlocal

cd /d "%~dp0"

set "PY_EXE=%~dp0venv\Scripts\python.exe"

if not exist "%PY_EXE%" (
    echo [WARN] venv not found, fallback to system python
    set "PY_EXE=python"
)

echo Starting GUI...
echo.

"%PY_EXE%" "%~dp0main.py"

if errorlevel 1 (
    echo.
    echo [Exit code: %errorlevel%]
    pause
)

endlocal