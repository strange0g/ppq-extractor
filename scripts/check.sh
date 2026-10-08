#!/usr/bin/env bash
set -euo pipefail

echo "==> Running PPQ Extractor Verification & Guardrail Suite..."

# 1. Run full unittest suite (including prompt guidelines & glossary linter)
echo "--> Running unittest suite..."
python3 -m unittest discover -s tests -p "test_*.py"

echo "==> All automated checks passed successfully!"
