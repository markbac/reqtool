# `reqtool` Standalone Executable (`reqtool.exe`) Guide

The standalone executable release of **`reqtool`** provides the full requirements management engine, REST API backend, CLI tools, and React Web Workstation bundled as a single binary executable (`reqtool.exe`).

**No Python, Node.js, or external dependencies are required to run `reqtool.exe`.**

---

## 1. Quick Start

### 1.1 Download
Download the latest executable binary for your operating system from the [GitHub Releases Page](https://github.com/markbac/reqtool/releases):
- **Windows:** `reqtool-windows-amd64.exe` (or `reqtool.exe`)
- **Linux:** `reqtool-linux-amd64`
- **macOS:** `reqtool-macos-amd64`

### 1.2 Running the Application

#### Option A: Native Desktop App Window Mode (Recommended for Engineers)
Launches the server and automatically opens the visual workstation in a dedicated, frameless desktop window:
```cmd
reqtool.exe serve --app
```

#### Option B: Web Workstation Server Mode
Launches the backend server and serves the visual workstation at `http://localhost:8765`:
```cmd
reqtool.exe serve
```

#### Option C: Terminal CLI Commands
Execute CLI operations directly from PowerShell or Command Prompt:
```cmd
reqtool.exe --help
reqtool.exe init defaults
reqtool.exe validate
reqtool.exe export --format csv
```

---

## 2. Command Line Reference (`reqtool.exe`)

| Command | Usage & Purpose |
| :--- | :--- |
| `reqtool.exe serve` | Starts the backend API & Web Workstation. Use `--app` to launch in a desktop window, `--port <N>` for custom ports. |
| `reqtool.exe init` | Initialises `.reqtool/` config in current directory. Subcommands: `defaults`, `agile`, `systems`, `demo`. |
| `reqtool.exe validate` | Runs full schema checks, vocabulary validation, and INCOSE prose quality linter. Exits 0 if clean. |
| `reqtool.exe export` | Exports requirements to CSV, ReqIF 1.2 XML, Markdown document tree, or React JSX components. |
| `reqtool.exe new` | Interactively creates a new requirement, principle, or TBD artefact. |
| `reqtool.exe new-agile` | Interactively creates an agile planning item (`story`, `task`, `bug`, `epic`, `initiative`). |
| `reqtool.exe diff` | Shows requirement changes and version increments since a Git ref (e.g. `reqtool.exe diff HEAD~1`). |
| `reqtool.exe stats` | Displays project summary metrics, quality gap counters, and approval rates. |
| `reqtool.exe openapi` | Exports the full OpenAPI 3.0 REST spec to `openapi.json` or `stdout`. |

---

## 3. Environment Variables & Configuration

Set these environment variables in your terminal or script before launching `reqtool.exe`:

- `REQTOOL_REPO`: Absolute path to target requirements repository directory (defaults to current working directory).
- `REQTOOL_PORT`: Port number for API and UI server (defaults to `8765`).
- `REQTOOL_HOST`: Network bind host (defaults to `127.0.0.1` for localhost security; use `0.0.0.0` for team access).

**Example (Windows PowerShell):**
```powershell
$env:REQTOOL_REPO = "D:\Engineering\Project-Saturn"
$env:REQTOOL_PORT = "9000"
.\reqtool.exe serve --app
```

---

## 4. Standalone Architecture & Self-Containment

```
  ┌─────────────────────────────────────────────────────────────┐
  │                   reqtool.exe (Standalone)                  │
  │                                                             │
  │  ┌──────────────────┐ ┌──────────────────┐ ┌─────────────┐  │
  │  │ Python 3.12 Engine│ │ FastAPI REST Server│ │ Embedded UI │  │
  │  │  (store / linter)│ │   (& WebSockets) │ │ (React SPA) │  │
  │  └──────────────────┘ └──────────────────┘ └─────────────┘  │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼ Reads & Writes
  ┌─────────────────────────────────────────────────────────────┐
  │         Git-Backed Repository (.reqtool / YAML files)       │
  └─────────────────────────────────────────────────────────────┘
```

- **Single Binary Executable:** Includes the PyInstaller bootloader, Python 3.12 runtime, FastAPI REST routers, INCOSE style rule sets, and bundled React SPA workstation assets.
- **Git Backed:** All requirement edits, principles, and TBDs remain 100% human-readable YAML files committed to your Git repository history.
