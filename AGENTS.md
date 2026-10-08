## Pipeline Roles

The PPQ Extractor pipeline runs autonomously with two decoupled agent roles:

### Extractor Agent
- Responsible for converting an unworked Question Paper into rendered page images.
- Invokes multimodal vision LLM on content pages using [`prompts/vision_slicing.md`](file:///home/raied/Programming/ppq-extractor/prompts/vision_slicing.md) to locate question/part vertical bounds on a normalized `0–1000` vertical scale.
- Excises dotted, lined, or dashed answer workspace lines.
- Assembles per-paper `manifest.json` and invokes [`tools.crop_slices`](file:///home/raied/Programming/ppq-extractor/tools/crop_slices.py) to generate standalone Question Part Images and Composite Question Images.
- Updates queue status to `extracted` via [`tools.queue_manager`](file:///home/raied/Programming/ppq-extractor/tools/queue_manager.py).
- Detailed agent system instructions: [`prompts/extractor_agent.md`](file:///home/raied/Programming/ppq-extractor/prompts/extractor_agent.md).

### Verifier Agent
- Responsible for inspecting crops produced by the Extractor Agent against the source Question Paper pages.
- Audits mathematical mark-sum invariants against syllabus benchmarks (e.g. 75 marks for Pure 1/Pure 3, 50 marks for Mechanics/Stats).
- Performs page-by-page visual reconciliation to verify sequence completeness and ensure no mathematical symbols, exponents, or mark tags are clipped.
- Autonomously repairs coordinates in `manifest.json` and re-runs [`tools.crop_slices`](file:///home/raied/Programming/ppq-extractor/tools/crop_slices.py) when minor flaws exist.
- Approves verified papers or flags unresolvable defects as `needs_rework` via [`tools.queue_manager`](file:///home/raied/Programming/ppq-extractor/tools/queue_manager.py).
- Detailed agent system instructions: [`prompts/verifier_agent.md`](file:///home/raied/Programming/ppq-extractor/prompts/verifier_agent.md).

---

## Domain Grounding

All agents must strictly adhere to the domain terminology defined in [`GLOSSARY.md`](file:///home/raied/Programming/ppq-extractor/GLOSSARY.md).
Specifically:
- Use **Question Part Image** (e.g., `q01_a.png`), never "subpart snippet" or "partial crop".
- Use **Composite Question Image** (e.g., `q01_full.png`), never "merged image" or "stitched page".
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

3. **Full-Width Cropping & Stitching**:
   ```bash
   python3 -m tools.crop_slices --manifest <MANIFEST_JSON> --pages-dir <PAGES_DIR> --out-dir <CROPS_DIR>
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

Issues are tracked as local markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical triage roles mapped to issue status strings. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repository layout (`GLOSSARY.md` and `docs/adr/`). See `docs/agents/domain.md`.
