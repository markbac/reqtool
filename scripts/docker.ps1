#Requires -Version 5.1
<#
.SYNOPSIS
    Run the reqtool server in a Docker container: build it, set up its repository, add users, start and stop it.

.DESCRIPTION
    Wraps `docker compose` with the docker-compose.yml at the root of this repository. The server runs in
    server mode with login required, and serves the requirements repository in the container's /repo:
    the named volume reqtool-repo, or the host folder given with -RepoDir.

    First time:
        .\scripts\docker.ps1 -Action Build
        .\scripts\docker.ps1 -Action Init -Flavour defaults -Id my-reqs -Title "My requirements"
        .\scripts\docker.ps1 -Action AddUser -UserName admin -Role admin
        .\scripts\docker.ps1 -Action Start

.PARAMETER Action
    Build     Build the image (-NoCache to rebuild every layer).
    Start     Start the server in the background and wait until /health answers (default).
    Stop      Stop and remove the container. The repository volume is kept.
    Restart   Restart the container, for example after Init.
    Status    Show the container and the answer from /health.
    Logs      Follow the server log. Ctrl+C stops following, not the server.
    Init      Set up an empty repository: git init, `req init <Flavour>` and a first commit.
    AddUser   Create an account with `req user add` (asks for the password).
    Req       Run any req command in the container, for example: -Action Req validate
    Shell     Open a shell in a new container on the same repository.

.PARAMETER RepoDir
    Host folder to use as the repository instead of the named volume (sets $env:REQTOOL_REPO_DIR).
    Use the same value for every action. On Linux the folder must belong to the user given with -Uid at Build.

.PARAMETER Port
    Port on this machine (default 8765, or $env:REQTOOL_PORT).

.PARAMETER Uid
    User and group ID the server runs as, applied at Build (default 1000, or $env:REQTOOL_UID).
    Match the owner of -RepoDir so files written by the server belong to you.

.PARAMETER Flavour
    For Init: blank, agile, systems, defaults (default) or demo.

.PARAMETER Id
    For Init: the repository ID (slug). Ignored by demo.

.PARAMETER Title
    For Init: the repository title. Ignored by demo.

.PARAMETER GitName
    For Init: the author of the first commit (default reqtool).

.PARAMETER GitEmail
    For Init: the e-mail address of the first commit (default reqtool@localhost).

.PARAMETER UserName
    For AddUser: the account name.

.PARAMETER Role
    For AddUser: admin, editor (default) or viewer.

.PARAMETER NoCache
    For Build: rebuild every layer.

.PARAMETER ReqArgs
    For Req: the req command and its arguments. The image sets REQTOOL_REPO=/repo, so --repo is not needed.

.EXAMPLE
    .\scripts\docker.ps1 -Action Build
    .\scripts\docker.ps1 -Action Init -Flavour agile -Id pump -Title "Pump controller"
    .\scripts\docker.ps1 -Action AddUser -UserName alice -Role admin
    .\scripts\docker.ps1                                   # start
    .\scripts\docker.ps1 -Action Status
    .\scripts\docker.ps1 -Action Req validate
    .\scripts\docker.ps1 Req export pdf --product sensor
    .\scripts\docker.ps1 -Action Start -RepoDir D:\reqs -Port 9000
#>

# Only -Action is positional, so the words after `-Action Req` all go to the req command.
[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Position = 0)]
    [ValidateSet('Build', 'Start', 'Stop', 'Restart', 'Status', 'Logs', 'Init', 'AddUser', 'Req', 'Shell')]
    [string]$Action = 'Start',

    [string]$RepoDir = $env:REQTOOL_REPO_DIR,

    [int]$Port = $(if ($env:REQTOOL_PORT) { [int]$env:REQTOOL_PORT } else { 8765 }),

    [int]$Uid = $(if ($env:REQTOOL_UID) { [int]$env:REQTOOL_UID } else { 1000 }),

    [ValidateSet('blank', 'agile', 'systems', 'defaults', 'demo')]
    [string]$Flavour = 'defaults',

    [string]$Id,

    [string]$Title,

    [string]$GitName = 'reqtool',

    [string]$GitEmail = 'reqtool@localhost',

    [string]$UserName,

    [ValidateSet('admin', 'editor', 'viewer')]
    [string]$Role = 'editor',

    [switch]$NoCache,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ReqArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir   = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$RepoRoot    = Split-Path -Parent $ScriptDir
$ComposeFile = Join-Path $RepoRoot 'docker-compose.yml'
$ServerUrl   = "http://localhost:${Port}"

function Write-Step { param([string]$Msg) Write-Host $Msg -ForegroundColor Cyan }
function Write-Note { param([string]$Msg) Write-Host $Msg -ForegroundColor Yellow }

function Assert-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "'docker' was not found. Install Docker Desktop, or Docker Engine (in WSL 2 on Windows)."
    }
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker is installed but not running. Start Docker Desktop or the Docker service.' }
    & docker compose version *> $null
    if ($LASTEXITCODE -ne 0) { throw "'docker compose' is not available. Install the Docker Compose plugin." }
}

