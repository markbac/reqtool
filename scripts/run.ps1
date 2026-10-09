#Requires -Version 5.1
<#
.SYNOPSIS
    Run reqtool: the API server and the web UI together, or either one on its own.

.DESCRIPTION
    Creates a .venv and installs reqtool the first time, builds the UI when it is missing, then starts
    what you asked for. Safe to run repeatedly.

.PARAMETER Mode
    Combined  One process: `req serve` serves the API and the built UI on one port (default).
    Server    The API only. No Node.js needed, the UI is not built.
    Ui        The Vite dev server with hot reload. It proxies API calls to a server you run separately
              (for example `.\scripts\run.ps1 -Mode Server` in another window).
    Dev       Both for development: the API in the background and the Vite dev server in the foreground.
              Ctrl+C stops both.

.PARAMETER Repo
    The requirements repository to serve. Defaults to $env:REQTOOL_REPO, then the current directory.

.PARAMETER Port
    API port (default 8765, or $env:REQTOOL_PORT). The Vite dev server proxies to 8765, so use another
    port only with Combined or Server.

.PARAMETER HostName
    Address to bind (default 127.0.0.1, or $env:REQTOOL_HOST).

.PARAMETER Auth
    local (no login, loopback only) or required (login for every call). Passed to `req serve --auth`.

.PARAMETER UiPort
    Port for the Vite dev server in Ui and Dev modes (default 5173).

.PARAMETER Browser
    Open the default browser once the server is up.

.PARAMETER Rebuild
    Rebuild the UI even if a build exists (Combined mode).

.EXAMPLE
    .\scripts\run.ps1                                  # API + UI on http://127.0.0.1:8765
    .\scripts\run.ps1 -Repo C:\reqs -Browser           # serve another repository and open the browser
    .\scripts\run.ps1 -Mode Server -Auth required      # API only, login required
    .\scripts\run.ps1 -Mode Ui                         # hot-reload UI against a running server
    .\scripts\run.ps1 -Mode Dev                        # API + hot-reload UI
#>

[CmdletBinding()]
param(
    [ValidateSet('Combined', 'Server', 'Ui', 'Dev')]
    [string]$Mode = 'Combined',

    [string]$Repo = $env:REQTOOL_REPO,

    [int]$Port = $(if ($env:REQTOOL_PORT) { [int]$env:REQTOOL_PORT } else { 8765 }),

    [string]$HostName = $(if ($env:REQTOOL_HOST) { $env:REQTOOL_HOST } else { '127.0.0.1' }),

    [ValidateSet('local', 'required')]
    [string]$Auth = 'local',

    [int]$UiPort = 5173,

    [switch]$Browser,

    [switch]$Rebuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$RepoDir   = Split-Path -Parent $ScriptDir
$UiDir     = [IO.Path]::Combine($RepoDir, 'src', 'reqtool', 'ui')
$UiIndex   = [IO.Path]::Combine($UiDir, 'dist', 'index.html')
$VenvDir   = Join-Path $RepoDir '.venv'
$IsWin     = [IO.Path]::DirectorySeparatorChar -eq '\'
$VenvPy    = if ($IsWin) { [IO.Path]::Combine($VenvDir, 'Scripts', 'python.exe') } else { [IO.Path]::Combine($VenvDir, 'bin', 'python') }
$SystemPy  = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
$ServerUrl = "http://${HostName}:${Port}"

function Write-Step { param([string]$Msg) Write-Host $Msg -ForegroundColor Cyan }
function Write-Note { param([string]$Msg) Write-Host $Msg -ForegroundColor Yellow }

function Assert-Command {
    param([string]$Name, [string]$Hint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "'$Name' was not found. $Hint"
    }
}

function Install-Venv {
    if (Test-Path $VenvPy) { return }
    Assert-Command $SystemPy 'Install Python 3.11 or newer, or set $env:PYTHON.'
    $version = & $SystemPy -c "import sys; print('%d.%d' % sys.version_info[:2])"
    $parts = $version.Split('.')
    if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 11)) {
        throw "Python 3.11 or newer is required (found $version)."
    }
    Write-Step "Creating the virtual environment in $VenvDir ..."
    & $SystemPy -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
    Write-Step 'Installing reqtool (editable) ...'
    & $VenvPy -m pip install --quiet --upgrade pip
    & $VenvPy -m pip install --quiet -e $RepoDir
    if ($LASTEXITCODE -ne 0) { throw 'pip install failed.' }
}

# Check the other tools reqtool uses (git, Node.js) and install Vale if it is missing. Never fatal, and quiet
# when everything is there. Runs every time, so a tool that went missing is noticed.
function Initialize-Tools {
    & $VenvPy -m reqtool.cli tools --quiet
    if ($LASTEXITCODE -ne 0) { Write-Note 'A required tool is missing (see above). Run: req tools' }
}

function Initialize-Python {
    Install-Venv
    Initialize-Tools
}

function Invoke-Npm {
    param([string[]]$NpmArgs)
    Push-Location $UiDir
    try {
        & npm @NpmArgs
        if ($LASTEXITCODE -ne 0) { throw "npm $($NpmArgs -join ' ') failed (exit $LASTEXITCODE)." }
    }
    finally { Pop-Location }
}

