@echo off
setlocal
set "ROOT=%~dp0"
set "VENV=%ROOT%backend\.venv"
set "PYTHON=%VENV%\Scripts\python.exe"

if not exist "%PYTHON%" (
    python -m venv "%VENV%"
    if errorlevel 1 exit /b 1
)

"%PYTHON%" -m pip install -r "%ROOT%backend\requirements-desktop.txt"
if errorlevel 1 exit /b 1

echo Desktop dependencies installed.
