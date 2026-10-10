#!/usr/bin/env bash
set -euo pipefail

echo "==> Running PPQ Extractor Verification & Guardrail Suite..."

# 1. Lint checks with ruff
echo "--> Running ruff linter..."
uv run ruff check .

# 2. Format checks with ruff
echo "--> Running ruff format check..."
uv run ruff format --check .

# 3. Run full unittest suite (including prompt guidelines & glossary linter)
echo "--> Running unittest suite..."
uv run python -m unittest discover -s tests -p "test_*.py"

echo "==> All automated checks passed successfully!"
