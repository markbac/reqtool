# GitHub Copilot Code Review Guidelines for `reqtool`

When reviewing Pull Requests in this repository, GitHub Copilot should evaluate code changes against the following core technical, architectural, and requirement quality guidelines:

## 1. Python Architecture & Decoupling
- **FastAPI APIRouters:** All new API endpoints MUST be placed inside dedicated `APIRouter` modules in `src/reqtool/routers/` (e.g., `requirements.py`, `principles.py`, `modules.py`, `exports.py`). Do not place endpoints in `src/reqtool/api.py`.
- **Domain Store Helpers:** Specialized storage logic should be placed in `src/reqtool/stores/` (`hierarchy_store.py`, `comment_store.py`, `attachment_store.py`).
- **Thread Safety:** Any state mutations in `Store` must maintain `threading.RLock()` synchronization.

## 2. Requirement Schema & Safety Standards
- **Schema Validation:** Ensure requirement YAML files strictly define required fields (`id`, `title`, `content.description`, `status`, `type`, `version`).
- **Regulatory Compliance:** Verify safety-critical metadata aligns with ISO 26262 (`ASIL_A`, `ASIL_B`, `ASIL_C`, `ASIL_D`), DO-178C (`DAL_A` through `DAL_E`), and IEC 62304 (`CLASS_A`, `CLASS_B`, `CLASS_C`).
- **Controlled Vocabularies:** Ensure tags, owners, teams, and disciplines map to `repo_enums` configured in `.reqtool/enums.yaml`.

## 3. INCOSE Prose Quality Rules
- **Active Voice:** Requirement statements must use active voice ("The system shall...") rather than passive phrasing.
- **No Ambiguous or Vague Terms:** Flag words such as `user-friendly`, `fast`, `robust`, `seamless`, `reliable`, `flexible`, `adequate`.
- **No Escape Clauses:** Flag phrases like `if possible`, `where appropriate`, `as far as practical`, `if necessary`.
- **Numeric Bounds:** Ensure performance criteria specify explicit numeric parameters rather than vague descriptors (`high`, `low`).

## 4. Versioning & Hashing Integrity
- **Content Hashing:** Edits to non-semantic metadata (e.g. comments, attachments) must not alter `compute_requirement_hash`.
- **Suspect Link Flagging:** When parent/target requirements undergo version updates, verify that suspect link tracking flags downstream relationships.

## 5. React UI Components
- **Component Placement:** Frontend components belong in `src/reqtool/ui/src/components/`.
- **Build Verification:** Any UI change must compile cleanly via `npm run build` without Vite bundling errors.

## 6. Test Suite Coverage
- **100% Pass Rate:** All unit and integration tests under `tests/` must pass (`pytest`).
- **New Tests Required:** Any new feature or bug fix must be accompanied by new test cases in `tests/unit/test_store.py`, `tests/integration/test_api.py`, `tests/unit/test_validation.py`, or `tests/acceptance/test_cli.py`.
