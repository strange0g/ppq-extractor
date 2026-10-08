# Wayfinder Map: PPQ Extractor

## Destination

A complete repository architecture, Python toolset, state tracking harness, and two autonomous prompts (Extractor Agent and Verifier Agent) enabling scheduled agents to extract, crop, stitch, verify, and catalog Cambridge past paper questions (starting with syllabus 9709) into uniform standalone part images, composite question images, and structured metadata manifests without blank answer workspaces.

## Notes

- **Domain**: Cambridge International A-Level Mathematics (Syllabus 9709) examination papers, architected to scale to other syllabus codes. See [`GLOSSARY.md`](file:///home/raied/Programming/ppq-extractor/GLOSSARY.md).
- **Execution Model**: Disconnected autonomous agents running on hourly schedules (12 extractor runs, 12 verifier runs per day), communicating asynchronously exclusively through git-tracked file queues.
- **Multimodal Coordinate Space**: Normalized [ymin, xmin, ymax, xmax] coordinates on a 0–1000 scale, with horizontal bounds standardized to full page width.
- **Skills to Consult**: `domain-modeling`, `codebase-design`, `research`, `writing-for-agents`.

## Decisions so far

<!-- the index: one line per closed ticket -->

- [01: Cambridge Paper Structure and Layout Research](file:///home/raied/Programming/ppq-extractor/.scratch/ppq-extractor/wayfinder-issues/01-cambridge-paper-structure-research.md): Identified 2017 transition from 4-page question booklets to 12-20 page write-in booklets with dotted lines, 2020 component renumbering, header/footer boundary safety ranges, and mark sum verification rules.
- [02: Pipeline State and Queue Schema](file:///home/raied/Programming/ppq-extractor/.scratch/ppq-extractor/wayfinder-issues/02-pipeline-state-and-queue-schema.md): Established directory layout, master queue schema (`.pipeline/queue.json`), and per-paper manifest schema (`manifest.json`) for decoupled Extractor/Verifier agent state transitions.
- [03: PDF and Image Processing Tools](file:///home/raied/Programming/ppq-extractor/.scratch/ppq-extractor/wayfinder-issues/03-pdf-and-image-processing-tools.md): Selected system `pdftoppm` for rendering and Pillow for full-width slicing, vertical padding (+10px), preamble concatenation, and composite question stitching.
- [04: Extractor Agent System Prompt](file:///home/raied/Programming/ppq-extractor/.scratch/ppq-extractor/wayfinder-issues/04-extractor-agent-prompt.md): Designed autonomous runner protocol (rework prioritization, CLI invocation, commit flow) and multimodal vision prompt for [ymin, 0, ymax, 1000] detection excising answer lines.
- [05: Verifier Agent System Prompt](file:///home/raied/Programming/ppq-extractor/.scratch/ppq-extractor/wayfinder-issues/05-verifier-agent-prompt.md): Designed autonomous audit protocol including mathematical mark-sum invariant verification, visual clipping checks, automated remediation loop, and approval transitions.
- [06: Autonomous Agent Repository Guidelines and AGENTS.md](file:///home/raied/Programming/ppq-extractor/.scratch/ppq-extractor/wayfinder-issues/06-agents-instructions-and-repo-guidelines.md): Specified AGENTS.md operational guidelines, queue discipline, deterministic tool mandates, and `prompts/` storage convention.
- [Impl 01: PDF to High-Resolution Page Image Tool](file:///home/raied/Programming/ppq-extractor/.scratch/ppq-extractor/issues/01-pdf-to-high-res-page-images.md): Implemented `tools.pdf_to_images` wrapping `pdftoppm -png -r 200` with zero-padded naming, skip-rendering, and page dimensions extraction.
- [Impl 02: Full-Width Slicing and Composite Stitching Tool](file:///home/raied/Programming/ppq-extractor/.scratch/ppq-extractor/issues/02-full-width-slicing-and-stitching.md): Implemented `tools.crop_slices` with full-width horizontal forcing, +10px safety padding, preamble attachment, answer line excision, composite question generation, and multi-slice preamble support.
- [Impl 03: Master Queue Ledger & Pipeline Manager](file:///home/raied/Programming/ppq-extractor/.scratch/ppq-extractor/issues/03-master-queue-and-discovery-ledger.md): Implemented `tools.queue_manager` providing paper scanning, metadata extraction, atomic queue state transitions (`unprocessed` -> `extracted` -> `verified`/`needs_rework`), role prioritization (`needs_rework` before `unprocessed`), and syllabus parameterization.
- [Impl 04: Autonomous Prompts Suite & AGENTS.md Guidelines](file:///home/raied/Programming/ppq-extractor/.scratch/ppq-extractor/issues/04-autonomous-prompts-and-agents-guidelines.md): Authored `prompts/extractor_agent.md`, `prompts/vision_slicing.md`, `prompts/verifier_agent.md`, and updated root `AGENTS.md` enforcing GLOSSARY domain terminology, CLI mandates, and git conventions.
- [Impl 05: End-to-End Pipeline Dry Run & Verification](file:///home/raied/Programming/ppq-extractor/.scratch/ppq-extractor/issues/05-end-to-end-pipeline-dry-run.md): Executed complete end-to-end verification against Cambridge 9709 paper (`9709_w24_qp_12.pdf`), validating 20 rendered pages, 10 questions/parts, 75 mark sum invariant, and queue status transition.

## Not yet specified

<!-- Fog of war: in-scope fog not yet sharp enough to ticket -->

- **Mark Scheme Pairing**: Slicing and associating mark scheme solutions (`_ms_*.pdf`) with extracted question items.
- **Topic & Syllabus Taxonomy Tagging**: Categorizing extracted questions by topic (e.g., Quadratics, Integration, Vectors, Mechanics, Normal Distribution).
- **LaTeX / Text Extraction**: Extracting raw text and mathematical notation alongside image crops.
- **Multi-Subject Expansion Harness**: Automated syllabus registry for ingesting subjects beyond 9709 (Physics 9702, Chemistry 9701, etc.).

## Out of scope

- **External Runner Infrastructure**: GitHub Actions cron runners and cloud trigger orchestration (managed externally by user).
- **Frontend / Question Browser**: Interactive UI or web portal for viewing extracted questions.
- **Vision Model Training / Fine-Tuning**: Custom weights training (pipeline relies on off-the-shelf multimodal LLMs).
