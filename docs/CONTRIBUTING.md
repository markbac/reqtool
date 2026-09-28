# Contributing

## Getting started

```bash
git clone https://github.com/markbac/reqtool.git
cd reqtool
pip install -e ".[test]"    # installs Python package with pre-built UI
./scripts/dev.sh test core  # quick sanity check
./scripts/dev.sh serve      # start the server -- UI at http://localhost:8765
```

On Windows:

```powershell
git clone https://github.com/markbac/reqtool.git
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

## Branching & PR Workflow

- `main` -- stable, always passes CI.
- Feature branches: `feature/<short-description>`.
- Bug fixes: `fix/<short-description>`.
- **Pull Requests:** Every PR triggers GitHub Actions CI and automated GitHub Copilot code review guided by `.github/copilot-instructions.md`.
