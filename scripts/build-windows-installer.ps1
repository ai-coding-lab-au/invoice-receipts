param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [string]$SourceDirectory,
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

if ($Version -notmatch "^[0-9A-Za-z][0-9A-Za-z._-]*$") {
    throw "Version may contain only letters, numbers, dots, underscores and hyphens."
}

if (-not $SourceDirectory) {
    $SourceDirectory = Join-Path $projectRoot "dist\InvoiceReceipts"
}
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $projectRoot "installer-output"
}

$sourcePath = [System.IO.Path]::GetFullPath($SourceDirectory)
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
$application = Join-Path $sourcePath "InvoiceReceipts.exe"
if (-not (Test-Path -LiteralPath $application -PathType Leaf)) {
    throw "The packaged application was not found: $application"
}

$compilerCandidates = @(
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
)
$compiler = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $compiler) {
    $command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($command) {
        $compiler = $command.Source
    }
}
if (-not $compiler) {
    throw "Inno Setup 6 was not found. Install it from https://jrsoftware.org/isdl.php"
}

New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$installerName = "InvoiceReceipts-$Version-Setup"
$scriptPath = Join-Path $projectRoot "installer\InvoiceReceipts.iss"
$arguments = @(
    "/DMyAppVersion=$Version",
    "/DMySourceDir=$sourcePath",
    "/O$outputPath",
    "/F$installerName",
    $scriptPath
)

& $compiler @arguments | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE."
}

$installerPath = Join-Path $outputPath "$installerName.exe"
if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf)) {
    throw "The installer compiler completed without producing $installerPath"
}
if ((Get-Item -LiteralPath $installerPath).Length -le 1MB) {
    throw "The generated installer is unexpectedly small: $installerPath"
}

Write-Output $installerPath