# The settings docker-compose.yml reads.
function Set-ComposeEnv {
    $env:REQTOOL_PORT = "$Port"
    $env:REQTOOL_UID  = "$Uid"
    $env:REQTOOL_GID  = "$Uid"
    if ($RepoDir) {
        if (-not (Test-Path $RepoDir)) { New-Item -ItemType Directory -Path $RepoDir | Out-Null }
        $env:REQTOOL_REPO_DIR = (Resolve-Path $RepoDir).Path
    }
}

function Invoke-Compose {
    param([string[]]$ComposeArgs)
    & docker compose -f $ComposeFile @ComposeArgs
    if ($LASTEXITCODE -ne 0) { throw "docker compose $($ComposeArgs -join ' ') failed (exit $LASTEXITCODE)." }
}

# A one-off container on the same repository, removed afterwards. Works whether or not the server is running.
function Invoke-InContainer {
    param([string[]]$Command)
    Invoke-Compose (@('run', '--rm', 'reqtool') + $Command)
}

function Test-Initialised {
    & docker compose -f $ComposeFile run --rm reqtool test -f /repo/.reqtool/config.yaml *> $null
    return $LASTEXITCODE -eq 0
}

function Wait-ForServer {
    param([int]$Seconds = 60)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $null = Invoke-WebRequest -Uri "$ServerUrl/health" -UseBasicParsing -TimeoutSec 2
            return $true
        }
        catch { Start-Sleep -Milliseconds 500 }
    }
    return $false
}

Assert-Docker
Set-ComposeEnv
if ($RepoDir) { Write-Host "Repository: $env:REQTOOL_REPO_DIR" } else { Write-Host 'Repository: Docker volume reqtool-repo' }

switch ($Action) {

    'Build' {
        Write-Step "Building the reqtool image (user ID $Uid) ..."
        $buildArgs = @('build')
        if ($NoCache) { $buildArgs += '--no-cache' }
        Invoke-Compose $buildArgs
    }

    'Start' {
        if (-not (Test-Initialised)) {
            Write-Note 'The repository is not set up yet. Run: .\scripts\docker.ps1 -Action Init'
        }
        Write-Step 'Starting the reqtool server ...'
        Invoke-Compose @('up', '-d')
        if (Wait-ForServer) { Write-Step "reqtool is running at $ServerUrl" }
        else { Write-Note 'The server did not answer within 60 seconds. See: .\scripts\docker.ps1 -Action Logs' }
    }

    'Stop' {
        Write-Step 'Stopping the reqtool server (the repository is kept) ...'
        Invoke-Compose @('down')
    }

    'Restart' {
        Write-Step 'Restarting the reqtool server ...'
        Invoke-Compose @('restart')
        if (Wait-ForServer) { Write-Step "reqtool is running at $ServerUrl" }
        else { Write-Note 'The server did not answer within 60 seconds. See: .\scripts\docker.ps1 -Action Logs' }
    }

    'Status' {
        Invoke-Compose @('ps')
        try {
            $health = Invoke-RestMethod -Uri "$ServerUrl/health" -TimeoutSec 3
            Write-Step "Health: $($health.status), version $($health.version), $($health.requirements) requirements, mode $($health.operating_mode)"
        }
        catch { Write-Note "No answer from $ServerUrl/health" }
    }

    'Logs' {
        Invoke-Compose @('logs', '--follow', '--tail', '100')
    }

    'Init' {
        if (Test-Initialised) { throw 'The repository is already set up (/repo/.reqtool/config.yaml exists).' }
        Write-Step "Setting up the repository ($Flavour) ..."
        Invoke-InContainer @('sh', '-c', 'test -d /repo/.git || git init -q /repo')
        $initArgs = @('req', 'init')
        if ($Flavour -ne 'blank') { $initArgs += $Flavour }
        $initArgs += @('--repo', '/repo')
        if ($Flavour -ne 'demo') {
            if ($Id) { $initArgs += @('--id', $Id) }
            if ($Title) { $initArgs += @('--title', $Title) }
        }
        Invoke-InContainer $initArgs
        Write-Step 'Making the first commit ...'
        # The identity goes in as environment variables, so a name with quotes or spaces needs no escaping.
        $identity = @('-e', "GIT_AUTHOR_NAME=$GitName", '-e', "GIT_AUTHOR_EMAIL=$GitEmail",
                      '-e', "GIT_COMMITTER_NAME=$GitName", '-e', "GIT_COMMITTER_EMAIL=$GitEmail")
        Invoke-Compose (@('run', '--rm') + $identity + @('reqtool', 'sh', '-c',
                        'cd /repo && git add -A && git commit -q -m "Initialise requirements repository"'))
        Write-Step 'Repository ready. Next: create the first administrator with -Action AddUser -Role admin'
    }

    'AddUser' {
        if (-not $UserName) { throw 'Give the account name with -UserName.' }
        Invoke-InContainer @('req', 'user', 'add', $UserName, '--role', $Role, '--repo', '/repo')
    }

    'Req' {
        if (-not $ReqArgs) { throw 'Give the req command, for example: .\scripts\docker.ps1 -Action Req validate' }
        Invoke-InContainer (@('req') + $ReqArgs)
    }

    'Shell' {
        Invoke-InContainer @('bash')
    }
}
