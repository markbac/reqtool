# reqtool -- Architecture and Technical Reference

**Version 0.3.0**

---

## 1. Purpose and scope

reqtool is a git-backed YAML requirements management tool for engineering programmes. It handles both formal systems engineering artefacts (stakeholder needs, functional/safety/compliance requirements) and agile planning items (themes, epics, stories, tasks) in a single unified store.

The fundamental premise is that requirements are source artefacts, not database rows. Every requirement, principle, and TBD lives as an individual YAML file in a git repository. The tool layers hashing, semantic versioning, workflow enforcement, validation, and export on top of that file store without hiding the files from the engineer.

This document covers:

- Overall system architecture and component boundaries
- Data model and YAML schema
- Type system and hierarchy
- Workflow engine and guard mechanics
- Store internals and the in-memory graph
- API surface and request lifecycle
- Validation rules
- Export engine
- Git integration
- Configuration reference

---

## 2. System architecture

### 2.1 Component overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        reqtool process                          │
│                                                                 │
│  ┌──────────┐   ┌─────────────────────────────────────────┐    │
│  │   CLI    │   │            FastAPI application           │    │
│  │ (Click)  │   │                                         │    │
│  │          │   │  ┌────────────┐  ┌────────────────────┐ │    │
│  │req serve │──▶│  │  REST API  │  │  WebSocket (/ws)   │ │    │
│  │req init  │   │  │ endpoints  │  │  ConnectionManager │ │    │
│  │req new   │   │  └─────┬──────┘  └────────┬───────────┘ │    │
│  │req valid │   │        │                  │             │    │
│  │req verify│   │  ┌─────▼──────────────────▼───────────┐ │    │
│  └──────────┘   │  │              Store                  │ │    │
│                 │  │  in-memory graph of all artefacts   │ │    │
│                 │  │  hierarchy config  ·  filter prefs  │ │    │
│                 │  └──────┬────────────────────────────┬─┘ │    │
│                 │         │                            │    │    │
│                 │  ┌──────▼──────┐  ┌─────────────────▼─┐ │    │
│                 │  │   fileio    │  │    validation /    │ │    │
│                 │  │  YAML I/O   │  │    exports /       │ │    │
│                 │  │  hashing    │  │    git_ops         │ │    │
│                 │  │  uuid7      │  └───────────────────┘ │    │
│                 │  └──────┬──────┘                        │    │
│                 └─────────┼────────────────────────────────┘    │
└───────────────────────────┼─────────────────────────────────────┘
                            │ read / write
        ┌───────────────────▼────────────────────┐
        │          Requirements repository        │
        │  (a plain git repository on disk)       │
        │                                         │
        │  .reqtool/                              │
        │    config.yaml  enums.yaml              │
        │    hierarchy.yaml  help.yaml            │
        │    templates.yaml  filter_presets.yaml  │
        │                                         │
        │  requirements/<uid>.yaml  (one per req) │
        │  principles/<uid>.yaml                  │
        │  tbds/<uid>.yaml                        │
        │  modules/<id>/_module.yaml + reqs       │
        │  products/<id>/_product.yaml + .lock    │
        │  comments/<uid>.yaml                    │
        │  attachments/<uid>/<filename>           │
        └─────────────────────────────────────────┘
```

### 2.2 Module dependency graph

```
cli.py
 └── store.py ──── fileio.py
 └── api.py ─────── store.py
                └── validation.py ─── fileio.py
                └── exports.py ─────── store.py
                └── git_ops.py
 └── validation.py
 └── exports.py

models.py  (no imports from reqtool -- pure Pydantic)
main.py    (thin ASGI factory -- imports api.py only)
```

All reqtool modules depend on `models.py` for type definitions. `models.py` itself has no internal dependencies, only Pydantic and the standard library. This makes models safe to import anywhere without triggering side effects.

### 2.3 Process startup

```
req serve
    │
    ▼
cli.py::serve()
    │  sets REQTOOL_REPO env var
    │
    ▼
