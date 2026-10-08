# Specification: Modular Question Packages and Decoupled Extraction Pipeline

Status: ready-for-agent

## Problem Statement

Educators, students, and curriculum applications extracting past paper questions from Cambridge A-Level examinations (starting with syllabus 9709) face multiple critical defects in the current extraction model:
1. When multi-part questions have shared introductory diagrams or formulas (e.g. Question 10), the shared preamble is redundantly pasted onto every individual question part image (`q10_a.png`, `q10_b.png`). This causes massive storage waste, visual token bloat in vision LLMs, and visual clutter when practicing consecutive parts.
2. In initial test extractions, question numbers were accidentally excised (e.g. Question 1 omitted the numeral "1") because the bounding box started below the question heading.
3. Assets are dumped into flat image folders with anonymous filenames and nested under cryptic directory codes (`data/extracted/9709/2024_w/12`), making it impossible for humans to immediately recognize the exam session and lacking item-level machine-readable metadata for downstream question banks and RAG systems.
4. The orchestration prompt contained a conceptual misunderstanding implying an inner LLM API loop inside each prompt, whereas the autonomous pipeline is designed for top-level scheduled agent sessions running hourly in isolated environments.

## Solution

An upgraded, two-tier Question Package extraction architecture adhering to assessment standards (IMS Global QTI 3.0) and CAIE taxonomy:
1. **Decoupled Preamble and Parts**: Crop question stems/diagrams once into `preamble.png`, crop subparts strictly in isolation into `part_{label}.png`, and generate a tightly stitched composite `full.png` with student answer workspaces excised.
2. **Two-Tier Question Packages**: Package each question into a dedicated folder `questions/q{NN}/` containing its image assets and an atomic `question.json` item descriptor declaring marks, diagram flags, and context dependencies (`dependencies: ["preamble"]`), indexed by a whole-paper `manifest.json`.
3. **Chronological CAIE Directory Taxonomy**: Standardize paper directory structures to human-readable paths: `data/extracted/<syllabus>/<year>/<session>/paper_<paper_code>/` (e.g. `data/extracted/9709/2024/oct_nov/paper_12/`).
4. **Guaranteed Question Number Invariant**: Enforce strict vertical upper bounds ensuring `ymin` encompasses question numerals with an upward margin buffer.
5. **Decoupled Hourly Autonomous Agents**: Re-architect Extractor and Verifier system prompts for standalone execution in scheduled hourly batches across isolated environments, where the Extractor creates and populates the paper's Question Packages and the Verifier audits mark sums, inspects visual completeness, and repairs coordinates.

## User Stories

1. As a student practicing a specific subpart, I want Question Part Images (`part_a.png`, `part_b.png`) to contain strictly the subpart prompt and marks without the stem diagram repeated on top, so that I can focus solely on that sub-problem without visual clutter.
2. As an interactive assessment frontend, I want an atomic `question.json` linking each subpart to its parent `preamble.png`, so that I can dynamically render the shared diagram once above whatever subpart the student is attempting.
3. As an AI researcher evaluating multimodal models on math benchmarks, I want question stems separated from subparts, so that I can cache the high-resolution preamble image tokens in prompt-caching systems and pass only the active subpart in subsequent turns.
4. As an educator compiling printed worksheets, I want a composite Question Image (`full.png`) containing the preamble and all subparts joined seamlessly without student handwriting lines, so that I can generate compact problem sets in a single glance.
5. As a student reviewing an extracted question, I want the top-level question number (e.g. bold "1", "2") clearly visible at the top of the question, so that I always know which exam problem I am solving.
6. As a curriculum developer browsing the repository, I want papers filed under explicit chronological session folders (`data/extracted/9709/2024/oct_nov/paper_12/`), so that I immediately understand the exam sitting without decoding single-letter session acronyms.
7. As a downstream question bank service, I want each Question Package to be self-contained in its own directory (`questions/q01/`), so that I can index, ingest, or export individual questions without parsing an entire multi-page exam paper.
8. As a Verifier Agent, I want a paper-level `manifest.json` indexing all questions and recording total extracted marks alongside expected marks, so that I can perform an $O(1)$ mark-sum invariant audit before inspecting image pixels.
9. As a Verifier Agent, I want the ability to edit bounding coordinates in `manifest.json` or `question.json` and re-run the cropping tool to fix misaligned crops autonomously, so that human intervention is eliminated for minor slicing flaws.
10. As an Extractor Agent running on an hourly schedule in an isolated container, I want clear system instructions to poll the queue, render PDF pages, inspect layouts directly with multimodal vision, generate Question Packages via deterministic CLI tools, and commit assets atomically.
11. As a Verifier Agent running in the subsequent scheduled hourly session, I want clear system instructions to claim the extracted paper, audit mathematical mark sums, verify visual continuity against source pages, commit any fixes, and update the queue status to verified.
12. As a repository maintainer, I want all queue transitions and paper attributes tracked deterministically in `.pipeline/queue.json`, so that state handoffs between decoupled hourly agent sessions require no shared memory.

## Implementation Decisions

