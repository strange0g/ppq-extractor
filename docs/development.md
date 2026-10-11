# Developer Guide

This document provides developer guidelines for local environment setup, CLI tooling usage, test suite execution, and code style standards in **PPQ Extractor**.

---

## 1. Local Environment Setup

The repository relies on [`uv`](https://docs.astral.sh/uv/) for Python dependency management and execution isolation.

### Prerequisites

- Python `>=3.10`
- `uv` installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- `poppler-utils` system package (`pdftoppm` and `pdfinfo`):
  ```bash
  # Ubuntu / Debian
  sudo apt-get update && sudo apt-get install -y poppler-utils

  # macOS
  brew install poppler
  ```

### Virtual Environment

Create and sync the virtual environment:

```bash
uv sync
```

This installs runtime dependencies (`pillow`, `numpy`) and dev dependencies (`ruff`, `pytest`).

---

## 2. CLI Tooling Reference

The package registers three console scripts in `pyproject.toml`:

### `ppq-queue` (`tools.queue_manager`)
 
Manages the Processing Queue ledger and provides question bank query capabilities in `.pipeline/queue.db`:
 
```bash
# Scan a source directory to discover and register Cambridge Question Papers
uv run ppq-queue scan --source-dir 9709/2024
 
# Poll next paper for a given role (extractor or verifier)
uv run ppq-queue next --role extractor
 
# View status and details of a paper
uv run ppq-queue show --id 9709_w24_qp_11
 
# Print concise queue status table
uv run ppq-queue summary
 
# Update paper status manually
uv run ppq-queue update --id 9709_w24_qp_11 --status extracted --extracted-marks 75 --notes "Slices extracted"

# Query questions by Cambridge Syllabus Topic Code
uv run ppq-queue query --topic 1.1 --component 1 --format table

# Query Question Parts by Syllabus Topic Code
uv run ppq-queue query --topic 1.1 --parts --format json
```
 
### `ppq-render` (`tools.pdf_to_images`)
 
Converts a Question Paper PDF to zero-padded PNG page images (`page_01.png`, `page_02.png`, etc.):
 
```bash
uv run ppq-render \
  --pdf "9709/2024/2024 Nov/9709_w24_qp_11.pdf" \
  --out-dir "data/output/9709_w24_qp_11/pages" \
  --dpi 200
```
 
Flags:
- `--dpi`: Resolution in dots per inch (default: `200`).
- `--force`: Force re-rendering even if valid cached page images already exist.
 
### `ppq-crop` (`tools.crop_slices`)
 
Performs full-width slicing, answer workspace excising, margin trimming, Question Package generation, and automatic SQLite database synchronization from a `manifest.json`:
 
```bash
uv run ppq-crop \
  --manifest "data/output/9709_w24_qp_11/manifest.json" \
  --pages-dir "data/output/9709_w24_qp_11/pages" \
  --out-dir "data/output/9709_w24_qp_11"
```
 
Flags:
- `--pad`: Vertical padding in pixels applied to each slice (default: `10`).
- `--spacing`: Vertical divider spacing in pixels between stitched slices (default: `20`).
- `--no-trim-margins`: Disable automatic lateral margin warning trimming.
- `--db-path`: Target SQLite database for automatic manifest synchronization (default: `.pipeline/queue.db` if present).
- `--no-db`: Disable automatic SQLite database synchronization.
- `--emit-question-json`: Emit legacy per-question `question.json` descriptors (deprecated by default).
 
---
 
## 3. Test Suite
 
The test suite contains 84 deterministic tests organized under `tests/`:
 
- **`test_queue.py`**: Validates queue loading, atomic writing, schema conformance, status transitions, role polling, and SQLite ledger operations.
- **`test_crop_slices.py`**: Tests coordinate translation, full-width cropping, composite stitching, automatic margin trimming, and Question Package asset isolation.
- **`test_pdf_to_images.py`**: Tests PDF rendering, page count determination, output naming, and error handling.
- **`test_db.py`**: Tests SQLite connection factory (WAL mode, timeouts, foreign keys), atomic transactions, and versioned migrations.
- **`test_db_sync.py`**: Tests atomic manifest-to-database synchronization, foreign key integrity, and idempotent verifier replacement.
- **`test_pipeline_integration.py`**: Tests end-to-end integration between `ppq-crop` and SQLite database synchronization.
- **`test_question_repository.py`**: Tests `QuestionRepository` topic filtering, multi-attribute search, sub-10ms performance, and CLI queries.
- **`test_review_fixes.py`**: Validates Pydantic v2 models, pagination bounds, domain vocabulary, and query argument builders.
- **`test_end_to_end_pipeline.py`**: Verifies full pipeline execution from raw PDF to verified Question Packages and database records.
- **`test_glossary_lint.py`**: Deterministic terminology linter ensuring prompts and instructions adhere to `GLOSSARY.md`.
- **`test_prompts_and_guidelines.py`**: Validates agent instructions, invariant enforcement, and prompt schemas.

### Running Tests

```bash
# Execute unittest discovery via uv
uv run python -m unittest discover -s tests -p "test_*.py"

# Or run with pytest
uv run pytest
```

---

## 4. Linting and Formatting

We use Ruff for linting and code formatting:

```bash
# Run lint checks
uv run ruff check .

# Fix auto-fixable lint issues
uv run ruff check --fix .

# Verify code formatting
uv run ruff format --check .

# Apply formatting
uv run ruff format .
```

---

## 5. Pre-Commit Guardrails

Execute `./scripts/check.sh` before committing:

```bash
./scripts/check.sh
```

A git pre-commit hook is also active and will execute `scripts/check.sh` automatically before allowing commits to be created.