uvicorn.run("reqtool.main:app_factory", factory=True)
    │
    ▼
main.py::app_factory()
    │  reads REQTOOL_REPO
    │
    ▼
api.py::create_app(repo_root: Path)
    │
    ├── Store(repo_root).load()          reads all YAML from disk
    │       ├── _load_config()
    │       ├── _load_enums()
    │       ├── _load_hierarchy()        loads hierarchy.yaml
    │       ├── _load_dir(requirements)
    │       ├── _load_dir(principles)
    │       ├── _load_dir(tbds)
    │       ├── _load_modules()
    │       └── _load_products()
    │
    ├── watchdog.Observer.start()        file system watcher for hot reload
    │
    └── FastAPI app returned to uvicorn
```

---

## 3. Data model

### 3.1 Artefact types

reqtool has three first-class artefact kinds: **requirements**, **principles**, and **TBDs**. All share the same structural pattern: a UID, a human-readable ID, a semantic version, a content hash, and a history list.

```
Artefact (shared structure)
├── schema_version     "1.0.0"
├── type               "requirement" | "principle" | "tbd"
├── tool_version       "0.3.0"
├── uid                UUIDv7 string  -- immutable primary key
├── id                 human-readable  e.g. "US-042", "FR-007"
├── title              one-line summary
├── version            semver  e.g. "1.4.2"
├── content_hash       "sha256:<hex>"  over hashed fields only
├── created            ISO 8601
├── last_modified      ISO 8601
├── deleted            bool  (soft delete)
└── history[]          [{version, date, modified_by, summary, commit_sha}]
```

### 3.2 Requirement schema

```
Requirement (extends Artefact)
├── parentId           UID of parent requirement (or null for roots)
├── req_type           one of the configured item types (see §4)
├── content
│   ├── description            the "shall" statement
│   ├── rationale              why this requirement exists
│   └── extended_description   additional context
├── acceptance_criteria[]      [{uid, id, text, links[]}]
├── status             workflow state (initial value from workflow.initial)
├── priority           critical | high | medium | low
├── domain             from enums.yaml domain list
├── owner              accountable person
├── assignee           person doing the work
├── iteration          sprint name, PI, or milestone
├── estimate           float (units: enums.yaml estimate_unit)
├── estimate_unit      per-item override
├── dor_checklist[]    [{item, checked}]  Definition of Ready
├── dod_checklist[]    [{item, checked}]  Definition of Done
├── tags[]
├── allocated_to[]     team names
├── relationships[]    [{type, target: {uid}}]
├── links[]            [{system, type, ref, title}]
├── attachments[]      [{filename, size_bytes, sha256, added_by, added_at}]
├── attributes{}       free-form key-value
├── custom_fields{}    validated against .reqtool/custom_fields.yaml
├── nfr{}              key -> float  e.g. {latency_ms: 100}
├── constraints[]
├── assumptions[]
├── risk               critical | high | medium | low | none
├── safety_related     bool
├── safety_classification  e.g. "SIL-2"
├── verification_method    test | analysis | inspection | demonstration
├── verification       {status, verified_date, note}
├── approval           {status, approved_by, approved_date}
├── review             {last_reviewed, reviewers[], note}
└── implementation     {status, branch}
```

### 3.3 Content hash

The hash covers only the semantically meaningful fields -- it excludes `version`, `last_modified`, `history`, `created`, `content_hash` itself, and operational blocks (`approval`, `review`, `verification`, `implementation`). This means administrative updates (changing a reviewer, recording a verification date) do not bump the version.

Hashed fields for requirements: `id`, `title`, `parentId`, `content`, `acceptance_criteria`, `req_type`, `domain`, `discipline`, `feature`, `component`, `status`, `priority`, `risk`, `owner`, `allocated_to`, `tags`, `safety_related`, `safety_classification`, `verification_method`, `relationships`, `links`, `attachments`, `constraints`, `assumptions`, `nfr`, `attributes`, `custom_fields`.

Hash computation:

```python
subset = {k: data[k] for k in HASHED_FIELDS if k in data}
canonical = json.dumps(canonical_sort(subset), separators=(",", ":"))
digest = hashlib.sha256(canonical.encode()).hexdigest()
return f"sha256:{digest}"
```

All keys are recursively sorted before serialisation so field ordering in memory never affects the hash.

### 3.4 UUIDv7

All UIDs are UUIDv7 strings. UUIDv7 embeds a 48-bit millisecond timestamp in the high bits, which means UIDs sort chronologically. This makes them suitable as file names and as primary keys in ordered collections without a separate created-at index.

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
├─────────────────────────────────────────────────────────────────┤
│                   unix_ts_ms (48 bits)                          │
├─────┬───────────────────────────────────────────────────────────┤
│0111 │         rand_a (12 bits)                                  │  ver=7
├──┬──┴─────────────────────────────────────────────────────────  ┤
│10│                rand_b (62 bits)                              │  var=2
└──┴─────────────────────────────────────────────────────────────┘
```

