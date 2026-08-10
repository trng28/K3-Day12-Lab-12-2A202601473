[CmdletBinding()]
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

function Invoke-Python {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [switch]$Quiet
    )

    # Windows PowerShell can promote a native program's stderr to a terminating
    # NativeCommandError when ErrorActionPreference is Stop. Native commands
    # communicate success through their exit code, so capture that explicitly.
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($Quiet) {
            & $Python @Arguments *> $null
        }
        else {
            # Out-Host displays native stdout without adding it to this
            # function's return pipeline. The caller receives only the exit code.
            & $Python @Arguments | Out-Host
        }
        $NativeExitCode = $LASTEXITCODE
        return $NativeExitCode
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtual environment not found. Create it first: py -m venv `"$ProjectRoot\.venv`""
}

Push-Location $ProjectRoot
try {
    if (-not $SkipInstall) {
        $PytestCheck = Invoke-Python -Arguments @("-c", "import pytest") -Quiet
        if ($PytestCheck -ne 0) {
            Write-Host "Installing pytest into .venv..."
            $InstallExitCode = Invoke-Python -Arguments @("-m", "pip", "install", "pytest")
            if ($InstallExitCode -ne 0) {
                throw "Failed to install pytest."
            }
        }
    }
    else {
        $PytestCheck = Invoke-Python -Arguments @("-c", "import pytest") -Quiet
        if ($PytestCheck -ne 0) {
            throw "pytest is not installed. Run without -SkipInstall or install it with: .\.venv\Scripts\python.exe -m pip install pytest"
        }
    }

    Write-Host "Running research workflow tests..."
    $TestExitCode = Invoke-Python -Arguments @(
        "-m",
        "pytest",
        "tests\test_research_workflow.py",
        "tests\test_research_chat.py",
        "tests\test_semantic_scholar.py",
        "tests\test_arxiv_tool.py",
        "tests\test_api.py",
        "-q"
    )
    if ($TestExitCode -ne 0) {
        throw "Research workflow tests failed."
    }

    Write-Host "Checking Python syntax..."
    $CompileExitCode = Invoke-Python -Arguments @(
        "-m",
        "compileall",
        "-q",
        "research_workflow.py",
        "research_chat.py",
        "api.py",
        "tools\papers\tool.py",
        "tools\semantic_scholar\tool.py"
    )
    if ($CompileExitCode -ne 0) {
        throw "Python compilation check failed."
    }

    Write-Host "All research workflow checks passed."
}
finally {
    Pop-Location
}
