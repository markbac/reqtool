# reqtool tests

## Structure

| File | Coverage | ~Time |
|------|----------|-------|
| `test_store.py` | Store load, CRUD, tree, modules, products, comments, attachments | 10s |
| `test_validation.py` | Full validation suite, all rules and edge cases | 5s |
| `test_cli.py` | CLI commands: init, validate, verify, export, import, diff, stats | 8s |
| `test_api.py` | All REST endpoints including edge cases; excludes watchdog-slow tests | 60s |
| `test_regression.py` | Cross-cutting regression scenarios | 30s |
| `test_features_v03.py` | v0.3.0 feature suite (see below) | 30s |

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
# Fast subset (no watchdog)
pytest tests/test_store.py tests/test_validation.py tests/test_cli.py tests/test_features_v03.py

# Full suite excluding slow watchdog tests
pytest -k "not watchdog"

# All tests (slow -- allows watchdog settle time)
pytest
```

## Fixtures

Defined in `conftest.py`:

- `repo_root` -- `tmp_path`-backed directory with required subdirectories
- `store` -- loaded `Store` instance backed by fresh temp repo
- `client` -- `TestClient` backed by fresh temp repo
- `client_with_store` -- returns `(TestClient, Store)` sharing the same root
- `make_req(client, **kwargs)` -- helper to POST a minimal requirement
- `make_principle(client, **kwargs)` -- helper to POST a minimal principle
- `make_tbd(client, **kwargs)` -- helper to POST a minimal TBD
