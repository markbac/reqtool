<#
.SYNOPSIS
    Bring a reqtool install up to date and check that it works: the code, the Python packages, the req
    command, the tools it uses and the web UI.

.DESCRIPTION
    Run it after every pull, or whenever reqtool misbehaves after a change. Each step says what it does,
    and the script stops at the first step that fails, with what to do about it.

      1. Code         git pull --ff-only (skipped with -NoPull, or when this is not a Git checkout). When
                      the pull changes this script, the new version runs instead, with the same options
      2. Python       the project's own virtual environment, .venv in this folder (the one run.ps1 and
                      dev.ps1 use), made from a Python 3.11 or later when it is missing or broken
                      (-System or -Python: another Python instead)
      3. Packages     pip install -e . into it (with the test tools when -Dev), then pip check
      4. Command      req runs, and the req on the PATH is this one: its folder is put first on your user
                      PATH when it is not already (-NoPath leaves the PATH alone)
      5. Tools        req tools: git must be there; Vale is installed if it is missing
      6. Web UI       npm ci and npm run build when the UI's sources are newer than its build, or it has
                      none (-RebuildUi: always; -NoUi: skip). Needs Node.js 18 or later
      7. Container    with -Docker: the server image is built again, and the server restarted on it when
                      it is running (docker-compose.yml, see scripts/docker.ps1)
      8. Tests        with -Test: the Python test suite and the UI tests

.PARAMETER NoPull
    Do not pull: use the code as it is.

.PARAMETER Dev
    Also install the test tools (pip install -e ".[test]"). -Test implies it.

.PARAMETER RebuildUi
    Build the web UI even when its build is up to date.

.PARAMETER NoUi
    Do not build the web UI. Without a build, req serve shows a page saying how to build it.

.PARAMETER Docker
    Also build the server's container image again, and restart the server when it is running.

.PARAMETER Test
    Also run the Python test suite and the UI tests.

.PARAMETER Python
    Install into this Python instead of .venv, such as C:\venvs\reqtool\Scripts\python.exe.

.PARAMETER System
    Install into the Python on the PATH (python, else py -3) instead of .venv. Its other packages can then
    conflict with reqtool's, which pip check reports.

.PARAMETER RecreateVenv
    Delete .venv and make it again, such as after a Python upgrade.

.PARAMETER NoPath
    Leave your user PATH alone. By default the folder of this reqtool is put first on it, when it is not
    already, so req in a new terminal is this one.

.EXAMPLE
    .\scripts\update.ps1
.EXAMPLE
    .\scripts\update.ps1 -Dev -Test
.EXAMPLE
    .\scripts\update.ps1 -Docker
.EXAMPLE
    .\scripts\update.ps1 -NoPull -RebuildUi -RecreateVenv
#>
[CmdletBinding()]
param(
    [switch]$NoPull,
    [switch]$Dev,
    [switch]$RebuildUi,
    [switch]$NoUi,
    [switch]$Docker,
    [switch]$Test,
    [string]$Python,
    [switch]$System,
    [switch]$RecreateVenv,
    [switch]$NoPath
)

Set-StrictMode -Version Latest
# Programs report failure through their exit status, which every step checks. 'Stop' would also turn any
# line a program writes to stderr into an error in Windows PowerShell 5.1, so it is not used.
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
$UiDir = Join-Path $Root 'src/reqtool/ui'
$IsWindowsHost = [IO.Path]::DirectorySeparatorChar -eq '\'
# PowerShell reads a script once, when it starts: a pull that changes this file needs the new copy started.
$script:SelfHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $PSCommandPath).Hash
$script:Step = 0
$script:Started = Get-Date

function Write-Step([string]$Text) {
    $script:Step++
    Write-Host ""
    Write-Host "[$script:Step] $Text" -ForegroundColor Cyan
}

function Write-Ok([string]$Text) { Write-Host "    ok    $Text" -ForegroundColor Green }
function Write-Note([string]$Text) { Write-Host "    note  $Text" -ForegroundColor Yellow }

