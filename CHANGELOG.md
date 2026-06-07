# Changelog

All notable changes to reqtool. Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.8] -- 2025-06-07

### Changed

- **Task Mgmt sidebar replaced flat list with a Kanban board**: columns are workflow states
  (backlog / ready / in_progress / in_review / done), cards grouped by swimlane (By Person,
  By Team, or All). Type filter, iteration filter, and person filter in the toolbar.
  Uses `GET /kanban` endpoint.

- **Modules moved into Requirements section**: Modules is now the 4th sub-tab under
  Requirements (Reqs | Principles | TBDs | Modules), not a separate top-level section.
  Top-level nav is now just two sections: Requirements and Task Mgmt.

### Fixed

- `dev.ps1 install` npm path error resolved definitively with `Start-Process -WorkingDirectory`.


## [0.3.7] -- 2025-06-07

### Fixed

- **`dev.ps1 install` npm path error (final fix)**: replaced `Set-Location` / `Push-Location`
  with `Start-Process -WorkingDirectory $uiDir`. `Start-Process` sets the Win32 working directory
  for the child process directly at the OS level -- the only approach that is immune to
  PowerShell's internal vs process-level directory distinction. Added explicit `Test-Path` guard
  and Node.js version diagnostic on failure.

### Added

- **Task Management section** in the sidebar: type-filter bar (theme/initiative/epic/feature/
  story/task/bug/spike) with status and iteration filters, assignee/iteration/priority pills on
  each card, and inline create.
- **Modules section** in the sidebar: lists all modules in the `modules/` directory independent
  of any product; selecting a module shows its requirements inline.
- **Three-level sidebar navigation**: Requirements (Reqs / Principles / TBDs sub-tabs),
  Task Mgmt, Modules -- replaces the flat three-tab layout.
- Type icons and accent colours on all tree nodes (🎯 theme, 🚀 initiative, 📦 epic, ✨ feature,
  📖 story, ✅ task, 🐛 bug, 🔬 spike, ⚙️ functional, ⚠️ safety, etc.).
- `api.kanban`, `api.modules`, `api.hierarchy` added to `api.js`.

## [0.3.6] -- 2025-06-07

### Fixed

- **`dev.ps1 install` npm still resolves to `scripts\package.json`**: `Push-Location` only
  updates PowerShell's internal location stack. Child processes spawned with `& npm` inherit
  `[System.Environment]::CurrentDirectory`, which `Push-Location` does **not** update.
  `Set-Location` updates both, so npm now correctly inherits `src\reqtool\ui` as its working
  directory. The fix saves the current directory before changing it and restores it
  unconditionally after npm exits, so the caller's directory is never permanently changed.

## [0.3.5] -- 2025-06-07

### Fixed

