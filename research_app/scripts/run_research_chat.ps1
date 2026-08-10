[CmdletBinding()]
param(
    [string]$Question,
    [string]$Output
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtual environment not found. Create it first: py -m venv `"$ProjectRoot\.venv`""
}

$Arguments = @("research_chat.py")
if ($Question) {
    $Arguments += @("--question", $Question)
}
if ($Output) {
    $Arguments += @("--output", $Output)
}

Push-Location $ProjectRoot
try {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Research chatbot exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