function Initialize-Ui {
    param([switch]$ForceBuild)
    Assert-Command npm 'Install Node.js 18 or newer from https://nodejs.org/ (or use -Mode Server).'
    if (-not (Test-Path ([IO.Path]::Combine($UiDir, 'node_modules')))) {
        Write-Step 'Installing UI dependencies ...'
        Invoke-Npm @('install', '--legacy-peer-deps')
    }
    if ($ForceBuild -or -not (Test-Path $UiIndex)) {
        Write-Step 'Building the UI ...'
        Invoke-Npm @('run', 'build')
    }
}

function Get-ServeArgs {
    $serveArgs = @('-m', 'reqtool.cli', 'serve', '--host', $HostName, '--port', "$Port", '--auth', $Auth)
    if ($Repo) { $serveArgs += @('--repo', $Repo) }
    return $serveArgs
}

function Wait-ForServer {
    param([int]$Seconds = 40)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $null = Invoke-WebRequest -Uri "$ServerUrl/health" -UseBasicParsing -TimeoutSec 2
            return $true
        }
        catch {
            # A 401 or 403 still means the server is answering.
            if ($_.Exception.PSObject.Properties['Response'] -and $_.Exception.Response) { return $true }
            Start-Sleep -Milliseconds 300
        }
    }
    return $false
}

function Open-InBrowser {
    param([string]$Url)
    if ($IsWin) { Start-Process $Url }
    elseif (Get-Command xdg-open -ErrorAction SilentlyContinue) { & xdg-open $Url }
    elseif (Get-Command open -ErrorAction SilentlyContinue) { & open $Url }
}

function Show-Where {
    Write-Host "Repository: $(if ($Repo) { $Repo } else { (Get-Location).Path })"
    Write-Host 'Press Ctrl+C to stop.'
    Write-Host ''
}

switch ($Mode) {

    'Combined' {
        Initialize-Python
        Initialize-Ui -ForceBuild:$Rebuild
        Write-Step "reqtool (API + UI) at $ServerUrl"
        Show-Where
        $browserJob = $null
        if ($Browser) {
            # Open the page once the server answers, without blocking the server itself.
            $browserJob = Start-Job -ScriptBlock {
                param($url)
                for ($i = 0; $i -lt 100; $i++) {
                    try { $null = Invoke-WebRequest -Uri "$url/health" -UseBasicParsing -TimeoutSec 2; break }
                    catch { if ($_.Exception.PSObject.Properties['Response'] -and $_.Exception.Response) { break }; Start-Sleep -Milliseconds 300 }
                }
                Start-Process $url
            } -ArgumentList $ServerUrl
        }
        try { & $VenvPy @(Get-ServeArgs) }
        finally { if ($browserJob) { Remove-Job $browserJob -Force -ErrorAction SilentlyContinue } }
    }

    'Server' {
        Initialize-Python
        Write-Step "reqtool API at $ServerUrl (no UI is built in this mode)"
        Show-Where
        & $VenvPy @(Get-ServeArgs)
    }

    'Ui' {
        Assert-Command npm 'Install Node.js 18 or newer from https://nodejs.org/.'
        if ($Port -ne 8765) {
            Write-Note "The Vite dev server proxies to port 8765 (see ui/vite.config.js), but -Port is $Port."
        }
        if (-not (Test-Path ([IO.Path]::Combine($UiDir, 'node_modules')))) {
            Write-Step 'Installing UI dependencies ...'
            Invoke-Npm @('install', '--legacy-peer-deps')
        }
        Write-Step "UI dev server at http://localhost:$UiPort (API calls go to http://localhost:8765)"
        Write-Note 'Start the API in another window with: .\scripts\run.ps1 -Mode Server'
        if ($Browser) { Open-InBrowser "http://localhost:$UiPort" }
        Invoke-Npm @('run', 'dev', '--', '--port', "$UiPort")
    }

    'Dev' {
        Initialize-Python
        Assert-Command npm 'Install Node.js 18 or newer from https://nodejs.org/.'
        if ($Port -ne 8765) {
            throw 'Dev mode needs -Port 8765 because the Vite dev server proxies to it.'
        }
        if (-not (Test-Path ([IO.Path]::Combine($UiDir, 'node_modules')))) {
            Write-Step 'Installing UI dependencies ...'
            Invoke-Npm @('install', '--legacy-peer-deps')
        }
        Write-Step "Starting the API at $ServerUrl in the background ..."
        $server = Start-Process -FilePath $VenvPy -ArgumentList (Get-ServeArgs) -PassThru -NoNewWindow
        try {
            if (-not (Wait-ForServer)) { throw "The API did not start within 40 seconds." }
            Write-Step "UI dev server at http://localhost:$UiPort (hot reload)"
            Show-Where
            if ($Browser) { Open-InBrowser "http://localhost:$UiPort" }
            Invoke-Npm @('run', 'dev', '--', '--port', "$UiPort")
        }
        finally {
            if ($server -and -not $server.HasExited) {
                Write-Note 'Stopping the API ...'
                Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
            }
        }
    }
}
