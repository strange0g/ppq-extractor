# Agent Operating System & Governance

This document governs autonomous agents operating in [`ppq-extractor`](file:///home/raied/Programming/ppq-extractor). It specifies operating rules, domain grounding, pipeline roles, tooling commands, and agent skill integration.

---

## Operating Rules & Invariants

1. **Canonical Tooling (`uv`)**:
   - Always run Python commands and scripts via `uv run` (e.g. `uv run ppq-queue`, `uv run python -m unittest`).
   - Never invoke ad-hoc pip commands or global python interpreters directly.
2. **Quality Guardrails**:
   - Execute `./scripts/check.sh` before completing any code changes.
   - All 84 deterministic tests must pass with zero functional regressions.
3. **Strict Domain Language**:
   - Adhere strictly to the canonical vocabulary in [`GLOSSARY.md`](GLOSSARY.md).
   - Use **Question Package** (`questions/q{NN}/`), never "question folder" or "problem bundle".
   - Use **Question Preamble Image** (`preamble.png`), never "stem crop" or "header snippet".
   - Use **Question Part Image** (`part_{label}.png`), never "subpart snippet" or "partial crop".
   - Use **Composite Question Image** (`full.png`), never "merged image" or "stitched page".
   - Use **Full-Width Crop** (width 0 to 1000 normalized), never "tight box" or "arbitrary crop".
   - Use **Answer Workspace**, never "dead zone" or "blank area".
   - Use **Processing Queue** (`.pipeline/queue.json`), never "job table" or "database queue".
   - Use **Syllabus Topic Code** (e.g. `1.1`, `1.7`), never "chapter tag" or "math unit".
   - Use **Margin Trimming**, never "edge crop" or "side clipping".
4. **Question Numeral Invariant**:
   - When extracting vertical coordinates, `ymin` must strictly encompass top-level question numerals (e.g. bold "1", "2") with an upward safety buffer of at least 15 normalized units (~15px) so question numbers are never clipped or excised.
5. **No Nested LLM Loops**:
   - Agents run in scheduled hourly autonomous containers without spawning unmanaged inner LLM API loops.
6. **Workflow & Prompt Synchronization**:
   - Any changes to execution tools, scripts, CLI flags, or workflows (such as canonical `uv run` commands) must be kept strictly synchronized across [`AGENTS.md`](AGENTS.md), [`prompts/extractor_agent.md`](prompts/extractor_agent.md), [`prompts/verifier_agent.md`](prompts/verifier_agent.md), and [`prompts/vision_slicing.md`](prompts/vision_slicing.md). Prompt files must never use legacy bare interpreters or unsynchronized command flags.
7. **Strict Wayfinder Invariant (Planning, Not Doing)**:
   - When operating in or managing a Wayfinder session (any session referencing a `wayfinder:map` or working a `wayfinder:*` ticket), agents must strictly produce decisions, not deliverables.
   - Writing production implementation code, editing application tools/modules, or modifying production database tables inside a Wayfinder session is strictly forbidden.
   - Every ticket resolves to an architectural or domain decision recorded in an issue comment, never code merged into `main`.
   - `wayfinder:task` tickets are strictly for prerequisite discovery/unblocking legwork, never implementation work.
   - An agent must never declare a map complete or suggest transitioning to downstream phases (`/spec`, `/tickets`, `/implement`) while any child ticket on the frontier remains open.
   - When all tickets are resolved and fog is cleared, hand off to the engineering flow: `/to-spec` -> `/to-tickets` -> `/implement`.
8. **Continuous Documentation Synchronization**:
   - Whenever code, database schemas, CLI commands or flags, domain terminology, or architectural flows are modified or introduced, all relevant documentation files must be updated in lockstep within the same commit/PR.
   - Specifically ensure synchronization across:
     - [`README.md`](README.md): system overview, directory layout, quickstart commands, and CLI references.
     - [`docs/architecture.md`](docs/architecture.md) & [`docs/development.md`](docs/development.md): dataflow diagrams, test suite breakdowns, and usage flags.
     - [`docs/adr/`](docs/adr/): document non-trivial architectural decisions with a new ADR.
     - [`prompts/`](prompts/): extractor, verifier, and vision slicing system prompts.
   - Code changes that alter observable behavior, commands, or data models must never be finalized without updating their corresponding documentation.

---

## Documentation Index & Progressive Disclosure

Agents must navigate the repository using context pointers rather than loading unneeded files into context:

- [`README.md`](README.md): System overview, quick start, and directory structure.
- [`CONTRIBUTING.md`](CONTRIBUTING.md): Developer workflow, formatting, and pull request conventions.
- [`docs/architecture.md`](docs/architecture.md): Deep-dive pipeline lifecycle, two-tier Question Package model, coordinate spaces, and margin trimming.
- [`docs/development.md`](docs/development.md): CLI reference flags, test suite breakdown, and developer tools.
- [`GLOSSARY.md`](GLOSSARY.md): Authoritative domain definitions and terminology rules.
- [`docs/adr/`](docs/adr/): Architectural Decision Records (`0001` Question Package layout, `0002` Syllabus taxonomy & margin trimming, `0003` Standalone Question Packages & workflow sync, `0004` Unified relational database & asset storage).

---

## Pipeline Roles

The extraction pipeline runs autonomously with two decoupled agent roles:

### Extractor Agent
- Converts an unworked Question Paper PDF into rendered page images via `ppq-render` / `tools.pdf_to_images`.
- Invokes multimodal vision capabilities on content pages using [`prompts/vision_slicing.md`](prompts/vision_slicing.md) to locate question/part vertical bounds on a normalized `0–1000` vertical scale.
- Enforces the question number invariant: `ymin` strictly encompasses question numerals with an upward safety buffer of at least 15 normalized units (~15px).
- Excises dotted, lined, or dashed answer workspace lines.
- Assembles per-paper `manifest.json` and runs `ppq-crop` / `tools.crop_slices` to generate modular Question Packages (`questions/q{NN}/`) containing pure media assets (standalone Question Preamble Images `preamble.png`, isolated Question Part Images `part_{label}.png`, Composite Question Images `full.png`) and automatically synchronizes manifest records into the SQLite database. Legacy `question.json` descriptors are deprecated by default.
- Updates queue status to `extracted` with `--extracted-marks` via `ppq-queue` / `tools.queue_manager`.
- Detailed system instructions: [`prompts/extractor_agent.md`](prompts/extractor_agent.md).

### Verifier Agent
- Inspects Question Packages produced by the Extractor Agent against source Question Paper pages.
- Audits mathematical mark-sum invariants against syllabus benchmarks (e.g. 75 marks for Pure 1/Pure 3, 50 marks for Mechanics/Stats).
- Audits Question Packages for question number visibility (especially Question 1) to verify question numerals were not clipped or excised.
- Performs page-by-page visual reconciliation to verify sequence completeness and ensure no mathematical symbols, exponents, or mark tags are clipped.
- Validates the integrity of paper-level `manifest.json` and SQLite synchronization (noting legacy per-question `question.json` descriptors are deprecated in favor of unified database indexing).
- Autonomously repairs coordinates in `manifest.json` (applying upward safety buffers) and re-runs `tools.crop_slices` (which idempotently re-syncs database tables and regenerates image crops) when minor flaws exist.
- Approves verified papers or flags unresolvable defects as `needs_rework` via `tools.queue_manager`.
- Detailed system instructions: [`prompts/verifier_agent.md`](prompts/verifier_agent.md).

---

## CLI Tooling Commands Reference

Agents must execute the canonical CLI entry points via `uv run` instead of writing ad-hoc scripts:

1. **Queue Management (`tools.queue_manager`)**:
   ```bash
   # Poll next paper for extractor or verifier
   uv run ppq-queue next --role {extractor,verifier}
   python3 -m tools.queue_manager next --role {extractor,verifier}

   # Show details of a paper in the queue ledger
   uv run ppq-queue show --id <PAPER_ID>
   python3 -m tools.queue_manager show --id <PAPER_ID>

   # Update paper status in the queue ledger
   uv run ppq-queue update --id <PAPER_ID> --status {extracted,verified,needs_rework} [--notes "<NOTES>"] [--extracted-marks <MARKS>]
   python3 -m tools.queue_manager update --id <PAPER_ID> --status {extracted,verified,needs_rework} [--notes "<NOTES>"] [--extracted-marks <MARKS>]

   # Scan directory to discover Question Papers
   uv run ppq-queue scan --source-dir <DIR>
   python3 -m tools.queue_manager scan --source-dir <DIR>
   ```

2. **High-Speed PDF Rendering (`tools.pdf_to_images`)**:
   ```bash
   uv run ppq-render --pdf <SOURCE_PDF> --out-dir <OUTPUT_DIR>/pages --dpi 200
   python3 -m tools.pdf_to_images --pdf <SOURCE_PDF> --out-dir <OUTPUT_DIR>/pages --dpi 200
   ```

3. **Full-Width Cropping & Question Package Generation (`tools.crop_slices`)**:
   ```bash
   uv run ppq-crop --manifest <MANIFEST_JSON> --pages-dir <PAGES_DIR> --out-dir <OUTPUT_DIR> [--db-path <DB_PATH>]
   python3 -m tools.crop_slices --manifest <MANIFEST_JSON> --pages-dir <PAGES_DIR> --out-dir <OUTPUT_DIR> [--db-path <DB_PATH>]
   ```
   Outputs Question Packages under `<OUTPUT_DIR>/questions/q{NN}/`:
   - `preamble.png` (optional stem context)
   - `part_{label}.png` (isolated Question Part Images)
   - `full.png` (Composite Question Image)
   - `question.json` (deprecated by default, available via `--emit-question-json`)

4. **Curriculum Topic & Question Querying (`tools.db.repository`)**:
   ```bash
   # Query questions by Syllabus Topic Code
   uv run python -m tools.db.repository query --topic 1.1 --component 1 --format table
   uv run ppq-queue query --topic 1.1 --component 1 --format table

   # Query Question Parts by Syllabus Topic Code
   uv run python -m tools.db.repository query --topic 1.1 --parts --format json
   uv run ppq-queue query --topic 1.1 --parts --format json
   ```

---

## Git Commit Guidelines

Autonomous runs must make atomic commits with conventional commit message prefixes:
- Extractor: `feat(extractor): extract <paper_id>`
- Verifier (approval): `feat(verifier): verify <paper_id>`
- Verifier (rework flag): `fix(verifier): flag <paper_id> needs_rework`

---

## Agent skills

### Issue tracker

Issues are tracked as GitHub issues via `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical triage roles mapped to issue status strings. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repository layout (`GLOSSARY.md` and `docs/adr/`). See `docs/agents/domain.md`.