---

## 4. Type system and hierarchy

### 4.1 Type vocabulary

All item types are defined in `hierarchy.yaml` (bundled default at `src/reqtool/defaults/hierarchy.yaml`, overridable at `.reqtool/hierarchy.yaml`).

```
Agile planning (top-down):

  theme ──────────────────────────────  TH-NNN  lightweight workflow
    └── initiative ──────────────────  IN-NNN  lightweight workflow
          └── epic ─────────────────  EP-NNN  sprint workflow
                └── feature ─────────  FT-NNN  sprint workflow
                      └── story ──────  US-NNN  sprint workflow
                            ├── task ──  TK-NNN  sprint workflow
                            └── bug ───  BG-NNN  sprint workflow
                      └── spike ───────  SP-NNN  sprint workflow

Systems engineering (top-down):

  stakeholder_need ──────────────────  SN-NNN  lightweight workflow
    └── functional ──────────────────  FR-NNN  formal workflow
    └── performance ─────────────────  PR-NNN  formal workflow
    └── security ────────────────────  SR-NNN  formal workflow
    └── safety ──────────────────────  SAF-NNN safety_formal workflow
    └── interface ───────────────────  IR-NNN  formal workflow
    └── compliance ──────────────────  CR-NNN  formal workflow
    └── constraint ──────────────────  CON-NNN formal workflow
    └── operational ─────────────────  OR-NNN  formal workflow
    └── physical ────────────────────  PHR-NNN formal workflow
```

Cross-layer: agile items link to systems requirements via explicit relationship types (`satisfies`, `implements`, `traces_to`), never via `parentId`.

### 4.2 Hierarchy enforcement

Parent/child relationships are validated against `hierarchy.yaml`. The `hierarchy.hierarchy` map defines `allowed_children` per parent type:

```yaml
epic:
  allowed_children: [feature, story, task, bug, spike]
story:
  allowed_children: [task, bug]
task:
  allowed_children: []
```

Violations produce a validation warning (not a hard error) to avoid blocking data migration.

### 4.3 ID auto-increment

When creating a requirement without an explicit `id`, `store.next_id_for_type(req_type)` scans all existing IDs with the matching prefix and returns the next in sequence:

```
US-001, US-002, US-003 → next US-004
```

The prefix is taken from the type's `id_prefix` in `hierarchy.yaml`. If no matching IDs exist, the sequence starts at `001`.

---

## 5. Workflow engine

### 5.1 Workflow definitions

Four workflow templates ship in `hierarchy.yaml`. Each maps states and transitions.

```
lightweight          sprint              formal              safety_formal
──────────           ──────              ──────              ─────────────
draft                backlog             draft               draft
  │                    │                  │                    │
  ▼                    ▼                  ▼                    ▼
active               ready             in_review           in_review
  │                    │                  │                    │
  ▼                  in_progress          ▼                    ▼
done ◀──────────       │               reviewed            reviewed
  │              in_review               │                    │
cancelled             │               approved ◀─────    approved ◀─ (guarded)
                     done                │                    │
                  cancelled          deprecated          deprecated

Legend: ◀─── = can transition back
```

