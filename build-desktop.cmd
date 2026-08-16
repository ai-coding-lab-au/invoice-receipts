@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%backend\.venv\Scripts\python.exe"

call "%ROOT%install-desktop.cmd"
if errorlevel 1 exit /b 1

pushd "%ROOT%frontend"
call npm.cmd install
if errorlevel 1 (
    popd
    exit /b 1
)
call npm.cmd run build
if errorlevel 1 (
    popd
    exit /b 1
)
popd

pushd "%ROOT%"
"%PYTHON%" -m PyInstaller --noconfirm --clean "backend\desktop.spec"
set "RESULT=%ERRORLEVEL%"
popd
if not "%RESULT%"=="0" exit /b %RESULT%

echo Desktop app built in dist\InvoiceReceipts
