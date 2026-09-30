# `reqtool` -- Product Overview & Technical Specification

**Version 0.4.0** | **Enterprise Systems Engineering & Agile Requirements Management Engine**

---

## 1. Executive Summary

**`reqtool`** is a high-performance, git-backed requirements engineering workstation and multi-user server designed for complex engineering programmes (aerospace, automotive, medical devices, defense, robotics, and software). 

Combining formal systems engineering rigor (INCOSE quality linter, ISO 26262 / DO-178C compliance workflows, ReqIF 1.2 exchange) with modern agile planning (Kanban boards, epics, stories, tasks, bugs), `reqtool` stores every requirement, principle, and TBD as an individual, human-readable YAML file inside a Git repository.

---

## 2. Exhaustive Feature Matrix & Technical Capabilities

### 📂 2.1 Git-Backed Data & Storage Engine
- **File-per-Item Store:** Every requirement (`requirements/*.yaml`), principle (`principles/*.yaml`), TBD (`tbds/*.yaml`), module (`modules/`), and product (`products/`) is stored as an individual human-readable YAML 1.2 file.
- **SHA-256 Hashing & Semantic Versioning:** Automatic content hashing and semantic versioning (`1.0.0` → `1.1.0` on content modification; `2.0.0` on major structural changes).
- **Incremental File System Watchdog:** Background Watchdog file system observer reloads modified files in `<10ms` without restarting the server.
- **Native Git Branching & Diffs:** Execute `req diff HEAD~5` or `GET /diff?since=ref` to inspect field-level delta histories across commits, branches, and baseline tags.
- **In-Tool Repository Switcher & Initializer:** Switch active working repositories or initialize new repositories directly inside the UI without restarting.

### 🎯 2.2 Formal Systems Engineering & Agile Planning
- **Unified Artefact Hierarchy:** Supports both formal systems engineering types (*stakeholder_need*, *system_requirement*, *functional*, *performance*, *interface*, *safety*, *compliance*) and agile items (*initiative*, *epic*, *feature*, *user_story*, *task*, *bug*).
- **Safety Criticality Tagging:** ASIL (A/B/C/D) and DAL (A/B/C/D/E) safety classification tagging.
- **Verification Method Allocation:** Allocate verification methods (*Test*, *Demonstration*, *Analysis*, *Inspection*, *Simulation*, *Similarity*).
- **Kanban Board Workstation:** Visual drag-and-drop workflow status transitions with customizable approval guards.
- **Traceability & Dependency Matrix:** Bi-directional parent-child hierarchy, verification links, and impact analysis graph (`GET /traceability/matrix`).

### 🤖 2.3 INCOSE Linter & AI Intelligence
- **INCOSE Prose Quality Linter:** Real-time checking against INCOSE rules (flags passive voice, ambiguous terms like *"suitable"*, *"flexible"*, missing imperatives, unquantified NFR values).
- **AI Semantic Duplicate & Overlap Detector:** `GET /analysis/detect-duplicates` scans all requirements and calculates word token similarity scores to flag overlapping requirements.
- **Spec-to-Test Case Auto Generator:** `POST /analysis/generate-tests/{uid}` automatically generates positive test procedures and acceptance criteria test steps.
- **Acceptance Criteria Generator:** Gherkin Given-When-Then scenario generator (`POST /analysis/generate-ac`).

### 🔒 2.4 Multi-User Server, Authentication & RBAC
- **Multi-Client Server Host (`reqtool-server.exe`):** Multi-client repository hosting listening on `0.0.0.0:8765`.
- **Remote Client Desktop App (`reqtool-client.exe`):** Desktop application workstation equipped with `🔐 Server Login & Connection` UI and dynamic server URL switching (`http://remote-server:8765`).
- **User Authentication:** Password hashing (PBKDF2-HMAC-SHA256) and signed JWT access tokens (`/auth/login`, `/auth/me`, `/auth/users`).
- **Default Admin Seeding:** Auto-seeds default admin credentials (`admin` / `admin123`) in `.reqtool/users.yaml`.
- **Role-Based Access Control (RBAC):** Permission enforcement across user roles (*admin*, *editor*, *reviewer*, *viewer*).

