# `reqtool` Standalone Executable Guide

The standalone executable release of **`reqtool`** provides the full requirements management engine, REST API backend, CLI tools, and React Web Workstation bundled as standalone binary executables.

**No Python, Node.js, or external dependencies are required to run `reqtool-web.exe` or `reqtool-app.exe`.**

---

## 1. Executable Release Options

| Executable | Auto-Launch Behavior | Recommended Use Case |
| :--- | :--- | :--- |
| **`reqtool-web.exe`** | Automatically launches the Web Workstation in your default web browser (`http://localhost:8765`). | General engineering work, browser tab navigation, dual-screen setups. |
| **`reqtool-app.exe`** | Automatically launches the visual workstation in a dedicated standalone application window. | Distraction-free native app experience for requirements engineers. |
| **`reqtool-server.exe`** | Automatically launches central backend server listening on `0.0.0.0:8765`. | Multi-user team server hosting requirements repository for remote client connections. |
| **`reqtool-client.exe`** | Automatically launches desktop client application configured with Remote Server Login UI. | Multi-user remote client connecting to central backend server with login credentials. |
| **`reqtool.exe`** | Command Line Interface (CLI). Run with `--help` for available subcommands. | Terminal workflows, CI/CD scripts, automated validation & exports. |

---

## 2. Quick Start

### 2.1 Downloading Executables
Download the executable binaries for your operating system from the [GitHub Releases Page](https://github.com/markbac/reqtool/releases):
- **Windows:** `reqtool-web-windows-amd64.exe`, `reqtool-app-windows-amd64.exe`, `reqtool-cli-windows-amd64.exe`
- **Linux:** `reqtool-web-linux-amd64`, `reqtool-app-linux-amd64`, `reqtool-cli-linux-amd64`
- **macOS:** `reqtool-web-macos-amd64`, `reqtool-app-macos-amd64`, `reqtool-cli-macos-amd64`

### 2.2 Launching the Application

#### Web Interface Executable
Double-click `reqtool-web.exe` (or run `./reqtool-web.exe` from terminal). The backend server will start and automatically open your default browser to `http://localhost:8765`.

#### Native App Executable
Double-click `reqtool-app.exe` (or run `./reqtool-app.exe` from terminal). The workstation will launch in an isolated desktop application window.

#### Command Line Executable
```cmd
reqtool.exe --help
reqtool.exe init defaults
reqtool.exe validate
reqtool.exe export --format csv
```

---

## 3. In-Tool Repository Management (Switch & Init)

Both `reqtool-web.exe` and `reqtool-app.exe` feature dynamic repository switching and initialization directly inside the UI without needing to restart the process.

### 3.1 Opening Repository Management
Click the **`📦 Repo`** button in the top navigation bar (or select **📦 Repository** from the overflow `⋮` menu).

### 3.2 Switching Repositories
1. Open the **📦 Repository** modal.
2. Select the **Switch Repository** tab.
3. Enter the absolute directory path of an existing `reqtool` repository.
4. Click **Switch Repository**. The backend will instantly validate the path, load the target repository, and refresh the UI tree.

### 3.3 Initializing a New Repository
1. Open the **📦 Repository** modal.
2. Select the **Init New Repository** tab.
3. Enter the directory path for the new repository.
4. (Optional) Provide a Repo ID slug and Title.
5. Select the template mode:
   - **Engineering Defaults:** Pre-populates ~30 engineering principles, standard enums, and workflows.
   - **Blank Repository:** Creates clean repository directory structure with empty configuration files.
6. Click **Initialize Repository**. The new repository will be created and immediately loaded into the UI.

---

## 4. Multi-User Server & Remote Client Setup

`reqtool` supports multi-user collaboration where a central backend server hosts the requirements repository, and multiple team members connect remotely using `reqtool-client.exe` or web browser.

### 4.1 Running Central Server (`reqtool-server.exe`)
Launch `reqtool-server.exe` on your server host machine:
```cmd
reqtool-server.exe --port 8765
```
- Listens on `0.0.0.0:8765` by default, making it accessible across your local network or server IP.
- No default account exists. Create the first administrator on the server with `req user add <name> --role admin` (prompts for a password).

### 4.2 Client Remote Connection & User Login (`reqtool-client.exe`)
1. Launch `reqtool-client.exe` on client desktop.
2. Click **🔐 User / Login** widget in top navigation bar or menu.
3. Enter Server URL (e.g. `http://server-hostname:8765`).
4. Enter the username and password of the account created with `req user add`.
5. Click **Login & Connect**.
6. The client authenticates via JWT token and connects to the central server repository.

---

## 5. Command Line Reference (`reqtool.exe`)

| Command | Usage & Purpose |
| :--- | :--- |
| `reqtool.exe serve` | Starts the backend API & Web Workstation. Use `--browser` for browser auto-open, `--app` for desktop app mode, `--port <N>` for custom ports. |
| `reqtool.exe init` | Initialises `.reqtool/` config in current directory. Subcommands: `defaults`, `agile`, `systems`, `demo`. |
| `reqtool.exe validate` | Runs full schema checks, vocabulary validation, and INCOSE prose quality linter. Exits 0 if clean. |
| `reqtool.exe export` | Exports requirements to CSV, ReqIF 1.2 XML, Markdown document tree, or React JSX components. |
| `reqtool.exe new` | Interactively creates a new requirement, principle, or TBD artefact. |
| `reqtool.exe new-agile` | Interactively creates an agile planning item (`story`, `task`, `bug`, `epic`, `initiative`). |
| `reqtool.exe diff` | Shows requirement changes and version increments since a Git ref (e.g. `reqtool.exe diff HEAD~1`). |
| `reqtool.exe stats` | Displays project summary metrics, quality gap counters, and approval rates. |
| `reqtool.exe openapi` | Exports the full OpenAPI 3.0 REST spec to `openapi.json` or `stdout`. |

---

## 5. Standalone Architecture & Self-Containment

```
  ┌─────────────────────────────────────────────────────────────┐
  │         reqtool-web.exe / reqtool-app.exe Standalone        │
  │                                                             │
  │  ┌──────────────────┐ ┌──────────────────┐ ┌─────────────┐  │
  │  │ Python 3.12 Engine│ │ FastAPI REST Server│ │ Embedded UI │  │
  │  │  (store / linter)│ │   (& WebSockets) │ │ (React SPA) │  │
  │  └──────────────────┘ └──────────────────┘ └─────────────┘  │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼ Dynamic Store Load / Switch
  ┌─────────────────────────────────────────────────────────────┐
  │         Git-Backed Repository (.reqtool / YAML files)       │
  └─────────────────────────────────────────────────────────────┘
```

- **Single Binary Executable:** Includes PyInstaller bootloader, Python runtime, FastAPI REST API, INCOSE linter rules, and pre-compiled React SPA assets.
- **Zero Installation:** Download and run directly. No setup installers, admin permissions, or external runtimes required.
