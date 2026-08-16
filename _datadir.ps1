# Resolve DATA_DIR the same way for every entry point:
#   an existing DATA_DIR environment variable > a DATA_DIR line in .env >
#   the portable default ./.data
# Dot-source this from each script; never re-implement the precedence.
function Resolve-DataDir([string]$Root) {
    if ($env:DATA_DIR) { return $env:DATA_DIR }
    $envFile = Join-Path $Root ".env"
    if (Test-Path -LiteralPath $envFile) {
        $match = Select-String -LiteralPath $envFile -Pattern '^\s*DATA_DIR\s*=' | Select-Object -Last 1
        if ($match) {
            $value = ($match.Line -replace '^\s*DATA_DIR\s*=\s*', '').Trim().Trim('"').Trim("'")
            if ($value) { return $value }
        }
    }
    return (Join-Path $Root ".data")
}
