# reqtool

Git-backed YAML requirements management tool for embedded and IoT product teams.

Requirements, principles, and TBDs live as individual YAML files in a git repository. The tool handles content hashing, semantic versioning, full validation, module reuse, and export. A FastAPI backend serves a React UI and a fully-typed REST API documented as OpenAPI 3.1.

---

## Quick start

```bash
# Install (Python 3.11+)
pip install reqtool          # from PyPI (when published)
# or from source:
pip install -e .             # pre-built UI is included -- no npm step required

# Initialise a new repository -- choose a flavour:
mkdir my-reqs && cd my-reqs
git init

req init               # blank repo (prompts for ID and title)
req init agile         # agile types: theme/initiative/epic/feature/story/task/bug/spike
req init systems       # systems types, formal/safety-formal workflow
req init defaults      # agile + systems types, formal workflows, and pre-populated principles
req init demo          # full IoT sensor demo dataset

# Start the server (opens http://localhost:8765 with full UI)
req serve
```

> **Note:** The React UI (`src/reqtool/ui/dist/`) is pre-built and committed to
> the repository. `pip install` is the only step needed. Rebuild the UI only if
> you modify files under `src/reqtool/ui/src/`:
> ```bash
> cd src/reqtool/ui && npm install && npm run build
> ```

---

## Repository layout

After `req init` your requirements repository will look like this:

```
my-reqs/
├── .reqtool/
│   ├── config.yaml          # Repo config (git settings, export, validation)
│   ├── enums.yaml           # Project-specific enum extensions and NFR key registry
│   ├── hierarchy.yaml       # Type system, workflow definitions, DoR/DoD templates
│   ├── help.yaml            # Custom help content (optional; falls back to defaults)
│   ├── templates.yaml       # Requirement creation templates
│   ├── custom_fields.yaml   # Custom field schema
│   └── filter_presets.yaml  # Saved sidebar filter combinations
├── requirements/
│   └── <uid>.yaml           # One file per requirement
├── principles/
│   └── <uid>.yaml
├── tbds/
│   └── <uid>.yaml
├── modules/
│   └── <module-id>/
│       ├── _module.yaml     # Module manifest
│       └── <uid>.yaml       # Module requirements
├── products/
│   └── <product-id>/
│       ├── _product.yaml    # Product manifest (module refs, variants, root ordering)
│       └── _product.lock    # Lock file written by `req import`
├── comments/                # Threaded comments (outside content hash)
├── attachments/             # File attachments
└── exports/                 # Generated output (gitignore-able)
```

---

## Item types

reqtool supports two complementary vocabularies that can coexist in the same repository.

### Agile planning hierarchy

| Type | Prefix | Workflow | Description |
|------|--------|----------|-------------|
| `theme` | `TH` | lightweight | Highest strategic grouping; multi-year outcome |
| `initiative` | `IN` | lightweight | Large body of work within a theme |
| `epic` | `EP` | sprint | Significant user-facing capability |
| `feature` | `FT` | sprint | Discrete piece of functionality |
| `story` | `US` | sprint | Unit of user value |
| `task` | `TK` | sprint | Concrete unit of technical work |
| `bug` | `BG` | sprint | A defect |
| `spike` | `SP` | sprint | Time-boxed investigation |

Hierarchy: `theme → initiative → epic → feature → story / task / bug / spike`

### Systems engineering types

| Type | Prefix | Workflow | Description |
|------|--------|----------|-------------|
| `stakeholder_need` | `SN` | lightweight | Top-level systems intent |
| `functional` | `FR` | formal | Capability the system shall provide |
| `performance` | `PR` | formal | Quantified speed/throughput/capacity constraint |
| `security` | `SR` | formal | Protection against threats |
| `safety` | `SAF` | safety_formal | Harm prevention constraint |
| `interface` | `IR` | formal | System boundary definition |
| `compliance` | `CR` | formal | Legal/standard/contractual obligation |
| `constraint` | `CON` | formal | Design or implementation restriction |
| `operational` | `OR` | formal | Operation/maintenance constraint |
| `physical` | `PHR` | formal | Physical/environmental constraint |

Cross-layer: agile items link to systems requirements via explicit relationship types (`satisfies`, `implements`, `traces_to`).