Terminal states are `done`, `cancelled`, `deprecated`. No transitions out.

### 5.2 Guard mechanics

Guards are pre-conditions on entering a target state. They are defined per workflow, per target state:

```yaml
workflows:
  safety_formal:
    guards:
      approved:
        requires_fields: [content.description, content.rationale, safety_classification]
        requires_ac: true
        message: "Safety requirements must have description, rationale, ACs, and safety_classification."
```

`requires_fields` is a list of dotted field paths. Each is resolved recursively against the requirement dict. A field fails the check if it is `None`, an empty string, or an empty list.

Guard evaluation:

```
store.validate_transition(req, to_state)
    │
    ├── lookup workflow for req.req_type
    │
    ├── check to_state is in transitions[req.status]
    │   └── if not: return "Transition from X to Y not permitted"
    │
    └── check_transition_guard(req, to_state)
            │
            ├── for each field in guard.requires_fields:
            │     resolve dotted path → fail if empty/None
            │
            └── if guard.requires_ac: fail if acceptance_criteria is empty
```

Guards are enforced on:
- `POST /requirements/{uid}/transition` -- explicit transition
- `PUT /requirements/{uid}` -- when `status` field changes

### 5.3 Default status on creation

New requirements get `status` set to the `initial` field of their workflow, not a hardcoded `"draft"`. Sprint-workflow types start at `backlog`; formal types start at `draft`.

---

## 6. Store internals

### 6.1 In-memory graph

`Store` holds all artefacts as plain dicts in memory. Every mutation writes through to YAML on disk immediately. There is no write-behind cache.

```python
Store.requirements: dict[uid, dict]
Store.principles:   dict[uid, dict]
Store.tbds:         dict[uid, dict]
Store.modules:      dict[module_id, dict]
Store.products:     dict[product_id, dict]
Store.module_requirements: dict[module_id, dict[uid, dict]]
```

The store is loaded once at startup (`Store.load()`). A `watchdog` file system observer monitors the `requirements/`, `principles/`, `tbds/`, `modules/`, `products/`, and `.reqtool/` directories. When a YAML file changes on disk (e.g. via external `git pull`), `store.reload_file(path)` is called. This skips re-loading if the in-memory `last_modified` is already at or newer than the file's value, avoiding a read-after-write race between the store's own saves and the watcher.

Config and enum changes trigger a full reload. Artefact changes trigger incremental reload of just the affected file.

### 6.2 Write path

All mutations follow this sequence:

```
1. sanitise input (_sanitise_requirement strips _display, fixes ephemeral AC UIDs)
2. apply field updates (deep merge for content/approval/review/verification/implementation)
3. recompute content hash
4. if hash changed: bump semver by requested increment (patch/minor/major)
5. append history entry {version, date, author, summary}
6. trim history to 20 entries
7. save_yaml(path, data)
8. update in-memory dict
```

Git staging and committing are separate explicit steps, either via `POST /requirements/{uid}/commit` or `POST /git/commit` (batch). The store does not auto-commit.

### 6.3 Impact analysis

`store.compute_impact(uid)` performs a BFS over the reverse relationship index:

```
Build index: target_uid → [{source_uid, rel_type, ...}]

BFS from uid following IMPACT_REL_TYPES:
    = {derived_from, depends_on, implements, satisfies}

Result:
    downstream: all transitively reachable items (grouped by req_type)
    upstream:   direct targets of uid's own IMPACT_REL_TYPES relationships
```

### 6.4 Estimate rollup

`store.compute_estimate_rollup(uid)` sums the `estimate` field of all direct children (items where `parentId == uid`). It returns `None` if there are no children or none of them have estimates. It is not stored -- it is computed on demand at `GET /requirements/{uid}/rollup`.

---

## 7. API surface

### 7.1 Architecture

The API is a standard FastAPI application. All routes are registered inside `create_app(repo_root)` as closures over the `store` instance, which is created once per server process. There is no dependency injection framework -- the store is captured by the closure.

