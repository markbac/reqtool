# scripts

Dev runner scripts for reqtool. Run `install` first -- it creates the virtual
environment, builds the React UI, and installs the Python package in one step.

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

If your execution policy blocks the script:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

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
