# Standalone Question Package Architecture and Invariant Synchronization

We refine the Question Package specification to treat Standalone Questions without subparts as atomic single-asset packages containing `full.png` and `question.json` (eliminating redundant `part.png` and `preamble.png` files), and mandate that all agent workflows and prompt templates remain strictly synchronized with the canonical `uv run` tooling workflow.

## Context & Problem

1. **Redundant Duplicate Crops in Standalone Questions**:
   Under the initial implementation of the two-tier Question Package model (ADR 0001), standalone whole questions without subparts produced identical duplicates: both `part.png` and `full.png` were saved with the exact same pixel data. This introduced unnecessary disk usage and visual ambiguity for downstream applications.
2. **Premature Standalone Question Slicing**:
   When vision agents sliced standalone questions with figures, there was a risk of cutting `ymax` immediately below the diagram, inadvertently lopping off the remaining textual question instruction and right-margin mark bracket `[X]` before the candidate answer workspace lines began.
3. **Workflow Drift between Prompts and Governance**:
   `AGENTS.md` mandates `uv run` for all Python tooling, but prompt markdown templates contained legacy `python3 -m tools.` commands, creating inconsistency during autonomous execution.

## Decision

1. **Atomic Standalone Question Package**:
   - When a Question has no divided parts (`kind: "whole"` or a single unpartitioned problem), the resulting Question Package under `questions/q{NN}/` contains only `full.png` and `question.json`.
   - No redundant `part.png` or `preamble.png` is generated.
   - Multipart questions continue to generate isolated `part_{label}.png`, `preamble.png` (if introductory stem exists), and composite `full.png`.
2. **Standalone Question Bottom-Bounding Invariant**:
   - For standalone questions, `ymax` MUST strictly extend below all diagrams and formulas to capture the full prompt text and the right-margin mark bracket `[X]` before candidate answer lines begin.
3. **Mandatory Workflow Synchronization**:
   - All prompt templates (`prompts/extractor_agent.md`, `prompts/verifier_agent.md`, etc.) must exclusively use canonical `uv run` commands (`uv run ppq-queue`, `uv run ppq-render`, `uv run ppq-crop`).
   - `AGENTS.md` explicitly codifies that any future changes to scripts, tools, or entrypoints must be simultaneously reflected across all agent prompts and guarded by automated tests.

## Consequences

- Standalone question packages are cleaner, eliminating 50% of unnecessary image files for single-problem questions.
- Downstream applications maintain a uniform contract: every Question Package (`questions/q{NN}/`) always contains `full.png` representing the entire problem.
- Automated tests enforce that prompt templates cannot drift from the `uv run` workflow.