function Stop-Update([string]$Text, [string]$Advice) {
    Write-Host "    FAIL  $Text" -ForegroundColor Red
    if ($Advice) { Write-Host "          $Advice" -ForegroundColor Red }
    exit 1
}

# Runs a program, shows its output, and stops the update when it fails.
function Invoke-Checked([string]$What, [string]$Advice, [string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { Stop-Update "$What failed (exit status $LASTEXITCODE)" $Advice }
}

# Runs req through the chosen Python, so it is always this install that runs.
function Invoke-Req([string[]]$Arguments) {
    & $script:PythonExe @script:PythonArgs -m reqtool.cli @Arguments
}

# Runs npm in the UI folder and stops the update when it fails.
function Invoke-Npm([string]$What, [string[]]$Arguments) {
    Push-Location $UiDir
    try { Invoke-Checked $What "Read npm's message above; a proxy may need npm config set proxy or cafile" npm $Arguments }
    finally { Pop-Location }
}

# The newest change to any file the UI is built from.
function Get-UiSourceTime {
    $files = @(Get-ChildItem -LiteralPath (Join-Path $UiDir 'src') -Recurse -File)
    $files += @('index.html', 'package.json', 'package-lock.json', 'vite.config.js' |
                ForEach-Object { Get-Item -LiteralPath (Join-Path $UiDir $_) -ErrorAction SilentlyContinue })
    # Sort-Object, not Measure-Object -Maximum: Windows PowerShell 5.1 measures numbers only.
    ($files | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1).LastWriteTimeUtc
}

Push-Location $Root
try {
    Write-Host "reqtool update in $Root"

    # 1. Code ------------------------------------------------------------------------------------
    Write-Step "Code"
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($NoPull) {
        Write-Note "not pulled (-NoPull)"
    } elseif (-not $git -or -not (Test-Path (Join-Path $Root '.git'))) {
        Write-Note "not a Git checkout, so nothing to pull"
    } else {
        $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
        $dirty = & git status --porcelain --untracked-files=no
        if ($dirty) { Write-Note "local changes to tracked files are kept; a pull that would touch them stops here" }
        if ($branch -ne 'main') { Write-Note "on branch $branch, not main" }
        Invoke-Checked "git pull" "Pull or merge by hand (the pull only fast-forwards), or run with -NoPull" git @('pull', '--ff-only')
        Write-Ok "$branch at $((& git log -1 --format='%h %s').Trim())"
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $PSCommandPath).Hash -ne $script:SelfHash) {
            Write-Note "the pull changed this script, so the new version runs now, with the same options"
            $again = @{}
            foreach ($key in $PSBoundParameters.Keys) { $again[$key] = $PSBoundParameters[$key] }
            $again['NoPull'] = $true
            & $PSCommandPath @again
            exit $LASTEXITCODE
        }
    }

    # 2. Python ----------------------------------------------------------------------------------
    Write-Step "Python"
    $script:PythonArgs = @()
    $venv = Join-Path $Root '.venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path $venvPython)) { $venvPython = Join-Path $venv 'bin/python' }  # PowerShell on Linux or macOS

    # A Python 3.11 or later on the PATH: the base of the virtual environment, or the target with -System
    function Find-BasePython {
        foreach ($candidate in @(@('python'), @('py', '-3'), @('python3'))) {
            if (-not (Get-Command $candidate[0] -ErrorAction SilentlyContinue)) { continue }
            $extra = @($candidate | Select-Object -Skip 1)
            $ok = & $candidate[0] @extra -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return , $candidate }
        }
        Stop-Update "no Python 3.11 or later found" "Install Python 3.11 or later from python.org, or name one with -Python"
    }

    if ($Python) {
        $script:PythonExe = $Python
        $where = "the Python -Python names"
    } elseif ($System) {
        $base = Find-BasePython
        $script:PythonExe = $base[0]
        $script:PythonArgs = @($base | Select-Object -Skip 1)
        $where = "the Python on the PATH (-System)"
    } else {
        $healthy = $false
        if ((Test-Path $venvPython) -and -not $RecreateVenv) {
            & $venvPython -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
            $healthy = ($LASTEXITCODE -eq 0)
            if (-not $healthy) { Write-Note ".venv is broken or too old (was its Python removed or upgraded?), so it is made again" }
        }
        if (-not $healthy) {
            if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }
            $base = Find-BasePython
            $baseArgs = @($base | Select-Object -Skip 1)
            Write-Host "    making .venv with $($base -join ' ')"
            Invoke-Checked "making the virtual environment" "Check that this Python can make one (python -m venv)" $base[0] ($baseArgs + @('-m', 'venv', $venv))
            $venvPython = Join-Path $venv 'Scripts\python.exe'
            if (-not (Test-Path $venvPython)) { $venvPython = Join-Path $venv 'bin/python' }
        }
        $script:PythonExe = $venvPython
        $where = "reqtool's own virtual environment, .venv"
    }
    $version = & $script:PythonExe @script:PythonArgs -c "import sys; print('%d.%d.%d' % sys.version_info[:3]); print(sys.executable)"
    if ($LASTEXITCODE -ne 0 -or -not $version) { Stop-Update "$script:PythonExe does not run" "Run again with -RecreateVenv, or name a working Python with -Python" }
    $parts = $version[0].Split('.')
    if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 11)) {
        Stop-Update "Python $($version[0]) is too old" "reqtool needs Python 3.11 or later"
    }
    Write-Ok "Python $($version[0]) in $where"

    # 3. Packages --------------------------------------------------------------------------------
    Write-Step "Packages"
    $target = if ($Dev -or $Test) { '.[test]' } else { '.' }
    Invoke-Checked "pip install" "Read pip's message above; a proxy may need PIP_INDEX_URL or a certificate" $script:PythonExe ($script:PythonArgs + @('-m', 'pip', 'install', '--disable-pip-version-check', '--quiet', '--upgrade', 'pip'))
    Invoke-Checked "pip install" "Read pip's message above; a proxy may need PIP_INDEX_URL or a certificate" $script:PythonExe ($script:PythonArgs + @('-m', 'pip', 'install', '--disable-pip-version-check', '--quiet', '--editable', $target))
    $shared = if ($Python -or $System) { " This Python is shared with other programs: the default, .venv, keeps reqtool's packages apart." } else { "" }
    Invoke-Checked "pip check" "A package above conflicts with another.$shared Run again with -RecreateVenv to start clean" $script:PythonExe ($script:PythonArgs + @('-m', 'pip', 'check', '--disable-pip-version-check'))
    Write-Ok "reqtool and its dependencies installed ($target)"

    # 4. Command ---------------------------------------------------------------------------------
    Write-Step "Command"
    $null = Invoke-Req @('--help')
    if ($LASTEXITCODE -ne 0) { Stop-Update "req does not start" "Its error is above. Run again with -RecreateVenv" }
    $reqVersion = (& $script:PythonExe @script:PythonArgs -c "import reqtool; print(reqtool.__version__)" | Select-Object -First 1)
    Write-Ok "reqtool $reqVersion"
    $find = "import os, sysconfig; dirs = [sysconfig.get_path('scripts'), sysconfig.get_path('scripts', os.name + '_user')]; " +
            "print(next((d for d in dirs if os.path.isfile(os.path.join(d, 'req.exe')) or os.path.isfile(os.path.join(d, 'req'))), dirs[0]))"
    $scripts = (& $script:PythonExe @script:PythonArgs -c $find | Select-Object -First 1).Trim()
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $userEntries = @("$userPath" -split ';' | Where-Object { $_ })
    $isFirst = $userEntries.Count -gt 0 -and $userEntries[0].TrimEnd('\') -eq $scripts.TrimEnd('\')
    if ($NoPath) {
        Write-Note "PATH left alone (-NoPath)"
    } elseif (-not $IsWindowsHost) {
        Write-Note "not Windows: add $scripts to PATH in your shell profile, or activate .venv"
    } elseif (-not $isFirst) {
        $others = @($userEntries | Where-Object { $_.TrimEnd('\') -ne $scripts.TrimEnd('\') })
        [Environment]::SetEnvironmentVariable('Path', (@($scripts) + $others) -join ';', 'User')
        $env:Path = "$scripts;$env:Path"
        Write-Ok "$scripts is now first on your user PATH. Open a new terminal to use it there"
    }
    $command = Get-Command req -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $mine = $command -and ((Split-Path -Parent $command.Source).TrimEnd('\') -eq $scripts.TrimEnd('\'))
    if ($mine) {
        Write-Ok "req on the PATH is this install ($($command.Source))"
    } else {
        if ($command) { Write-Note "the req on the PATH is another install: $($command.Source)" }
        else { Write-Note "req is not on the PATH" }
        Write-Note "run without -NoPath to put $scripts first, or use $(Join-Path $scripts 'req')"
    }

    # 5. Tools -----------------------------------------------------------------------------------
    Write-Step "Tools"
    Invoke-Req @('tools', '--quiet')
    if ($LASTEXITCODE -ne 0) { Stop-Update "a required tool is missing" "Install what is named above (git is required), then run again" }
    Write-Ok "git found; Vale installed or not needed (req tools --check lists them)"

    # 6. Web UI ----------------------------------------------------------------------------------
    Write-Step "Web UI"
    $index = Join-Path $UiDir 'dist/index.html'
    $built = Test-Path $index
    $stale = $built -and ((Get-UiSourceTime) -gt (Get-Item -LiteralPath $index).LastWriteTimeUtc)
    if ($NoUi) {
        Write-Note "not built (-NoUi)$(if (-not $built) { '; req serve shows a page saying how to build it' })"
    } elseif ($built -and -not $stale -and -not $RebuildUi) {
        Write-Ok "the build is up to date"
    } else {
        $why = if ($RebuildUi) { "-RebuildUi" } elseif ($stale) { "its sources changed" } else { "there is no build" }
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
            Stop-Update "the UI needs building ($why), but npm was not found" "Install Node.js 18 or later from https://nodejs.org/, or run with -NoUi"
        }
        Write-Host "    building, because $why"
        Invoke-Npm "npm ci" @('ci', '--no-audit', '--no-fund')
        Invoke-Npm "npm run build" @('run', 'build')
        if (-not (Test-Path $index)) { Stop-Update "the build wrote no dist/index.html" "The build log is above" }
        Write-Ok "built into src/reqtool/ui/dist"
    }

    # 7. Container -------------------------------------------------------------------------------
    if ($Docker) {
        Write-Step "Container"
        $compose = Join-Path $Root 'docker-compose.yml'
        & docker info *> $null
        if ($LASTEXITCODE -ne 0) { Stop-Update "Docker does not answer" "Start Docker Desktop or the Docker service, or run without -Docker" }
        Invoke-Checked "docker compose build" "The build log is above" docker @('compose', '-f', $compose, 'build')
        Write-Ok "server image built"
        $running = & docker compose -f $compose ps --status running --quiet
        if ($running) {
            Invoke-Checked "docker compose up" "See .\scripts\docker.ps1 -Action Logs" docker @('compose', '-f', $compose, 'up', '-d')
            Write-Ok "server restarted on the new image"
        } else {
            Write-Note "the server is not running; start it with .\scripts\docker.ps1"
        }
    }

    # 8. Tests -----------------------------------------------------------------------------------
    if ($Test) {
        Write-Step "Tests"
        Invoke-Checked "the Python test suite" "A failing test above names what broke" $script:PythonExe ($script:PythonArgs + @('-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--ignore=tests/e2e'))
        if ($NoUi -or -not (Get-Command npm -ErrorAction SilentlyContinue)) {
            Write-Note "UI tests skipped (they need Node.js)"
        } else {
            if (-not (Test-Path (Join-Path $UiDir 'node_modules'))) { Invoke-Npm "npm ci" @('ci', '--no-audit', '--no-fund') }
            Invoke-Npm "the UI tests" @('test')
        }
        Write-Ok "tests pass"
    }

    $minutes = [math]::Round(((Get-Date) - $script:Started).TotalMinutes, 1)
    Write-Host ""
    Write-Host "reqtool is up to date and working ($minutes min)." -ForegroundColor Green
    exit 0
} finally {
    Pop-Location
}
