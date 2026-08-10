[CmdletBinding()]
param(
    [switch]$Build
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    $Arguments = @("compose", "up", "-d")
    if ($Build) {
        $Arguments += "--build"
    }
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed with exit code $LASTEXITCODE."
    }
    Write-Host ""
    Write-Host "Research Agent UI: http://localhost:8080"
    Write-Host "Backend API docs: http://localhost:8000/docs"
}
finally {
    Pop-Location
}
