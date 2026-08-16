param(
    [string]$Destination = (Join-Path (Split-Path -Parent $PSScriptRoot) "open-source-staging")
)

$ErrorActionPreference = "Stop"
$sourceRoot = Split-Path -Parent $PSScriptRoot
$destinationPath = [System.IO.Path]::GetFullPath($Destination)
$sourcePath = [System.IO.Path]::GetFullPath($sourceRoot)

if ($destinationPath -eq $sourcePath) {
    throw "The staging destination cannot be the source directory."
}
if (Test-Path -LiteralPath $destinationPath) {
    throw "The staging destination already exists: $destinationPath"
}

$rootFiles = @(
    ".env.example",
    ".gitattributes",
    ".gitignore",
    "build-desktop.cmd",
    "build.ps1",
    "build.sh",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "COPYRIGHT",
    "install-desktop.cmd",
    "install.ps1",
    "install.sh",
    "LICENSE",
    "README.md",
    "run-desktop.cmd",
    "SECURITY.md",
    "start.ps1",
    "start.sh",
    "THIRD_PARTY_NOTICES.md",
    "_datadir.ps1",
    "_datadir.sh"
)
$sourceDirectories = @(".github", "backend", "docs", "frontend", "installer", "scripts")
$excludedDirectories = @(
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules"
)

New-Item -ItemType Directory -Path $destinationPath | Out-Null

foreach ($file in $rootFiles) {
    $source = Join-Path $sourcePath $file
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required source file is missing: $file"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $destinationPath $file)
}

foreach ($directory in $sourceDirectories) {
    $sourceDirectory = Join-Path $sourcePath $directory
    if (-not (Test-Path -LiteralPath $sourceDirectory -PathType Container)) {
        throw "Required source directory is missing: $directory"
    }
    Get-ChildItem -LiteralPath $sourceDirectory -Recurse -File -Force | ForEach-Object {
        $relative = $_.FullName.Substring($sourcePath.Length).TrimStart([char]92, [char]47)
        $parts = $relative -split "[\\/]"
        $skip = $false
        foreach ($part in $parts[0..([Math]::Max(0, $parts.Length - 2))]) {
            if ($excludedDirectories -contains $part -or $part -like "build-*" -or $part -like "release-*") {
                $skip = $true
                break
            }
        }
        if (
            $skip -or
            $_.Name -like "*.pyc" -or
            $_.Name -like "*.running.lock" -or
            $_.Name -like "*.tsbuildinfo"
        ) {
            return
        }
        $target = Join-Path $destinationPath $relative
        $targetDirectory = Split-Path -Parent $target
        if (-not (Test-Path -LiteralPath $targetDirectory)) {
            New-Item -ItemType Directory -Path $targetDirectory | Out-Null
        }
        Copy-Item -LiteralPath $_.FullName -Destination $target
    }
}

Write-Host "Clean source staging tree created at $destinationPath"
Write-Host "Run: python scripts/check_repository_hygiene.py `"$destinationPath`""