- **`dev.ps1` resolves `$RepoDir` from `$PSScriptRoot`** instead of
  `$MyInvocation.MyCommand.Path`. `$MyInvocation.MyCommand.Path` is `$null` when a script is
  invoked with `.\scripts\dev.ps1` from a different working directory, which caused `$ScriptDir`
  to be empty and `$RepoDir` to collapse to the current directory (`scripts\`). npm then looked
  for `scripts\package.json` instead of `src\reqtool\ui\package.json`. `$PSScriptRoot` is an
  automatic variable that is always set to the directory of the running script file, regardless
  of working directory or invocation style.
- Path diagnostic lines added to `install` output so repository root and UI directory are
  visible on every run, making future path issues immediately obvious.

## [0.3.4] -- 2025-06-07

### Fixed

- **`npm install failed` on Windows**: `npm --prefix <path>` resolves the prefix relative to the
  current working directory when called from PowerShell. Running the script from `scripts\` made
  npm look for `scripts\package.json` rather than `src\reqtool\ui\package.json`. Both `dev.ps1`
  and `dev.sh` now `Push-Location`/`cd` into the UI directory before calling npm, then restore
  the original directory.

- **Stale `{.github` brace-expansion directory removed from zip**: an earlier `mkdir` command
  used shell brace expansion which wasn't interpreted on the build system, creating a literal
  directory named `{.github` in the repository root. It served no purpose and has been deleted.

## [0.3.3] -- 2025-06-07

### Fixed

- **Root cause of `Cannot read properties of null (reading 'useContext')`**: a duplicated
  function body in `Header.jsx` left hooks (`useApp`, `useState`, `useEffect`, `useCallback`)
  at module scope between two component definitions. React validates that hooks are only called
  inside component bodies; calling them at module evaluation time produces exactly this error.
  The duplicate block (lines 229--276) was removed. `onCustomFields`, `onWebhooks`, and
  `onToggleSidebar` were added to the Header props destructuring, where they were previously
  only declared in the now-removed duplicate.

- **`@uiw/react-codemirror` lazy loaded**: changed from a static import to `React.lazy()` +
  `<Suspense>`. This removes the package from the synchronous module graph, so it can never
  bring a second React copy into scope at parse time regardless of npm's deduplication
  behaviour. The `<textarea>` fallback is shown during the lazy load (imperceptible in practice).

- **Vite config `resolve.dedupe` and `resolve.alias`**: pin all `react`, `react-dom`, and
  `react/jsx-runtime` imports to absolute paths in the project's own `node_modules`, for both
  the production build and the Vitest test environment.

### Added

- **UI test suite** (`src/test/ui.test.jsx`, `src/test/components.test.jsx`): 34 tests covering
  AppContext state machine, React deduplication invariants, and component smoke renders for
  Header, Sidebar, Editor, and App. Run with `npm test` from `src/reqtool/ui/`.
- `vitest@^4.1.8`, `@testing-library/react`, `@testing-library/dom`, `@testing-library/jest-dom`,
  `jsdom` added as dev dependencies.
- CI `ui-build` job now runs `npm test` after `npm run build`.

## [0.3.2] -- 2025-06-07

### Fixed

- **`npm ci` peer dependency conflict** on Windows (and any npm version that resolves `@eslint/js@10`
  against `eslint@9`): removed all ESLint dev dependencies from `package.json`. ESLint is only
  needed for authoring the UI source -- it is not required to build or run the app. The build
  toolchain is now just `vite` + `@vitejs/plugin-react`, which have no peer conflicts.
- `npm install --legacy-peer-deps` used in both dev scripts and CI as a belt-and-braces guard
  against future transitive peer dep mismatches.
- Python 3.14 added to CI test matrix.

## [0.3.1] -- 2025-06-07

### Fixed

- **React duplicate context crash** (`Cannot read properties of null (reading 'useContext')`): pinned
  React to 18.3.1 and added `overrides` in `package.json` to force a single copy of `react` and
  `react-dom` across all dependencies. `@uiw/react-codemirror` v4.25 declares `>=17.0.0` as a peer
  dependency, which caused npm on Windows to install a separate nested React copy, breaking context
  across the module boundary.
- Downgraded `@vitejs/plugin-react` to v4 (React 18-compatible) and `vite` to v6 to match.
- **`req serve` landing page** now shows `"not built"` correctly before the UI dist is present.
- **`req init defaults`** now copies `hierarchy.yaml` and writes `estimate_unit` / `relationship_types`
  to `enums.yaml`, giving the full agile + systems type system on first use.
- **`req serve` banner** now prints version, repo stats, URLs, and UI build status before handing
  off to uvicorn.

### Changed

- Version bump policy: every released zip increments the version.

## [0.3.0] -- 2025-06-07

### Added

**Type system and hierarchy**

- Nine new item types: `theme`, `initiative`, `epic`, `feature`, `story`, `task`, `bug`, `spike`, `stakeholder_need`.
- `hierarchy.yaml` is now the single source of truth for types, hierarchy rules, per-type workflows, DoR/DoD templates, and cross-layer relationship rules. Loaded from `.reqtool/hierarchy.yaml` in the repo, falling back to the bundled default.
- `HierarchyConfig`, `ItemTypeConfig`, `HierarchyRule`, `HierarchyWorkflowDef`, `WorkflowGuard`, `CrossLayerRule`, and `RelationshipTypeDef` models wired into `Store` and consumed by the API.
- Per-type workflow definitions: `lightweight` (theme/initiative), `sprint` (epic/feature/story/task/bug/spike), `formal` (functional/performance/interface etc.), `safety_formal` (safety requirements). New requirements receive the workflow's `initial` state as their default status.
- Workflow guards enforced at transition time: configurable pre-conditions (required fields, required ACs) block invalid transitions with a `409 workflow_guard` error. Guards are defined per target state in `hierarchy.yaml`.
- `POST /requirements/{uid}/transition` -- explicit workflow transition endpoint with guard enforcement.
- `PUT /requirements/{uid}` now also enforces guards when the `status` field changes.

**New fields on requirements**

- `assignee` -- the person doing the work, distinct from `owner` (accountable person).
- `iteration` -- named iteration reference (sprint name, PI, milestone); plain string.
- `estimate` -- numeric effort estimate (units configured repo-wide via `estimate_unit` in `enums.yaml`).
- `estimate_unit` -- per-item override for the estimate unit label.
- `dor_checklist` -- Definition of Ready; list of `{item, checked}` pairs, populated from `hierarchy.yaml` defaults on creation.
- `dod_checklist` -- Definition of Done; same structure, separate list.
- `estimate_unit` added to `RepoEnums` (default `"points"`).
- `relationship_types` list added to `RepoEnums` for project-specific relationship type extensions.

**New API endpoints**

- `GET /requirements/{uid}/impact` -- transitive downstream impact closure (derived_from, depends_on, implements, satisfies), grouped by type, with upstream chain.
- `GET /requirements/{uid}/rollup` -- computed estimate rollup (sum of direct children's estimates).
- `GET /kanban` -- column-per-state kanban board; filters: `req_type`, `iteration`, `owner`, `assignee`; uses per-type workflow states.
- `GET /ws` (WebSocket) -- real-time event stream; broadcasts created, updated, deleted, status_changed, comment_added, attachment_added events.
- `GET /badge/validated` -- Shields.io-compatible SVG badge for CI integration.
- `GET /help` -- contextual help content from `defaults/help.yaml` or `.reqtool/help.yaml`; `?topic=<key>` for a specific section.
- `GET /hierarchy` -- full hierarchy configuration (types, workflows, rules, DoR/DoD templates).
- `GET /hierarchy/types` -- list of configured item types with metadata.
- `GET /hierarchy/children/{req_type}` -- allowed child types for a given parent type.
- `GET /filter-presets`, `PUT /filter-presets/{id}`, `DELETE /filter-presets/{id}` -- named, persisted filter presets stored in `.reqtool/filter_presets.yaml`.

**CLI**

- `req init agile` -- scaffolds a repository with agile workflow, type vocabulary, DoR/DoD defaults, sprint states, and `estimate_unit: points`.
- `req init systems` -- scaffolds a repository with systems engineering defaults, formal/safety-formal workflows, and `estimate_unit: days`.
- `req new-agile story|task|bug|spike|epic|feature|theme|initiative` -- interactive agile item creation with auto-increment IDs.

**ID auto-increment**

- `store.next_id_for_type(req_type)` computes the next ID for a type using the configured prefix (e.g. `US-042` for story, `SAF-007` for safety). Used automatically on creation when no `id` is supplied.

**Default files**

- `defaults/hierarchy.yaml` -- full type system, workflow definitions, DoR/DoD templates, cross-layer rules, and relationship type registry.
- `defaults/help.yaml` -- contextual help content for all concepts, fields, workflows, relationships, estimates, DoR/DoD, validation rules, git/baselines, and export.

**Tests**

- `tests/test_features_v03.py` -- 101 new tests covering all v0.3.0 features.

### Fixed

- `store.compute_affected_requirements` body was missing after a prior refactor (stray docstring left an empty function).
- Default requirement status now uses the workflow's `initial` state rather than hardcoded `"draft"`, ensuring sprint-workflow types start at `backlog`.

### Changed

- `CoreEnums.relationship_type` updated to the full named set: `relates_to`, `depends_on`, `depended_by`, `satisfies`, `implements`, `traces_to`, `derived_from`, `conflicts_with`, `supersedes`.
- `RepoEnums` gains `estimate_unit` (default `"points"`) and `relationship_types` (extends core).
- `websockets>=12.0` added as a runtime dependency.


## [0.1.0] -- 2026-06-02

Initial release.

### Added

**Core**
- YAML-as-source-of-truth artefact schema: requirements, principles, TBDs, modules, products
- UUIDv7 identifiers; SHA-256 content hash over canonical JSON of content-bearing fields
- Semantic versioning per artefact: patch/minor/major increment on commit
- In-file history (cap 20 entries) with commit SHA written back after git commit
- Git integration: stage, commit, amend, log, conflict detection
- Watchdog file watcher: in-memory store reloads on external YAML changes
- Module system: reusable requirement sets with lock files and field overrides
- Product manifests with module references, variant definitions, root ordering

**API** (`src/reqtool/api.py`)
- 57-route FastAPI application generating OpenAPI 3.1 at `/openapi.json`
- All request/response bodies typed with Pydantic v2 models (no `dict[str, Any]` endpoints)
- Requirements: CRUD, tree, bulk update, clone, commit, approve, relationships, AC management
- Principles and TBDs: CRUD, commit, resolve
- Modules: import (writes lock), verify (checks lock vs current files)
- Products: list, get, tree, allocation matrix
- Validation: full suite and single-artefact
- Export: CSV, Markdown (ZIP), JSX viewer
- Git: status, batch commit, log
- Meta: `/version`, `/config`, `/search`, `/enums`

**Validation** (`src/reqtool/validation.py`)
- 11 error codes and 11 warning codes per spec §13.1
- Full enum validation for all status, priority, type, and relationship fields
- Content hash verification; broken UID reference detection
- Module lock file and content hash checks
- NFR unknown key warning; open TBD on approved requirement warning
- `validate_single` for inline validation after save

**Exports** (`src/reqtool/exports.py`)
- CSV: configurable field list, acceptance criteria as numbered cell, relationships as `type:uid8`
- Markdown: split by domain/product/none; mkdocs nav fragment; relationship cross-links; full metadata
- JSX: self-contained viewer component

**CLI** (`src/reqtool/cli.py`)
- `req init` -- scaffold config, enums, directory structure, .gitignore
- `req serve` -- uvicorn server with optional hot reload
- `req validate` / `req verify` -- CI-friendly, exit 1 on failures
- `req new requirement|principle|tbd` -- interactive creation
- `req show` / `req history` -- artefact inspection
- `req export csv|markdown|jsx`
- `req import <module-id>` -- write lock files
- `req version` -- print tool version
- `req openapi` -- export OpenAPI spec to YAML or JSON

**UI** (`src/reqtool/ui/`)
- Industrial dark theme; IBM Plex Mono + IBM Plex Sans
- Sidebar: requirements tree with search filter, keyboard navigation, right-click context menu (add/clone/delete/history), principles list, TBDs list
- Editor: all §10.4 field sections; CodeMirror 6 markdown with preview; reparent picker; breadcrumb; Ctrl+S; inline validation after save; per-AC links editor
- Header: live search, git status polling (10s), clickable staged badge → global commit modal, Validate / Coverage / Bulk / Export actions
- Coverage dashboard: status breakdown, quality gaps, priority distribution
- Bulk update panel: multi-select requirements, set status/priority/owner
- Validation panel, Export panel (CSV field editor, Markdown split-by)

---

## Versioning policy

`MAJOR` -- breaking change to the YAML schema (`schema_version` bump) or API contract.\
`MINOR` -- new endpoints, new fields (backwards compatible), new UI features.\
`PATCH` -- bug fixes, validation rule additions, documentation.

The `schema_version` field in each YAML file (`1.0.0`) is independent of the tool version. A tool version bump does not necessarily mean a schema version bump.

To bump the version:
1. Update `__version__` in `src/reqtool/__init__.py`
2. Update `version` in `pyproject.toml` (must match)
3. Add a section to `CHANGELOG.md`
4. Tag the commit: `git tag v0.2.0 && git push --tags`