---

## Workflows

Four workflow types are defined in `defaults/hierarchy.yaml`. Override any per-project in `.reqtool/hierarchy.yaml`.

| Workflow | Used by | States |
|----------|---------|--------|
| `lightweight` | theme, initiative, stakeholder_need | draft → active → done / cancelled |
| `sprint` | epic, feature, story, task, bug, spike | backlog → ready → in_progress → in_review → done |
| `formal` | functional, performance, interface, etc. | draft → in_review → reviewed → approved → deprecated |
| `safety_formal` | safety | Same as formal, with a transition guard on `approved` requiring ACs and `safety_classification` |

### Workflow guards

Guards are configurable pre-conditions enforced at transition time. If a guard fails, the transition returns `409 workflow_guard`. They are defined per target state in `hierarchy.yaml`:

```yaml
workflows:
  safety_formal:
    guards:
      approved:
        requires_fields: [content.description, content.rationale, safety_classification]
        requires_ac: true
        message: "Safety requirements must have description, rationale, ACs, and safety_classification."
```

Use `POST /requirements/{uid}/transition` for explicit transitions, or `PUT /requirements/{uid}` (which also enforces guards when `status` changes).

---

## Fields

### Core fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | string | Immutable UUID7. Used in relationships and API calls. |
| `id` | string | Human-readable identifier (e.g. `US-042`). Auto-assigned from type prefix if omitted. |
| `title` | string | One-line summary. |
| `status` | string | Current workflow state. Initial value set from workflow `initial`. |
| `priority` | string | `critical` / `high` / `medium` / `low` |
| `req_type` | string | Item type (see table above). |
| `owner` | string | Accountable person (from `enums.yaml` `owner` list). |
| `assignee` | string | Person doing the work. Distinct from `owner`. |
| `iteration` | string | Named iteration reference (sprint name, PI, milestone). |
| `estimate` | float | Numeric effort estimate. Unit configured by `estimate_unit` in `enums.yaml`. |
| `dor_checklist` | list | Definition of Ready; `{item, checked}` pairs. Populated from `hierarchy.yaml` defaults. |
| `dod_checklist` | list | Definition of Done; same structure. |

All long-form text fields (`content.description`, `content.rationale`, `content.extended_description`, AC text, DoR/DoD labels, comment text) support Markdown, rendered server-side via `POST /render/markdown`.

### Estimate rollup

`GET /requirements/{uid}/rollup` returns the sum of all direct children's `estimate` values. The result is read-only and computed on demand. Unit is the repo-wide `estimate_unit` from `enums.yaml`.

---

## Relationships

The primary structural relationship is parent/child via `parentId`. Additional relationships are explicit typed links in the `relationships` array.

### Built-in relationship types

| Type | Direction | Description |
|------|-----------|-------------|
| `relates_to` | non-directional | Generic association |
| `depends_on` | → | This item cannot proceed until the target is complete |
| `depended_by` | ← | Computed inverse of `depends_on`; read-only |
| `satisfies` | → | Agile item satisfies a systems requirement |
| `implements` | → | Agile item implements a requirement |
| `traces_to` | → | General traceability link |
| `derived_from` | → | This item was derived from the target |
| `conflicts_with` | non-directional | This item is in tension with the target |
| `supersedes` | → | This item replaces the target |

Add or remove types in `enums.yaml` under `relationship_types`.

Cross-layer rules in `hierarchy.yaml` define which relationship types are valid between which source and target types. Violations produce a validation **warning**, not a hard error.

### Change impact analysis

`GET /requirements/{uid}/impact` returns the transitive downstream closure: all items linked via `derived_from`, `depends_on`, `implements`, or `satisfies`, grouped by type, plus the direct upstream chain.

---

## Definition of Ready / Definition of Done

DoR and DoD checklists are `{item, checked}` lists stored on each requirement. Templates are defined per type in `hierarchy.yaml` and applied automatically on creation.

```yaml
dor:
  story:
    - item: Acceptance criteria defined
    - item: Estimate provided
    - item: Dependencies identified
```

Check items off via `PUT /requirements/{uid}` with the updated `dor_checklist` / `dod_checklist`.

---

## Kanban board

