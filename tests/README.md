# reqtool tests

## Structure

The suite has four tiers (QA-01). Put a new test in the lowest tier that can show the behaviour.

| Directory | What it tests | How it runs |
|-----------|---------------|-------------|
| `unit/` | Logic in one process with no HTTP: the store, validation, services, gateways, models, file IO, architecture guards | seconds |
| `integration/` | The REST API through a test client, including the hierarchy and workflow contract tests | minutes |
| `acceptance/` | The product from outside: the CLI, the demo repository, the docs and the CI definitions | a minute or two |
| `e2e/` | A real browser against a real server (needs Playwright, see `CONTRIBUTING.md`) | about six minutes |

Shared helpers and fixtures live in `conftest.py`; `golden/` holds the recorded files that tests compare against.

## v0.3.0 test coverage (`test_features_v03.py`)

101 tests across 14 test classes:

- `TestHierarchyLoading` -- hierarchy.yaml loads, type metadata, workflow definitions, DoR/DoD templates, cross-layer rules
- `TestHierarchyEndpoints` -- GET /hierarchy, GET /hierarchy/types, GET /hierarchy/children/{type}
- `TestItemTypes` -- all 11 new/updated type prefixes, ID auto-increment per type, independent sequences, explicit ID override
- `TestDorDodChecklists` -- DoR/DoD populated on creation, all items unchecked, update via PUT, custom overrides
- `TestNewFields` -- assignee, iteration, estimate create/update/persist
- `TestEstimateRollup` -- sum of children, no children, partial children, none when no estimates
- `TestWorkflowTransitions` -- valid sprint transitions, terminal state blocks, safety guard without AC, safety guard passes with AC, missing to_state 422, PUT guard enforcement
- `TestImpactAnalysis` -- isolated req, downstream via derived_from, upstream chain, transitive closure (A→B→C), satisfies relationship, 404 for unknown UID
- `TestKanban` -- columns returned, filter by type/iteration/assignee, card shape, sprint workflow states, empty filter result
- `TestBadge` -- SVG returned, "passing" text, no-cache headers
- `TestHelpSystem` -- full content, topic filter, unknown topic returns empty, fields section coverage
- `TestFilterPresets` -- empty list, save+retrieve, update, delete, delete nonexistent 404, missing label 422, multiple presets
- `TestWebSocket` -- connection accepted, stays open
- `TestCliInitVariants` -- req init agile (files created, estimate_unit=points), req init systems (files created, estimate_unit=days), re-init exits non-zero
- `TestCliNewAgile` -- parametrised over story/task/bug/spike/epic
- `TestStoreHierarchyHelpers` -- workflow by type, validate_transition allow/block, next_id increment, default_checklist, compute_impact, estimate rollup, filter preset round-trip and delete

## Running

```bash
# Fast: no HTTP
pytest tests/unit

# Everything except the browser tests
pytest tests --ignore=tests/e2e

# A single tier
pytest tests/integration
```

## Fixtures

Defined in `conftest.py`:

- `repo_root` -- `tmp_path`-backed directory with required subdirectories
- `store` -- loaded `Store` instance backed by fresh temp repo
- `client` -- `TestClient` backed by fresh temp repo
- `client_with_store` -- returns `(TestClient, Store)` sharing the same root
- `agile_client` -- returns `(TestClient, items)` over a repository with every level of the agile hierarchy
  (theme to task, a bug and a spike) in mixed workflow states; `build_agile_repo(client)` builds it on any client
- `make_req(client, **kwargs)` -- helper to POST a minimal requirement
- `make_principle(client, **kwargs)` -- helper to POST a minimal principle
- `make_tbd(client, **kwargs)` -- helper to POST a minimal TBD
