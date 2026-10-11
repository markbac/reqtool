#Requires -Version 5.1
<#
.SYNOPSIS
    Set up a local virtual environment and run reqtool without installing it system-wide.

.DESCRIPTION
    Idempotent -- safe to run multiple times. Creates a .venv in the repository
    root, installs the package in editable mode with test extras, then executes
    the requested command.

.PARAMETER Command
    The command to run. One of:
        serve       Start the API server (default)
        test        Run the test suite (optionally specify a Subset)
        validate    Run req validate on the current repo
        verify      Run req verify on the current repo
        req         Run any req subcommand (pass remaining args after --)
        shell       Drop into a shell with the venv active
        help        Show this help

.PARAMETER Subset
    For the test command. One of: core | features | api | all (default: all)

.PARAMETER ReqArgs
    Additional arguments forwarded to req when using the req command.

.EXAMPLE
    .\scripts\dev.ps1
    .\scripts\dev.ps1 serve
    .\scripts\dev.ps1 test core
    .\scripts\dev.ps1 test features
    .\scripts\dev.ps1 req init agile --repo C:\my-reqs
    .\scripts\dev.ps1 req validate --repo C:\my-reqs

.NOTES
    Environment variables:
        REQTOOL_REPO    Requirements repository root (default: current directory)
        REQTOOL_PORT    Server port (default: 8765)
        REQTOOL_HOST    Server host (default: 127.0.0.1)
        PYTHON          Python interpreter (default: python)
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('install', 'serve', 'test', 'validate', 'verify', 'req', 'shell', 'help', '')]
    [string]$Command = 'serve',

    [Parameter(Position = 1)]
    # Only `test` uses this; with `req` it is the first word of the req command (checked below, not here).
    [string]$Subset = 'all',

    [Parameter(ValueFromRemainingArguments)]
    [string[]]$ReqArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$SubsetGiven = $PSBoundParameters.ContainsKey('Subset')

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$RepoDir   = Split-Path -Parent $ScriptDir
if (-not $RepoDir -or -not (Test-Path $RepoDir)) {
    Write-Red "ERROR: Could not determine repository root from script location '$ScriptDir'."
    Write-Yellow "Run the script as: .\\scripts\\dev.ps1 install"
    exit 1
}
$VenvDir   = Join-Path $RepoDir '.venv'
# Windows PowerShell 5.1 has no $IsWindows; PowerShell 7 on Linux or macOS puts the tools in bin/, not Scripts/.
$OnWindows = [IO.Path]::DirectorySeparatorChar -eq '\'
$VenvBin   = Join-Path $VenvDir $(if ($OnWindows) { 'Scripts' } else { 'bin' })
$ExeSuffix = if ($OnWindows) { '.exe' } else { '' }

$PythonExe  = if ($env:PYTHON)       { $env:PYTHON }       else { 'python' }
$ReqtoolRepo = if ($env:REQTOOL_REPO) { $env:REQTOOL_REPO } else { $null }
$Port        = if ($env:REQTOOL_PORT) { $env:REQTOOL_PORT } else { '8765' }
$Host_       = if ($env:REQTOOL_HOST) { $env:REQTOOL_HOST } else { '127.0.0.1' }

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
function Write-Green  { param([string]$Msg) Write-Host $Msg -ForegroundColor Green }
function Write-Yellow { param([string]$Msg) Write-Host $Msg -ForegroundColor Yellow }
function Write-Red    { param([string]$Msg) Write-Host $Msg -ForegroundColor Red }
function Write-Bold   { param([string]$Msg) Write-Host $Msg -ForegroundColor White }

# ---------------------------------------------------------------------------
# Verify Python version
# ---------------------------------------------------------------------------
function Assert-Python {
    try {
        $null = Get-Command $PythonExe -ErrorAction Stop
    }
    catch {
        Write-Red "ERROR: '$PythonExe' not found. Install Python 3.11+ or set `$env:PYTHON."
        exit 1
    }

    $versionStr = & $PythonExe -c "import sys; print('%d.%d' % sys.version_info[:2])"
    $parts  = $versionStr.Split('.')
    $major  = [int]$parts[0]
    $minor  = [int]$parts[1]

    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
        Write-Red "ERROR: Python 3.11+ required (found $versionStr)."
        exit 1
    }
    Write-Green "Python $versionStr OK"
}

# ---------------------------------------------------------------------------
# Create / update venv
# ---------------------------------------------------------------------------
function Initialize-Venv {
    Assert-Python

    if (-not (Test-Path $VenvDir)) {
        Write-Yellow "Creating virtual environment at $VenvDir ..."
        & $PythonExe -m venv $VenvDir
    }

    $VenvPython = Join-Path $VenvBin "python$ExeSuffix"
    $VenvPip    = Join-Path $VenvBin "pip$ExeSuffix"

    Write-Yellow "Upgrading pip ..."
    & $VenvPython -m pip install --quiet --upgrade pip

    Write-Yellow "Installing reqtool (editable) ..."
    & $VenvPip install --quiet -e "$RepoDir[test]"

    # Check the other tools reqtool uses (git, Node.js) and install Vale if it is missing. Never fatal.
    & $VenvPython -m reqtool.cli tools --quiet
    if ($LASTEXITCODE -ne 0) { Write-Yellow "A required tool is missing (see above). Run: req tools" }

    Write-Green "Environment ready."
    return $VenvDir
}