```
create_app(repo_root: Path) -> FastAPI
    │
    ├── store = Store(repo_root); store.load()
    ├── watchdog observer started
    ├── ConnectionManager (WebSocket) instantiated
    │
    ├── @app.get("/requirements") ...        all routes registered here
    ├── @app.post("/requirements") ...
    ├── ...
    │
    └── StaticFiles("/", ui/dist/)           React UI served last (catch-all)
```

### 7.2 Request lifecycle

```
HTTP request
    │
    ▼
FastAPI routing
    │
    ▼
Endpoint function (closure over store)
    │
    ├── check has_conflicts(repo_root)    409 if merge conflicts
    ├── fetch artefact from store
    ├── validate input (Pydantic model)
    ├── call store method (create/update/delete)
    │       └── write YAML to disk
    ├── fire webhooks (async thread)
    ├── broadcast WebSocket event (async task)
    └── return JSON response
```

### 7.3 Endpoint groups

| Group | Prefix | Key endpoints |
|-------|--------|---------------|
| Requirements | `/requirements` | CRUD, bulk, clone, approve, commit, transition, impact, rollup, history, relationships, ACs |
| Hierarchy | `/hierarchy` | config, types, allowed children |
| Kanban | `/kanban` | column-per-state board with filters |
| Principles | `/principles` | CRUD, commit |
| TBDs | `/tbds` | CRUD, commit, resolve |
| Modules | `/modules` | list, get, import, verify |
| Products | `/products` | CRUD, tree, matrix |
| Attachments | `/artefacts/{uid}/attachments` | upload, download, delete |
| Comments | `/artefacts/{uid}/comments` | add, update, resolve, delete |
| Exports | `/export` | csv, markdown (zip), jsx |
| Validation | `/validate` | full suite, single artefact |
| Git | `/git` | status, commit, log |
| Baselines | `/baselines` | list, create (tag), diff |
| Filter presets | `/filter-presets` | save, list, delete |
| Enums | `/enums` | merged, core, repo, update |
| Workflow | `/workflow` | get, update |
| Templates | `/templates` | get, save |
| Help | `/help` | full, by topic |
| Badge | `/badge/validated` | Shields.io SVG |
| WebSocket | `/ws` | real-time events |
| Meta | `/version`, `/health`, `/metrics`, `/search`, `/config`, `/diff`, `/render/markdown` | |

### 7.4 WebSocket events

```
Client connects to /ws
    │
    └── ConnectionManager.active.append(ws)

Server-side mutation occurs (any create/update/delete/status change)
    │
    └── _broadcast_sync(event, payload)
            │
            └── asyncio.create_task(ws_manager.broadcast(msg))
                    │
                    └── for each ws in active: ws.send_text(json.dumps(msg))

Event payload shape:
{
    "event":   "status_changed" | "created" | "updated" | "deleted"
               | "comment_added" | "attachment_added" | "approved",
    "uid":     "<uuid>",
    "payload": { ... event-specific fields ... }
}
```

Outbound webhooks (configured in `.reqtool/config.yaml`) fire from a daemon thread independently of WebSocket. They use HMAC-SHA256 signatures if a secret is configured.

---

## 8. Validation

### 8.1 Rule categories

`validate_all(store)` runs every rule and returns `{errors: [...], warnings: [...]}`. Errors block promotion workflows; warnings are advisory.