`GET /kanban` returns a column-per-state board using the workflow states for the filtered type. Cards include: `uid`, `id`, `title`, `assignee`, `estimate`, `priority`, `req_type`.

Query parameters: `req_type`, `iteration`, `owner`, `assignee`.

---

## Real-time updates

Connect to `GET /ws` (WebSocket) for a live event stream. The server broadcasts:

- `created` -- new artefact written
- `updated` -- artefact changed (includes `changed_fields`)
- `deleted` -- artefact soft-deleted
- `status_changed` -- status field changed
- `comment_added`, `attachment_added`

Event payload: `{event, uid, id, type, payload}`.

Outbound webhooks (configured in `.reqtool/config.yaml`) remain for external integrations.

---

## Filter presets

Save named filter combinations for the sidebar:

```
PUT  /filter-presets/{id}    {"label": "Sprint 3", "filters": {"iteration": "Sprint-3", "req_type": "story"}}
GET  /filter-presets          list all presets
DELETE /filter-presets/{id}  delete a preset
```

Presets are stored in `.reqtool/filter_presets.yaml`.

---

## Help system

`GET /help` returns contextual help content from `defaults/help.yaml` (or `.reqtool/help.yaml` if present). Use `?topic=<key>` for a specific section: `concepts`, `fields`, `workflow`, `relationships`, `estimates`, `dor_dod`, `validation`, `git_baselines`, `export`.

---

## CI badge

Add a validation badge to your README:

```markdown
![reqtool validated](http://localhost:8765/badge/validated)
```

`GET /badge/validated` returns a Shields.io-compatible SVG. Green = passing, yellow = warnings, red = errors. Add `?nocache=1` to force re-evaluation.

---

## CLI reference

```
req init                         Blank repo (prompts for ID and title)
req init agile                   Agile types, sprint workflow, DoR/DoD defaults
req init systems                 Systems types, formal/safety-formal workflow
req init defaults                Blank repo with engineering principles pre-populated
req init demo                    Full IoT sensor demo dataset

req serve                        Start API + UI at http://localhost:8765
req validate                     Full validation suite; exit 1 on errors
req verify                       Verify all content hashes; exit 1 on mismatch

req new requirement              Create a requirement interactively
req new principle                Create a principle interactively
req new tbd                      Create a TBD interactively

req new-agile story              Create a story (auto-increments US-NNN)
req new-agile task               Create a task (TK-NNN)
req new-agile bug                Create a bug (BG-NNN)
req new-agile spike              Create a spike (SP-NNN)
req new-agile epic               Create an epic (EP-NNN)
req new-agile feature            Create a feature (FT-NNN)
req new-agile theme              Create a theme (TH-NNN)
req new-agile initiative         Create an initiative (IN-NNN)

req export jsx                   Export JSX viewer component
req export markdown              Export Markdown files
req export csv                   Export CSV

req import <module-id>           Import a module into a product
req baseline create <name>       Create a baseline tag
req baseline list                List all baseline tags
req diff [--since <ref>]         Show changes since a ref
req stats                        Print metrics summary
req show <id-or-uid>             Print an artefact to stdout
req history <id-or-uid>          Print git log for an artefact
req openapi [-o openapi.yaml]    Export OpenAPI specification
```

---

## API overview

All endpoints are documented at `http://localhost:8765/docs` (Swagger UI) or `http://localhost:8765/redoc`.

### Requirements

```
GET    /requirements                     List (filter by domain, status, type, owner, tag)
POST   /requirements                     Create
GET    /requirements/{uid}               Get
PUT    /requirements/{uid}               Update (enforces workflow guards on status change)
DELETE /requirements/{uid}               Soft-delete
POST   /requirements/{uid}/transition    Explicit workflow transition with guard enforcement
GET    /requirements/{uid}/impact        Transitive downstream impact closure
GET    /requirements/{uid}/rollup        Computed estimate rollup for children
GET    /requirements/{uid}/history       In-file + git history
GET    /requirements/{uid}/relationships Outgoing + incoming relationship links
POST   /requirements/bulk                Bulk field update across multiple UIDs
POST   /requirements/{uid}/clone         Clone a requirement
POST   /requirements/{uid}/approve       Approve and set approval block
POST   /requirements/{uid}/commit        Stage + git commit a single requirement
POST   /requirements/{uid}/ac            Add acceptance criterion
PUT    /requirements/{uid}/ac/{ac_uid}   Update acceptance criterion
DELETE /requirements/{uid}/ac/{ac_uid}   Delete acceptance criterion
```