### 🛡️ 2.5 Cryptographic Signatures & Audit Package Exporter
- **Cryptographic Electronic Signatures:** HMAC-SHA256 / Ed25519 digital signature generation on requirement approvals (`SIG-v1-xxxxxxxx...`).
- **21 CFR Part 11 / ISO 26262 Compliance Exporter:** `GET /export/audit-package` packages audit manifests, cryptographic signature ledgers, requirement dumps, and verification logs into a compressed `.zip` dossier.

### 🎨 2.6 Visual Architecture & Diagram Canvas
- **Dual-Engine Diagram Canvas:** Client-side **Mermaid.js** and Server-side **PlantUML** (`POST /render/plantuml` via `plantuml.jar`).
- **Pre-Loaded Templates:** System Hierarchy, Sequence Flow, Component Diagram, Traceability Graph.
- **One-Click Snippet Copy:** Export formatted Markdown code blocks directly into requirement documentation.

### ⏱ 2.7 Flexible Iteration, Sprint & Gate Management
- **Methodology Modes:** Flexible support for **Scrum** (Sprint Backlog & Velocity), **Waterfall** (Phase & Gate Review), **Wagile** (Hybrid Sprint + Gate), and **Kanban** (Continuous Flow).
- **Milestone Gate Tracking:** Track planned, active, completed, and closed status, story point capacity, start/end dates, and milestone CDR gate readiness.
- **Iteration Metrics (`GET /iterations/{id}/metrics`):** Burndown charts and completion percentage.

### ⇌ 2.8 Ecosystem & Webhook Integrations
- **GitHub Webhook Ingestion (`POST /webhooks/github`):** Automatically parses commit messages (`"Fixes REQ-SYS-001"`) and links commits/PRs to requirement verification logs.
- **Outbound Webhooks:** Configurable HTTP webhooks with HMAC-SHA256 signatures triggered on requirement changes and approvals.
- **ReqIF 1.2 XML Exchange:** OMG ReqIF 1.2 XML import and export (`GET /export/reqif`) for IBM DOORS, Jama, and Polarion.
- **OpenAPI 3.1 Spec:** Auto-generated REST API specification (`/openapi.json`).

---

## 3. Standalone Executable Matrix (5 Binary Targets)

| Executable | Output Binary | Port / Binding | Primary Usage |
| :--- | :--- | :--- | :--- |
| **Multi-User Server** | `reqtool-server.exe` | `0.0.0.0:8765` | Central server hosting repository for team networks. |
| **Remote Client App** | `reqtool-client.exe` | Client GUI | Desktop client with remote server login & connection modal. |
| **Web Workstation** | `reqtool-web.exe` | `127.0.0.1:8765` | Workstation auto-launching web browser interface. |
| **Desktop Workstation**| `reqtool-app.exe` | Client GUI | Workstation auto-launching native desktop app window. |
| **CLI Tool** | `reqtool.exe` | CLI | Command-line interface for scripts and CI/CD pipelines. |

---

## 4. Technical Specifications

| Parameter | Specification |
| :--- | :--- |
| **Storage Architecture** | File-per-item Git-backed YAML store (`requirements/*.yaml`, `principles/*.yaml`, `tbds/*.yaml`) |
| **Supported OS** | Windows 10/11 (x64), Linux (Ubuntu/Debian/RHEL x64), macOS (Apple Silicon / Intel) |
| **Deployment Options** | Standalone Executables (`.exe` / binary), Python Wheel, Docker Container, Multi-User Server Host |
| **Backend Engine** | Python 3.12 / FastAPI / Uvicorn / PyInstaller / Watchdog |
| **Frontend Workstation** | React 18 / Vite / CodeMirror 6 / Tailwind CSS / Mermaid.js |
| **Data Formats** | YAML 1.2, JSON, CSV, ReqIF 1.2 XML, Markdown (MkDocs/Hugo), OpenAPI 3.1 |
| **Security** | PBKDF2-HMAC-SHA256 password hashing, HMAC-SHA256 JWT tokens, Ed25519 digital signatures |
