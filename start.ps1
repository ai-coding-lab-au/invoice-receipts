$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $root "_datadir.ps1")
$env:DATA_DIR = Resolve-DataDir $root

$venvPython = Join-Path $root "backend\.venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

Write-Host "Invoice & Receipts: http://127.0.0.1:8790"
Write-Host "Data directory: $env:DATA_DIR"
Write-Host "Press Ctrl+C to stop."

Set-Location (Join-Path $root "backend")
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8790
if ($LASTEXITCODE -ne 0) { throw "Invoice & Receipts exited with code $LASTEXITCODE" }
