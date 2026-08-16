$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $root "backend\.venv"

python -m venv $venv
if ($LASTEXITCODE -ne 0) { throw "Unable to create the Python environment" }
$python = Join-Path $venv "Scripts\python.exe"
$requirements = Join-Path $root "backend\requirements-runtime.txt"
$wheelhouse = Join-Path $root "vendor\wheels"
if (Test-Path -LiteralPath $wheelhouse) {
    & $python -m pip install --no-index --find-links $wheelhouse -r $requirements
} else {
    & $python -m pip install -r $requirements
}
if ($LASTEXITCODE -ne 0) { throw "Unable to install dependencies" }

Write-Host "Installed. Run .\start.ps1 and open http://127.0.0.1:8790"
