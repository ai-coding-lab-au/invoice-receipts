@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%backend\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Python environment not found. Run install-desktop.cmd first.
    exit /b 1
)

"%PYTHON%" -c "import webview" >nul 2>&1
if errorlevel 1 (
    echo Desktop dependencies not found. Run install-desktop.cmd first.
    exit /b 1
)

pushd "%ROOT%backend"
"%PYTHON%" desktop.py
set "RESULT=%ERRORLEVEL%"
popd
exit /b %RESULT%
