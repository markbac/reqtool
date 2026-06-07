# Contributing

## Getting started

```bash
git clone https://github.com/<your-org>/reqtool.git
cd reqtool
pip install -e ".[test]"    # installs Python package with pre-built UI
./scripts/dev.sh test core  # quick sanity check
./scripts/dev.sh serve      # start the server -- UI at http://localhost:8765
```

On Windows:

```powershell
git clone https://github.com/<your-org>/reqtool.git
cd reqtool
pip install -e ".[test]"
.\scripts\dev.ps1 test core
.\scripts\dev.ps1 serve
```

`pip install -e .` is all that is required. The pre-built React UI (`src/reqtool/ui/dist/`) is committed to the repository and ships inside the Python wheel, so no `npm` step is needed to run the server.

## Rebuilding the UI

Only needed if you change files under `src/reqtool/ui/src/`:

```bash
cd src/reqtool/ui
npm install   # first time only
npm run build # writes src/reqtool/ui/dist/
```

Commit the updated `dist/` alongside your source changes. CI verifies the committed dist matches the source on every push.

## Running tests

```bash
./scripts/dev.sh test             # full suite
./scripts/dev.sh test core        # store, validation, CLI  (~20s)
./scripts/dev.sh test features    # v0.3.0 feature suite   (~30s)
./scripts/dev.sh test api         # API + regression       (~2 min)
```

See `tests/README.md` for details on what each suite covers.

## Project layout

```
reqtool/
├── .github/
│   └── workflows/
│       └── ci.yml          GitHub Actions CI (lint, 3×test matrix, build)
├── scripts/
│   ├── dev.sh              Bash dev runner (Linux / macOS)
│   └── dev.ps1             PowerShell dev runner (Windows)
├── src/
│   └── reqtool/
│       ├── __init__.py     Version
│       ├── api.py          FastAPI application
│       ├── cli.py          Click CLI
│       ├── store.py        In-memory artefact store + hierarchy helpers
│       ├── models.py       Pydantic models
│       ├── validation.py   Validation rules
│       ├── exports.py      CSV / Markdown / JSX export
│       ├── fileio.py       YAML I/O, hashing, UUID7, version bumping
│       ├── git_ops.py      Git wrappers
│       ├── main.py         ASGI factory for uvicorn
│       ├── defaults/       Bundled YAML defaults (hierarchy, enums, templates, help)
│       └── ui/             React frontend source (Vite)
├── tests/
│   ├── conftest.py         Shared fixtures
│   ├── test_store.py
│   ├── test_validation.py
│   ├── test_cli.py
│   ├── test_api.py
│   ├── test_features_v03.py
│   └── test_regression.py
├── pyproject.toml
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
└── README.md
```

## Making changes

- Keep changes surgical -- touch only what the task requires.
- Match the existing code style.
- Add or update tests for every new behaviour.
- Add a CHANGELOG entry under `[Unreleased]`.
- Run `./scripts/dev.sh test` before opening a PR.

## Branching

- `main` -- stable, always passes CI.
- Feature branches: `feature/<short-description>`.
- Bug fixes: `fix/<short-description>`.

Open a PR against `main`. CI runs automatically.

## Releasing

1. Update the version in `src/reqtool/__init__.py` and `pyproject.toml`.
2. Move the `[Unreleased]` section of `CHANGELOG.md` to a versioned heading.
3. Commit: `chore: release v<version>`.
4. Tag: `git tag v<version> && git push --tags`.
