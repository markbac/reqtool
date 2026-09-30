# `reqtool` -- Product Datasheet & Technical Specification

**Version 0.4.0** | **Enterprise Systems Engineering & Agile Requirements Management Engine**

---

## 1. Executive Summary

**`reqtool`** is a high-performance, git-backed requirements engineering workstation and multi-user server designed for complex engineering programmes (aerospace, automotive, medical devices, defense, robotics, and software). 

Combining formal systems engineering rigor (INCOSE quality linter, ISO 26262 / DO-178C compliance workflows, ReqIF 1.2 exchange) with modern agile planning (Kanban boards, epics, stories, tasks, bugs), `reqtool` stores every requirement, principle, and TBD as an individual, human-readable YAML file inside a Git repository.

Unlike legacy database-bound tools (IBM DOORS, Jama, Polarion), `reqtool` provides 100% version-controlled transparency, offline-first standalone executables, instant diffing across Git branches, real-time collaboration, and zero database administration.

---

## 2. Technical Datasheet & Specifications

### 2.1 System Specifications

| Feature | Specification |
| :--- | :--- |
| **Storage Architecture** | File-per-item Git-backed YAML store (`requirements/*.yaml`, `principles/*.yaml`, `tbds/*.yaml`) |
| **Supported Operating Systems** | Windows 10/11 (x64), Linux (Ubuntu/Debian/RHEL x64), macOS (Apple Silicon / Intel) |
| **Deployment Options** | Standalone Executables (`.exe` / binary), Python Wheel, Docker Container, Multi-User Server Host |
| **Backend Engine** | Python 3.12 / FastAPI / Uvicorn / PyInstaller / Watchdog |
| **Frontend Workstation** | React 18 / Vite / CodeMirror 6 / Tailwind CSS / Mermaid.js |
| **Data Formats** | YAML 1.2, JSON, CSV, ReqIF 1.2 XML, Markdown (MkDocs/Hugo), OpenAPI 3.1 |
| **Authentication & Security** | PBKDF2-HMAC-SHA256 password hashing, HMAC-SHA256 JWT tokens, Ed25519 digital signatures |
| **Network Interfaces** | REST API (HTTP 8765), WebSockets (`ws://host:8765/ws`), OpenAPI 3.1 spec |

---

## 3. Product Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       reqtool Ecosystem Architecture                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         ▼                             ▼                             ▼
┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│ reqtool-server   │         │ reqtool-client   │         │ reqtool-web      │
│ Central Host     │◄───────►│ Desktop Client   │         │ Browser SPA      │
│ (0.0.0.0:8765)   │   JWT   │ Standalone App   │         │ Workstation      │
└────────┬─────────┘         └──────────────────┘         └──────────────────┘
         │
         ├──► Authentication & RBAC Engine (PBKDF2 / JWT)
         ├──► Cryptographic Signature Verification (Ed25519)
         ├──► Real-Time WebSocket Presence & Locking (/ws)
         ├──► INCOSE Prose Linter & Validation Engine
         └──► In-Memory Dependency Graph & Impact Index
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Git-Backed Repository (.reqtool / YAML)                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Key Capabilities & Feature Matrix

### 4.1 Requirements & Agile Management
- **Dual Systems & Agile Support:** Unified management of formal engineering requirements (*functional*, *performance*, *interface*, *safety*, *compliance*) alongside agile items (*initiative*, *epic*, *feature*, *story*, *task*, *bug*).
- **INCOSE Prose Quality Linter:** Real-time checking against INCOSE rules (flags passive voice, ambiguous terms like *"suitable"*, *"flexible"*, missing imperatives, unquantified NFR values).
- **Traceability & Dependency Matrix:** Bi-directional parent-child hierarchy, verification links, and impact analysis graph.
- **Kanban Board Workstation:** Visual drag-and-drop workflow status transitions with customizable approval guards.

### 4.2 Multi-User Collaboration & Security
- **Central Server Host (`reqtool-server.exe`):** Multi-client repository hosting listening on `0.0.0.0:8765`.
- **JWT & Role-Based Access Control:** User authentication with JWT Bearer tokens and role enforcement (*admin*, *editor*, *reviewer*, *viewer*).
- **Real-Time Presence & Edit Locking:** Live WebSocket connection broadcasting active user presence and preventing edit collisions.
- **Cryptographic Signatures:** Ed25519 cryptographic digital signing of requirement approvals for audit trails.

### 4.3 Visual Modeling & Diagramming
- **Embedded Mermaid Diagram Canvas:** Live diagram editor rendering sequence diagrams, flowcharts, and architecture models linked directly to requirement UIDs.

---

## 5. Standalone Executables & Binary Matrix

| Executable Target | Output Binary Name | Default Port / Binding | Primary Usage |
| :--- | :--- | :--- | :--- |
| **Multi-User Server** | `reqtool-server.exe` | `0.0.0.0:8765` | Central server hosting repository for team networks. |
| **Remote Client App** | `reqtool-client.exe` | Client GUI | Desktop client with remote server login & connection modal. |
| **Web Workstation** | `reqtool-web.exe` | `127.0.0.1:8765` | Workstation auto-launching web browser interface. |
| **Desktop Workstation**| `reqtool-app.exe` | Client GUI | Workstation auto-launching native desktop app window. |
| **CLI Tool** | `reqtool.exe` | CLI | Command-line interface for scripts and CI/CD pipelines. |

---

## 6. Supported Standards & Compliance

- **INCOSE:** INCOSE Guide for Writing Requirements (prose quality linter).
- **ISO 26262 / DO-178C:** Safety-critical classification (`safety_class`, ASIL/DAL tagging, verification methods).
- **ReqIF 1.2:** Requirement Interchange Format XML import/export.
- **OpenAPI 3.1:** Auto-generated REST API specification (`/openapi.json`).
- **Git:** Native Git integration (commits, branch diffing, tags, baselines).