### Hierarchy

```
GET  /hierarchy                          Full hierarchy config
GET  /hierarchy/types                    Configured item types
GET  /hierarchy/children/{req_type}      Allowed child types
```

### Kanban

```
GET  /kanban                             Column-per-state board (filter: req_type, iteration, owner, assignee)
```

### Help

```
GET  /help                               Full help content
GET  /help?topic=<key>                   Specific help section
```

### Filter presets

```
GET    /filter-presets                   List saved presets
PUT    /filter-presets/{id}              Save or update a preset
DELETE /filter-presets/{id}              Delete a preset
```

### Other endpoints

```
GET  /requirements/tree                  Nested tree for a product
GET  /products/{id}/tree                 Product tree
GET  /kanban                             Kanban board
GET  /ws                                 WebSocket event stream
GET  /badge/validated                    Shields.io SVG badge
GET  /validate                           Full validation result
GET  /validate/{uid}                     Single artefact validation
GET  /metrics                            Repository health metrics
GET  /workflow                           Workflow config
GET  /hierarchy                          Full hierarchy config
GET  /templates                          Requirement templates
GET  /enums                              Merged enums
GET  /git/status                         Git working tree status
POST /git/commit                         Batch commit
GET  /baselines                          List baselines
POST /baselines                          Create baseline tag
GET  /baselines/{name}/diff              Diff against baseline
GET  /diff                               Requirement diff since ref
POST /render/markdown                    Render Markdown to HTML
GET  /health                             Health check
GET  /version                            Tool + schema version
```

---

## Modules

Requirements modules are self-contained sets of requirements stored outside product definitions in a top-level `modules/` directory. Multiple products can reference the same module.

```
modules/
└── comms-baseline/
    ├── _module.yaml    # Manifest: title, version, overrideable fields
    └── <uid>.yaml      # Module requirements
```

Reference a module from a product manifest:

```yaml
modules:
  - id: comms-baseline
    version: 1.2.0
    overrides:
      <uid>:
        priority: critical
```

Lock a module with `req import <module-id>` (writes `_product.lock`). Verify integrity with `GET /modules/{id}/verify`.

---

## Validation

Run offline with `req validate` (exits 1 on errors) or via `GET /validate`.

Common warnings and how to resolve them:

| Code | Resolution |
|------|-----------|
| `missing_owner` | Set `owner` to a person from `enums.yaml` |
| `missing_ac` | Add at least one acceptance criterion |
| `missing_rationale` | Fill in `content.rationale` |
| `hash_mismatch` | File edited outside reqtool; run `req verify` |
| `unknown_relationship_target` | Target UID does not exist |
| `cross_layer_violation` | Relationship type not permitted between these types |
| `dor_incomplete` | DoR items not checked before transition to In Progress |
| `dod_incomplete` | DoD items not checked before transition to Done |

---

## Configuration

`.reqtool/config.yaml` controls git settings, export paths, validation flags, and the fallback workflow config (used when no `hierarchy.yaml` is present).

`.reqtool/enums.yaml` extends the core enums and configures:

- `estimate_unit` -- repo-wide unit label for estimates (`points`, `days`, `hours`)
- `relationship_types` -- additional relationship type IDs beyond the built-in set
- `id_domain` -- maps ID prefix → type for suggestion

---

## Development

```bash
pip install -e ".[test]"
pytest tests/test_store.py tests/test_validation.py tests/test_cli.py     # ~20s
pytest tests/test_features_v03.py                                          # ~30s
pytest tests/test_api.py -k "not watchdog"                                 # ~60s
pytest tests/test_regression.py                                            # ~30s
```

The watchdog-based incremental reload tests are slow (they wait for filesystem events). Exclude with `-k "not watchdog"` during development.

## Further reading

- [ARCHITECTURE.md](ARCHITECTURE.md) -- component overview, data model, workflow engine, API surface, validation rules, git integration, and annotated sequence diagrams.