```
Errors
├── missing_title             requirement has no title
├── duplicate_id              two artefacts share the same id
├── invalid_status            status not in merged enums
├── invalid_priority          priority not in enums
├── invalid_req_type          req_type not in enums
├── invalid_relationship      relationship target UID does not exist
├── hash_mismatch             content_hash does not match recomputed value
├── deleted_parent_ref        parentId points to a deleted requirement
├── lock_missing              product has modules but no _product.lock
├── lock_mismatch             module files changed since lock was generated
└── invalid_custom_field      custom_fields value fails schema validation

Warnings
├── missing_owner             no owner set
├── missing_rationale         content.rationale is empty (for approved)
├── missing_ac                no acceptance criteria (for approved)
├── missing_test_ref          no test link and verification_method=test
├── open_tbd_in_approved      approved requirement references open TBD
├── unknown_tag               tag not in enums.yaml
├── unknown_team              allocated_to contains unknown team
├── unknown_owner             owner not in owner list
├── unknown_safety_class      safety_classification not in safety_class list
├── unknown_nfr_key           nfr key not in nfr_keys list
├── supersedes_non_deprecated  supersedes target is not deprecated
└── cross_layer_violation     relationship type not valid between these types
```

### 8.2 Hash verification

`req verify` re-runs `compute_*_hash()` on every artefact and compares the result to the stored `content_hash`. A mismatch means the file was edited outside reqtool (e.g. `vi requirements/abc123.yaml`) without going through the API, which would not have bumped the version or written a history entry.

---

## 9. Export engine

Three export formats are supported.

### 9.1 Markdown

`exports.export_markdown(store, product_id, variant, split_by, flavor)` returns a `dict[filename, content]`.

Each requirement is rendered as a Markdown section with a definition-list style for metadata. Relationships cross-reference by human ID rather than UID. The export optionally splits by domain (one `.md` file per domain) and includes a `mkdocs_nav.yml` fragment for MkDocs site generation.

### 9.2 CSV

`exports.export_csv(store, product_id, variant, fields)` returns a UTF-8 with BOM string (for Excel compatibility). Fields are specified as dotted paths (`approval.status`, `content.description`). Multi-value fields (lists, ACs, relationships) are serialised as semicolon-separated strings within a single cell.

### 9.3 JSX

`exports.export_jsx(store, product_id, variant)` generates a self-contained React component that embeds all requirements, principles, and TBDs as JSON constants. The component renders a collapsible tree with status badges and domain colour coding. It has no runtime dependencies beyond React.

---

## 10. Git integration

### 10.1 Philosophy

reqtool wraps git via subprocess rather than through a library. This keeps the dependency lightweight and ensures the tool uses the user's local git binary with their configured signing keys, hooks, and aliases.

### 10.2 Operations

| Operation | git command | Used by |
|-----------|-------------|---------|
| Stage file | `git add <rel_path>` | commit endpoints |
| Commit | `git commit -m <msg>` | commit endpoints |
| SHA lookup | `git rev-parse HEAD` | post-commit SHA writeback |
| File log | `git log --pretty=format:... -- <path>` | history endpoint |
| Status | `git status --porcelain` | status endpoint, conflict check |
| Tag create | `git tag -a <name> -m <msg>` | baseline create |
| Tag list | `git tag -l --format=...` | baseline list |
| Diff tree | `git diff --name-status <ref> HEAD` | baseline diff |
| Show file | `git show <ref>:<path>` | baseline diff, history |

### 10.3 Commit SHA writeback

After `git commit`, the resulting SHA is written back into the last history entry of the committed artefact:

```
req.history[-1].commit_sha = sha[:7]
save_yaml(path, req)
```

This creates a bidirectional link: the YAML file records its own commit SHA, and the git log records the file path.

### 10.4 Baselines

Baselines are annotated git tags with the prefix `baseline/`. Creating a baseline tags the current HEAD. Diffing against a baseline uses `git diff --name-status baseline/<name> HEAD` to identify changed files, then reads both versions to produce a structured diff of field changes.

---

## 11. Configuration

### 11.1 File locations

All project configuration lives in `.reqtool/` within the requirements repository. The tool ships bundled defaults in `src/reqtool/defaults/` which are used when project files are absent.

| File | Purpose | Bundled default |
|------|---------|----------------|
| `config.yaml` | Repo identity, git settings, export config, validation flags | No -- written by `req init` |
| `enums.yaml` | Domain, team, owner, tag, NFR key lists; estimate_unit | `defaults/enums.yaml` |
| `hierarchy.yaml` | Type system, workflows, DoR/DoD, cross-layer rules | `defaults/hierarchy.yaml` |
| `help.yaml` | Contextual help content | `defaults/help.yaml` |
| `templates.yaml` | Requirement creation templates | `defaults/templates.yaml` |
| `custom_fields.yaml` | Custom field schema | None (optional) |
| `filter_presets.yaml` | Saved sidebar filter combinations | None (written at runtime) |