# ---------------------------------------------------------------------------
# Resolve the req executable inside the venv
# ---------------------------------------------------------------------------
function Get-ReqExe {
    $exe = Join-Path $VenvBin "req$ExeSuffix"
    if (-not (Test-Path $exe)) {
        # Fallback -- invoke as module
        $exe = $null
    }
    return $exe
}

function Invoke-Req {
    param([string[]]$Args_)
    $VenvPython = Join-Path $VenvBin "python$ExeSuffix"
    $reqExe = Get-ReqExe
    if ($reqExe) {
        & $reqExe @Args_
    }
    else {
        & $VenvPython -m reqtool.cli @Args_
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Invoke-Pytest {
    param([string[]]$Args_)
    $VenvPython = Join-Path $VenvBin "python$ExeSuffix"
    & $VenvPython -m pytest @Args_
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
function Invoke-Install {
    Assert-Python

    Write-Host "  Repository root: $RepoDir" -ForegroundColor DarkGray
    Write-Host "  UI directory:    $(Join-Path $RepoDir 'src\reqtool\ui')" -ForegroundColor DarkGray
    Write-Host ""

    Write-Bold "Step 1/3 -- Setting up Python virtual environment ..."
    Initialize-Venv | Out-Null

    Write-Bold "Step 2/3 -- Building React UI ..."
    $uiDir = Join-Path $RepoDir 'src\reqtool\ui'
    Write-Host "  UI dir: $uiDir" -ForegroundColor DarkGray

    if (-not (Test-Path $uiDir)) {
        Write-Red "ERROR: UI directory not found: $uiDir"
        Write-Yellow "Ensure the repository was extracted correctly."
        exit 1
    }

    $skipBuild = $false
    try { $null = Get-Command npm -ErrorAction Stop }
    catch {
        Write-Yellow "npm not found -- skipping UI build. Install Node.js 18+ to build the UI."
        $skipBuild = $true
    }

    if (-not $skipBuild) {
        # Windows: find npm.cmd explicitly -- Start-Process cannot run .ps1 shims. Elsewhere `npm` itself works.
        # (No `?.` here: it needs PowerShell 7.1 and this script supports 5.1.)
        $npmCmd = $null
        if ($OnWindows) {
            foreach ($name in @('npm.cmd', 'npm.exe')) {
                $found = Get-Command $name -ErrorAction SilentlyContinue
                if ($found) { $npmCmd = $found.Source; break }
            }
            if (-not $npmCmd) {
                $candidates = @(
                    "$env:ProgramFiles\nodejs\npm.cmd",
                    "${env:ProgramFiles(x86)}\nodejs\npm.cmd",
                    "$env:APPDATA\npm\npm.cmd",
                    "$env:LOCALAPPDATA\Programs\nodejs\npm.cmd"
                )
                foreach ($c in $candidates) {
                    if (Test-Path $c) { $npmCmd = $c; break }
                }
            }
        } else {
            $found = Get-Command 'npm' -ErrorAction SilentlyContinue
            if ($found) { $npmCmd = $found.Source }
        }

        if (-not $npmCmd) {
            Write-Red "Cannot find npm. Install Node.js 18+ from https://nodejs.org/"
            Write-Yellow "After installing Node.js, close and reopen this shell, then re-run."
            exit 1
        }

        Write-Host "  npm: $npmCmd" -ForegroundColor DarkGray

        function Invoke-Npm {
            param([string[]]$NpmArgs)
            if ($OnWindows) {
                $p = Start-Process -FilePath 'cmd.exe' -ArgumentList "/c `\"$npmCmd`\" $($NpmArgs -join ' ')" `
                                   -WorkingDirectory $uiDir -Wait -PassThru -NoNewWindow
                return $p.ExitCode
            }
            Push-Location $uiDir
            try { & $npmCmd @NpmArgs; return $LASTEXITCODE } finally { Pop-Location }
        }

        Write-Yellow "Installing UI dependencies ..."
        $code = Invoke-Npm @('install', '--legacy-peer-deps')
        if ($code -ne 0) {
            Write-Red "npm install failed (exit $code)."
            Write-Yellow "Node.js version: $(& node --version 2>$null)"
            exit $code
        }

        Write-Yellow "Building UI ..."
        $code = Invoke-Npm @('run', 'build')
        if ($code -ne 0) {
            Write-Red "npm run build failed (exit $code)."
            exit $code
        }
        Write-Green "UI built: $uiDir\dist"
    }

    Write-Bold "Step 3/3 -- Re-installing package (picks up new dist) ..."
    $VenvPip = Join-Path $VenvBin "pip$ExeSuffix"
    & $VenvPip install --quiet -e "$RepoDir[test]"

    Write-Green ""
    Write-Green "Done. Run: .\scripts\dev.ps1 serve"
}

function Invoke-Serve {
    Initialize-Venv | Out-Null
    Write-Bold "Starting reqtool at http://$Host_`:$Port"
    Write-Host "Repository: $(if ($ReqtoolRepo) { $ReqtoolRepo } else { (Get-Location).Path })"
    Write-Host "Press Ctrl+C to stop."
    Write-Host ""

    $reqArgs_ = @('serve', '--host', $Host_, '--port', $Port)
    if ($ReqtoolRepo) { $reqArgs_ += @('--repo', $ReqtoolRepo) }
    Invoke-Req $reqArgs_
}

function Invoke-Test {
    param([string]$Sub = 'all')
    Initialize-Venv | Out-Null
    Push-Location $RepoDir

    switch ($Sub) {
        'core' {
            Write-Bold "Running core tests (unit and acceptance tiers) ..."
            Invoke-Pytest @('tests/unit', 'tests/acceptance', '--timeout=30', '-v', '--tb=short')
        }
        'features' {
            Write-Bold "Running integration tests (without the API and regression files) ..."
            Invoke-Pytest @(
                'tests/integration', '--ignore=tests/integration/test_api.py',
                '--ignore=tests/integration/test_regression.py', '--timeout=30', '-v', '--tb=short'
            )
        }
        'api' {
            Write-Bold "Running API + regression tests ..."
            Invoke-Pytest @(
                'tests/integration/test_api.py', 'tests/integration/test_regression.py',
                '--timeout=60', '-v', '--tb=short'
            )
        }
        default {
            Write-Bold "Running full test suite ..."
            Invoke-Pytest @('tests', '--ignore=tests/e2e', '--timeout=60', '-v', '--tb=short')
        }
    }

    Pop-Location
}

function Invoke-Validate {
    Initialize-Venv | Out-Null
    $repo = if ($ReqtoolRepo) { $ReqtoolRepo } else { (Get-Location).Path }
    Write-Bold "Running req validate on $repo ..."
    Invoke-Req @('validate', '--repo', $repo)
}

function Invoke-Verify {
    Initialize-Venv | Out-Null
    $repo = if ($ReqtoolRepo) { $ReqtoolRepo } else { (Get-Location).Path }
    Write-Bold "Running req verify on $repo ..."
    Invoke-Req @('verify', '--repo', $repo)
}

function Invoke-ReqCmd {
    Initialize-Venv | Out-Null
    # `dev.ps1 req init agile` binds "init" to -Subset, so put it back in front of the other words.
    $words = @()
    if ($SubsetGiven) { $words += $Subset }
    if ($ReqArgs) { $words += $ReqArgs }
    Invoke-Req $words
}

function Invoke-Shell {
    Initialize-Venv | Out-Null
    $activate = Join-Path $VenvBin 'Activate.ps1'
    Write-Green "Activating virtual environment. Run 'deactivate' to exit."
    & $activate
}

function Show-Help {
    Write-Host @"
reqtool dev script

Usage: .\scripts\dev.ps1 [Command] [Subset] [ReqArgs...]

Commands:
  install           Build UI + install everything (run this first)
  serve             Start the API server (default)
  test [subset]     Run tests. Subsets: core | features | api | all (default: all)
  validate          Run req validate on the current repo
  verify            Run req verify on the current repo
  req [args...]     Run any req subcommand
  shell             Activate the venv in the current shell
  help              Show this help

Environment variables:
  REQTOOL_REPO      Requirements repository root (default: current directory)
  REQTOOL_PORT      Server port (default: 8765)
  REQTOOL_HOST      Server host (default: 127.0.0.1)
  PYTHON            Python interpreter (default: python)

Examples:
  .\scripts\dev.ps1
  .\scripts\dev.ps1 serve
  .\scripts\dev.ps1 test core
  .\scripts\dev.ps1 test features
  .\scripts\dev.ps1 req init agile --repo C:\my-reqs
  `$env:REQTOOL_REPO = 'C:\my-reqs'; .\scripts\dev.ps1 serve
  `$env:REQTOOL_PORT = '9000';       .\scripts\dev.ps1 serve
"@
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
switch ($Command) {
    'install'  { Invoke-Install }
    'serve'    { Invoke-Serve }
    'test'     {
        if ($Subset -notin @('core', 'features', 'api', 'all', '')) {
            Write-Red "Unknown test subset: $Subset (use core, features, api or all)"
            exit 1
        }
        Invoke-Test $Subset
    }
    'validate' { Invoke-Validate }
    'verify'   { Invoke-Verify }
    'req'      { Invoke-ReqCmd }
    'shell'    { Invoke-Shell }
    'help'     { Show-Help }
    ''         { Invoke-Serve }
    default    {
        Write-Red "Unknown command: $Command"
        Write-Host ""
        Show-Help
        exit 1
    }
}
