# scripts

Dev runner scripts for reqtool. Run `install` first -- it creates the virtual
environment, builds the React UI, and installs the Python package in one step.
Whenever the venv is checked, the scripts also run `req tools`, which checks for git and Node.js and
downloads [Vale](https://vale.sh) (verified against its published checksum, kept in `~/.reqtool/tools`)
if it is missing. Run `req tools --check` to see what is installed, or `req tools --force` to retry a failed download.

## dev.sh (Linux / macOS)

```bash
chmod +x scripts/dev.sh   # first time only

./scripts/dev.sh install            # build UI + install everything  ← start here
./scripts/dev.sh serve              # start the server
./scripts/dev.sh test               # full test suite
./scripts/dev.sh test core          # store + validation + CLI  (~20s)
./scripts/dev.sh test features      # v0.3.0 feature suite     (~30s)
./scripts/dev.sh test api           # API + regression         (~2 min)
./scripts/dev.sh validate           # req validate in cwd
./scripts/dev.sh verify             # req verify in cwd
./scripts/dev.sh req <args>         # any req subcommand
./scripts/dev.sh shell              # drop into venv shell
./scripts/dev.sh help               # show usage
```

## dev.ps1 (Windows PowerShell)

```powershell
.\scripts\dev.ps1 install           # build UI + install everything  ← start here
.\scripts\dev.ps1 serve             # start the server
.\scripts\dev.ps1 test              # full test suite
.\scripts\dev.ps1 test core         # store + validation + CLI
.\scripts\dev.ps1 test features     # v0.3.0 feature suite
.\scripts\dev.ps1 test api          # API + regression
.\scripts\dev.ps1 validate          # req validate in cwd
.\scripts\dev.ps1 verify            # req verify in cwd
.\scripts\dev.ps1 req <args>        # any req subcommand
.\scripts\dev.ps1 shell             # activate venv in current session
.\scripts\dev.ps1 help              # show usage
```

## run.ps1 (Windows PowerShell: run the tool)

`run.ps1` starts reqtool; `dev.ps1` is for setting up and testing. The first run creates `.venv`, installs reqtool and builds the UI.

```powershell
.\scripts\run.ps1                              # API + UI together on http://127.0.0.1:8765
.\scripts\run.ps1 -Repo C:\reqs -Browser       # another repository, open the browser
.\scripts\run.ps1 -Mode Server                 # API only (no Node.js needed)
.\scripts\run.ps1 -Mode Server -Auth required  # API only, login required
.\scripts\run.ps1 -Mode Ui                     # hot-reload UI (Vite, port 5173) against a running API
.\scripts\run.ps1 -Mode Dev                    # API in the background + hot-reload UI, Ctrl+C stops both
.\scripts\run.ps1 -Rebuild                     # rebuild the UI first
```

Add `-RepoMode local`, `server` or `shared-repo` to choose how the repository is used (the [three modes](../README.md#starting-reqtool-the-three-modes)). `-RepoMode server` requires a login, listens on every address and offers to create the first administrator. `-RepoMode shared-repo` runs `req setup` and pulls the latest before starting. `-RepoMode` is not the same as `-Mode`, which chooses whether the API, the UI or both run.

```powershell
.\scripts\run.ps1 -RepoMode server -Repo C:\reqs           # shared server, login required
.\scripts\run.ps1 -RepoMode shared-repo -Repo C:\reqs      # your clone, synced through git
```

`Combined` is the normal way to use the tool. `Ui` and `Dev` are for working on the UI: the Vite dev server proxies API calls to port 8765. Get-Help `.\scripts\run.ps1 -Full` lists every parameter.

If your execution policy blocks the script:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## update.ps1 (Windows PowerShell: bring an install up to date)

Run it after every `git pull`, or whenever reqtool misbehaves after a change. Each step says what it does, and the script stops at the first one that fails, with what to do about it.

1. Pulls (fast-forward only), and runs the new copy of itself when the pull changed it.
1. Makes or repairs `.venv` (Python 3.11 or later), the same environment `run.ps1` and `dev.ps1` use.
1. Runs `pip install -e .` and `pip check`.
1. Checks that `req` runs, and puts this install first on your user PATH.
1. Runs `req tools` (git is required; Vale is installed if it is missing).
1. Builds the web UI when its sources are newer than its build.
1. With `-Docker`, rebuilds the server image, and restarts the server when it is running.
1. With `-Test`, runs the Python and UI tests.

```powershell
.\scripts\update.ps1                    # the usual
.\scripts\update.ps1 -Dev -Test         # with the test tools, then run the tests
.\scripts\update.ps1 -Docker            # also rebuild and restart the server container
.\scripts\update.ps1 -NoPull -RebuildUi # use the code as it is, rebuild the UI anyway
```

`Get-Help .\scripts\update.ps1 -Full` lists every option (`-NoUi`, `-NoPath`, `-RecreateVenv`, `-Python`, `-System`).

## docker.ps1 (run the server in a container)

`docker.ps1` runs the shared server (server mode, login required) in Docker, with the `docker-compose.yml` at the repository root. It needs Docker and the Compose plugin, not Python or Node.js. See [Running the server in a container](../docs/USER_GUIDE.md#13-running-the-server-in-a-container).

```powershell
.\scripts\docker.ps1 -Action Build                       # build the image
.\scripts\docker.ps1 -Action Init -Flavour defaults -Id my-reqs -Title "My requirements"
.\scripts\docker.ps1 -Action AddUser -UserName admin -Role admin   # the first administrator
.\scripts\docker.ps1                                     # start, on http://localhost:8765
.\scripts\docker.ps1 -Action Status                      # container state and /health
.\scripts\docker.ps1 -Action Logs                        # follow the log
.\scripts\docker.ps1 Req validate                        # any req command in the container
.\scripts\docker.ps1 -Action Stop                        # stop; the repository is kept
.\scripts\docker.ps1 -Action Start -RepoDir D:\reqs      # a host folder instead of the Docker volume
```

`Get-Help .\scripts\docker.ps1 -Full` lists every parameter.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REQTOOL_REPO` | current directory | Requirements repository root |
| `REQTOOL_PORT` | `8765` | Server port |
| `REQTOOL_HOST` | `127.0.0.1` | Server host |
| `PYTHON` | `python3` / `python` | Python interpreter |

## Examples

```bash
# Point the server at an existing requirements repository
REQTOOL_REPO=~/my-reqs ./scripts/dev.sh serve

# Use a different port
REQTOOL_PORT=9000 ./scripts/dev.sh serve

# Use a specific Python version
PYTHON=python3.12 ./scripts/dev.sh test core

# Initialise a new agile repo and serve it
./scripts/dev.sh req init agile --repo ~/my-reqs --id my-proj --title "My Project"
REQTOOL_REPO=~/my-reqs ./scripts/dev.sh serve
```

```powershell
# Point the server at an existing requirements repository
$env:REQTOOL_REPO = 'C:\my-reqs'
.\scripts\dev.ps1 serve

# Initialise and serve
.\scripts\dev.ps1 req init agile --repo C:\my-reqs --id my-proj --title "My Project"
$env:REQTOOL_REPO = 'C:\my-reqs'
.\scripts\dev.ps1 serve
```
