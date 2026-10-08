## Pipeline Roles

The PPQ Extractor pipeline runs autonomously with two decoupled agent roles operating in scheduled hourly containers (without nested LLM loops):

### Extractor Agent
- Responsible for converting an unworked Question Paper into rendered page images.
- Invokes multimodal vision capabilities on content pages using [`prompts/vision_slicing.md`](file:///home/raied/Programming/ppq-extractor/prompts/vision_slicing.md) to locate question/part vertical bounds on a normalized `0–1000` vertical scale.
- Enforces the question number invariant: `ymin` must strictly encompass top-level question numerals (e.g., bold "1", "2") with an upward safety buffer of at least 15 normalized units (~15px) so question numbers are never clipped or excised.
- Excises dotted, lined, or dashed answer workspace lines.
- Assembles per-paper `manifest.json` and invokes [`tools.crop_slices`](file:///home/raied/Programming/ppq-extractor/tools/crop_slices.py) to generate modular Question Packages (`questions/q{NN}/`) containing standalone Question Preamble Images (`preamble.png`), isolated Question Part Images (`part_{label}.png`), Composite Question Images (`full.png`), and atomic metadata descriptors (`question.json`).
- Updates queue status to `extracted` with `--extracted-marks` via [`tools.queue_manager`](file:///home/raied/Programming/ppq-extractor/tools/queue_manager.py).
- Detailed agent system instructions: [`prompts/extractor_agent.md`](file:///home/raied/Programming/ppq-extractor/prompts/extractor_agent.md).

### Verifier Agent
- Responsible for inspecting Question Packages produced by the Extractor Agent against the source Question Paper pages.
- Audits mathematical mark-sum invariants against syllabus benchmarks (e.g. 75 marks for Pure 1/Pure 3, 50 marks for Mechanics/Stats).
- Audits Question Packages for question number visibility (especially Question 1) to verify question numerals were not clipped or excised.
- Performs page-by-page visual reconciliation to verify sequence completeness and ensure no mathematical symbols, exponents, or mark tags are clipped.
- Validates the integrity of per-question `question.json` descriptors and the paper-level `manifest.json` index.
- Autonomously repairs coordinates in `manifest.json` (applying upward safety buffers) and re-runs [`tools.crop_slices`](file:///home/raied/Programming/ppq-extractor/tools/crop_slices.py) when minor flaws exist.
- Approves verified papers or flags unresolvable defects as `needs_rework` via [`tools.queue_manager`](file:///home/raied/Programming/ppq-extractor/tools/queue_manager.py).
- Detailed agent system instructions: [`prompts/verifier_agent.md`](file:///home/raied/Programming/ppq-extractor/prompts/verifier_agent.md).

---

## Domain Grounding

All agents must strictly adhere to the domain terminology defined in [`GLOSSARY.md`](file:///home/raied/Programming/ppq-extractor/GLOSSARY.md).
Specifically:
- Use **Question Package** (e.g., `questions/q01/` with `question.json`), never "question folder" or "problem bundle".
- Use **Question Preamble Image** (e.g., `preamble.png`), never "stem crop" or "header snippet".
- Use **Question Part Image** (e.g., `part_a.png`), never "subpart snippet" or "partial crop".
- Use **Composite Question Image** (e.g., `full.png`), never "merged image" or "stitched page".
- Use **Full-Width Crop** (width 0 to 1000 normalized), never "tight box" or "arbitrary crop".
- Use **Answer Workspace**, never "dead zone" or "blank area".
- Use **Processing Queue** (`.pipeline/queue.json`), never "job table" or "database queue".

---

## CLI Tooling Commands Reference

Agents must use the deterministic CLI tools provided in the repository instead of writing ad-hoc scripts:

1. **Queue Management**:
   ```bash
   # Poll next paper for extractor or verifier
   python3 -m tools.queue_manager next --role {extractor,verifier}

   # Update paper status in the queue ledger
   python3 -m tools.queue_manager update --id <PAPER_ID> --status {extracted,verified,needs_rework} [--notes "<NOTES>"] [--extracted-marks <MARKS>]

   # Scan directory to discover Question Papers
   python3 -m tools.queue_manager scan --source-dir <DIR>
   ```

2. **High-Speed PDF Rendering**:
   ```bash
   python3 -m tools.pdf_to_images --pdf <SOURCE_PDF> --out-dir <OUTPUT_DIR>/pages --dpi 200
   ```

3. **Full-Width Cropping & Question Package Generation**:
   ```bash
   python3 -m tools.crop_slices --manifest <MANIFEST_JSON> --pages-dir <PAGES_DIR> --out-dir <OUTPUT_DIR>
   ```
   Outputs Question Packages under `<OUTPUT_DIR>/questions/q{NN}/`:
   - `preamble.png` (optional stem context)
   - `part_{label}.png` (isolated Question Part Images)
   - `full.png` (Composite Question Image)
   - `question.json` (atomic item metadata descriptor)

---

## Git Commit Guidelines

Autonomous runs must make atomic commits with conventional commit message prefixes:
- Extractor: `feat(extractor): extract <paper_id>`
- Verifier (approval): `feat(verifier): verify <paper_id>`
- Verifier (rework flag): `fix(verifier): flag <paper_id> needs_rework`

---

## Agent skills

### Issue tracker

Issues are tracked as local markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical triage roles mapped to issue status strings. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repository layout (`GLOSSARY.md` and `docs/adr/`). See `docs/agents/domain.md`.