### 1. Two-Tier Question Package On-Disk Hierarchy
Each Question Paper directory will be structured as:
```text
data/extracted/<syllabus>/<year>/<session>/paper_<paper_code>/
├── manifest.json
├── pages/
│   ├── page_01.png
│   └── ...
└── questions/
    ├── q01/
    │   ├── question.json
    │   ├── preamble.png          (omitted if question has no preamble)
    │   ├── part_a.png
    │   ├── part_b.png
    │   └── full.png
    └── q02/
        ├── question.json
        ├── part_a.png
        └── full.png
```

### 2. Item-Level Metadata Schema (`question.json`)
Every question package contains a `question.json` file specifying:
- `id`: Globally unique question ID (e.g., `9709_w24_qp_12_q01`)
- `paper_id`: Identifier of the source paper
- `question_number`: Integer question number
- `total_marks`: Total mark allocation for the entire question
- `preamble`: Object with `present: bool`, `asset_path`, `dimensions`, and `slices`
- `parts`: Array of subparts with `part_id`, `label`, `marks`, `isolated_asset_path`, `slices`, and `context_dependencies: ["preamble"]`
- `composite`: Object with `asset_path` (`full.png`) and `dimensions`
- `taxonomy`: Metadata fields for syllabus topics and diagram presence

### 3. Paper-Level Manifest Schema (`manifest.json`)
The root manifest records:
- `id`: Unique paper identifier (e.g. `9709_w24_qp_12`)
- `provenance`: Syllabus code, title, year, session, session name, component, variant, source PDF path
- `verification`: Status (`unprocessed`, `extracted`, `verified`, `needs_rework`), expected marks, extracted marks total, balance check, verifier notes
- `pages_processed`: Array of physical page indices analyzed
- `question_index`: Array of summary objects pointing to each question package (`package_path: "questions/q01/question.json"`, `total_marks`, `composite_asset`)

### 4. Standard CAIE Directory Taxonomy
The queue manager and cropping tools will construct output paths using explicit session naming:
- `m` $\rightarrow$ `feb_march`
- `s` $\rightarrow$ `may_june`
- `w` $\rightarrow$ `oct_nov`
Path pattern: `data/extracted/{syllabus}/{year}/{session_slug}/paper_{paper_code}`.

### 5. Crop Slices Engine Refactoring (`tools/crop_slices.py`)
- Extract `preamble.png` once per question when `preamble_slices` or `preamble_slice` is defined.
- Stop concatenating preamble onto part images. Crop each subpart independently to `part_{label}.png`.
- Concatenate preamble and all subparts into `full.png` with 20px padding dividers.
- Output assets into per-question directories `questions/q{NN}/`.
- Write out both individual `question.json` files and the unified `manifest.json`.

### 6. Queue Manager Update (`tools/queue_manager.py`)
- Update output directory calculation to use the new taxonomy: `data/extracted/{syllabus}/{year}/{session_slug}/paper_{paper_code}`.
- Provide automatic path resolution and migration helpers for existing queue entries.

### 7. Agent System Prompts Modernization
- **`prompts/extractor_agent.md`**: Define the agent as the direct multimodal LLM acting in an isolated scheduled session: poll queue, render pages, perform visual layout analysis, execute `tools.crop_slices`, verify package generation, update queue, and commit.
- **`prompts/verifier_agent.md`**: Define the audit and repair agent acting in the subsequent hourly session: poll queue for `extracted` papers, audit mark sums, reconcile page sequences, inspect bounds for clipped question numbers, repair `manifest.json` / `question.json`, regenerate crops, update queue, and commit.
- **`prompts/vision_slicing.md`**: Mandate that `ymin` must encompass top-level question numerals and include a 15-pixel upward safety buffer.

## Testing Decisions

### What Makes a Good Test
Tests must verify external behavioral contracts via public CLI commands and disk state assertions, without inspecting internal private functions.

### Modules Tested
1. **`tools.crop_slices`**:
   - Verify generation of `questions/q{NN}/` directories.
   - Verify `preamble.png` is generated once and isolated from `part_*.png`.
   - Verify `full.png` stitches preamble and parts together.
   - Verify `question.json` and `manifest.json` schemas and cross-links.
2. **`tools.queue_manager`**:
   - Verify paper scanning maps CAIE filenames to the new directory taxonomy (`oct_nov`, `may_june`, `feb_march`).
   - Verify queue serialization, polling, and status transitions.
3. **End-to-End Pipeline**:
   - Full integration test processing a sample paper from PDF rendering through cropping and verification, asserting zero clipped question numbers and balanced mark sums.

### Prior Art
- Existing unit and integration tests in `tests/test_crop_slices.py`, `tests/test_queue.py`, and `tests/test_end_to_end_pipeline.py`.

## Out of Scope

- OCR text extraction or LaTeX mathematical formula conversion.
- Mark scheme (`_ms_`) or Examiner Report (`_er_`) extraction (deferred to future milestones).
- Automatic upload to external cloud object storage (S3/GCS) or remote LMS integration.

## Further Notes

- Architecture Decision Record recorded at `docs/adr/0001-question-package-and-decoupled-stem-architecture.md`.
- Canonical domain terminology defined in `GLOSSARY.md`.