### 11.2 `config.yaml` structure

```yaml
schema_version: "1.0.0"
repo_id:        my-product
repo_title:     My Product Requirements

git:
  default_branch: main
  commit_name:    Requirements Tool
  commit_email:   reqtool@example.com
  sign_commits:   false
  post_commit_hook: true

export:
  output_dir: exports/
  csv:
    delimiter: ","
    include_fields: []
  markdown:
    flavor: mkdocs
    split_by: domain
  jsx:
    component_name: RequirementsViewer
    include_principles: true
    include_tbds: true

validation:
  require_rationale_for_approved: true
  require_ac_for_approved: true
  require_owner: true
  warn_on_missing_test_ref: true
  warn_on_open_tbds_in_approved: true
  max_history_entries: 20

webhooks:
  - url: https://hooks.example.com/reqtool
    events: [status_changed, approved, comment_added]
    secret: ""
    enabled: true
```

### 11.3 `enums.yaml` extension model

Core enums (status values, verification methods, etc.) are defined in `models.py::CoreEnums`. The `enums.yaml` file extends them with project-specific values. At runtime, `store.merged_enums()` returns the union: core values first, then any project-only additions.

```yaml
# .reqtool/enums.yaml
domain: [system, firmware, hardware, comms, security]
team:   [firmware, hardware, systems, qa]
owner:  [mb, jd, ak]
estimate_unit: points
relationship_types: [blocks, blocked_by]   # extends built-in set
nfr_keys: [latency_ms, throughput_kbps, power_mw]
id_domain:
  FR: functional
  SAF: safety
  US: story
```

---

## 12. Module system

Requirements modules are self-contained sets of requirements stored at `modules/<id>/`. Multiple products can reference the same module. A module appears in a product's tree as a synthetic group node.

```
products/my-product/_product.yaml:
  modules:
    - id: comms-baseline
      version: 1.2.0
      overrides:
        <uid>:
          priority: critical   # only overrideable fields (from _module.yaml)
```

Module integrity is verified by computing a SHA-256 over all module requirement files and comparing it to the stored hash in `_product.lock`. This lock file is written by `req import <module-id>` and checked by `req validate`.

---

## 13. Diagrams

### 13.1 Artefact state machines

**Sprint workflow** (epic, feature, story, task, bug, spike):

```
        ┌──────────────────────────────────────────┐
        │                                          │
        ▼                                          │
    ┌─────────┐    ┌───────┐    ┌─────────────┐   │
    │ backlog │───▶│ ready │───▶│ in_progress │───┘
    └─────────┘    └───────┘    └──────┬──────┘
         ▲              │              │
         │              │         ┌───▼──────┐
         └──────────────┴─────────│ in_review│
                                  └───┬──────┘
                                      │
                               ┌──────▼──────┐    ┌───────────┐
                               │    done     │    │ cancelled │
                               └─────────────┘    └───────────┘
```

**Formal workflow** (functional, performance, interface, etc.):

```
    ┌───────┐    ┌───────────┐    ┌──────────┐    ┌──────────┐    ┌────────────┐
    │ draft │───▶│ in_review │───▶│ reviewed │───▶│ approved │───▶│ deprecated │
    └───────┘    └─────┬─────┘    └────┬─────┘    └────┬─────┘    └────────────┘
         ▲             │               │               │
         └─────────────┘               └───────────────┘
              (back)                        (back)
```

**Safety formal workflow** (safety requirements):

Same states and transitions as formal, plus an `approved` guard requiring:
- `content.description` non-empty
- `content.rationale` non-empty
- `safety_classification` set
- at least one acceptance criterion

### 13.2 Write path sequence

