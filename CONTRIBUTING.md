# Contributing to PPQ Extractor

Thank you for contributing to **PPQ Extractor**! This guide outlines our development workflow, coding standards, domain terminology rules, and quality assurance procedures.

---

## Code of Conduct & Core Invariants

1. **Strict Domain Language**: All code, documentation, test cases, and commits must adhere strictly to the terminology codified in [`GLOSSARY.md`](GLOSSARY.md). Never introduce colloquial synonyms (e.g. use **Question Package**, never "question folder" or "problem bundle"; use **Answer Workspace**, never "dead zone" or "blank area").
2. **Zero Functional Regressions**: All 42 baseline tests in `tests/` must pass unconditionally. Extraction logic, coordinate calculations, and prompt instructions must not be altered without explicit architectural review.
3. **Progressive Disclosure**: Documentation must start with concise, actionable summaries before delving into detailed technical mechanics.

---

## Development Setup

### 1. Requirements

- Python 3.10 or newer
- [`uv`](https://docs.astral.sh/uv/) (modern Python package and project manager)
- `poppler-utils` (system dependency for PDF rendering)

### 2. Initial Setup

```bash
# Clone the repository
git clone https://github.com/strange0g/ppq-extractor.git
cd ppq-extractor

# Create virtual environment and install dependencies
uv sync
```

---

## Quality Guardrails & Tooling

We enforce strict formatting, linting, and deterministic testing standards using `uv` and `ruff`.

### Linting & Formatting

We use [Ruff](https://docs.astral.sh/ruff/) configured via `pyproject.toml`:

```bash
# Run linter
uv run ruff check .

# Automatically fix lint issues where possible
uv run ruff check --fix .

# Check formatting without modifying files
uv run ruff format --check .

# Automatically reformat files
uv run ruff format .
```

### Running Tests

We maintain comprehensive unit and end-to-end tests covering PDF rendering, coordinate translation, composite stitching, queue operations, and prompt invariants:

```bash
# Run unittest discovery via uv
uv run python -m unittest discover -s tests -p "test_*.py"

# Alternatively run with pytest
uv run pytest
```

### Master Verification Suite

Before submitting a pull request or pushing commits, execute the unified check script:

```bash
./scripts/check.sh
```

This script verifies:
1. Ruff linting checks pass with zero errors.
2. Ruff formatting checks pass.
3. Full test suite executes and passes 100% of tests.

---

## Conventional Commits

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification. Commits should use descriptive scopes reflecting the subsystem or role modified:

- `feat(extractor): extract <paper_id>` — Autonomous extractor agent operations.
- `feat(verifier): verify <paper_id>` — Verifier agent audits and approvals.
- `fix(verifier): flag <paper_id> needs_rework` — Rejection or defect identification.
- `feat(project): ...` / `feat(quality): ...` — Tooling and configuration additions.
- `docs: ...` — Human or agent documentation updates.
- `test: ...` — New test cases or test framework updates.
- `refactor: ...` — Code restructuring that does not change external behavior.

---

## Pull Request Guidelines

1. **Single Responsibility**: Keep changes focused on a single concern or ticket.
2. **Include Tests**: Any bug fix or feature addition must include accompanying tests under `tests/`.
3. **Clean Diffs**: Ensure no temporary test artifacts, `.pyc` files, or rogue images are checked in.
4. **Green Checks**: Ensure `./scripts/check.sh` passes cleanly before requesting review.