```
Client                  API endpoint              Store              Disk
  │                          │                      │                  │
  │── PUT /requirements/uid ▶│                      │                  │
  │                          │── validate_transition│                  │
  │                          │       (if status     │                  │
  │                          │        changing)     │                  │
  │                          │── update_requirement▶│                  │
  │                          │                      │── _sanitise      │
  │                          │                      │── deep merge     │
  │                          │                      │── recompute hash │
  │                          │                      │── bump version   │
  │                          │                      │── append history │
  │                          │                      │── save_yaml ────▶│
  │                          │◀─── updated dict ────│                  │
  │                          │── _fire_webhook       │                  │
  │                          │── _broadcast_sync     │                  │
  │◀──── 200 JSON ───────────│                      │                  │
```

### 13.3 Tree construction

```
store.build_tree(product_id, variant)
    │
    ├── start with all store.requirements
    │
    ├── for each module in product.modules:
    │     add module requirements (with overrides applied)
    │
    ├── if variant set:
    │     filter by attribute variant_<name> != false
    │
    ├── exclude deleted
    │
    ├── build children_map: {parent_uid: [child_req, ...]}
    │
    ├── collect roots (parentId == None)
    │   if product.root_requirements is set: apply that ordering
    │
    ├── recurse: node(req) -> {uid, id, title, status, ..., children: [...]}
    │
    └── append synthetic module group nodes for each module
```

### 13.4 Validation rule execution

```
validate_all(store)
    │
    ├── for each requirement (not deleted):
    │     _validate_requirement(req, ...)
    │       ├── check id, title, status, priority, req_type (enum membership)
    │       ├── check hash (content_hash matches recomputation)
    │       ├── check relationships (target UIDs exist)
    │       ├── check AC required (if approved + config flag)
    │       ├── check owner required (if config flag)
    │       ├── check rationale (if approved + config flag)
    │       ├── check NFR keys (against repo enum)
    │       ├── check tags, teams, owners (against enums)
    │       ├── check safety_classification (if safety_related)
    │       ├── check supersedes target is deprecated
    │       └── check cross-layer relationship rules (from hierarchy.yaml)
    │
    ├── for each principle (not deleted):
    │     _validate_principle(principle, ...)
    │
    ├── for each TBD (not deleted):
    │     _validate_tbd(tbd, ...)
    │
    ├── check parentId references are not deleted
    │
    └── _validate_module_locks(store, errors)
          └── for each product with modules:
                check _product.lock exists
                check lock hash matches current module files
```

---

## 14. Performance characteristics

| Operation | Complexity | Notes |
|-----------|-----------|-------|
| `Store.load()` | O(n) files | Done once at startup |
| `GET /requirements` (list) | O(n) | Linear scan with filter |
| `GET /requirements/{uid}` | O(1) | Dict lookup by UID |
| `store.build_tree()` | O(n) | Single pass to build children map |
| `store.compute_impact()` | O(n + e) | BFS over relationship edges |
| `store.compute_estimate_rollup()` | O(children) | Scans all reqs for matching parentId |
| `validate_all()` | O(n²) worst case | Relationship lookups; in practice O(n log n) |
| `req verify` | O(n) | Recomputes all hashes |

For typical engineering programme sizes (< 10,000 requirements) all operations complete in under a second on commodity hardware. The file-per-requirement layout means git operations scale with the number of changed files, not total repository size.

---

## 15. Security notes

- The server binds to `127.0.0.1` by default. Exposing it on a network interface is the operator's responsibility.
- Webhook signatures use HMAC-SHA256. The secret is stored in plaintext in `config.yaml`; treat that file as a secret if webhooks are in use.
- File attachments are stored under `attachments/<uid>/` with filenames sanitised to `[A-Za-z0-9._-]`. Maximum filename length is 200 characters.
- Content-Disposition filenames from upload requests are sanitised before use as paths.
- There is no authentication layer built in. Add a reverse proxy (nginx, Caddy) with basic auth or mutual TLS if multi-user network access is required.
