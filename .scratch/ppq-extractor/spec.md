# Specification: Past Paper Question (PPQ) Extractor

Status: ready-for-agent

## Problem Statement

Educators, students, and curriculum systems need access to modular past paper questions and subparts from Cambridge International A-Level examinations (starting with syllabus 9709). Currently, past examination papers are bundled as multi-page PDF documents where questions are interspersed with extensive blank or dotted answer workspaces (10–20 pages of handwriting lines introduced since 2017). Manually cropping each question, isolating individual subparts, stripping blank lined spaces, and verifying extraction accuracy across decades of papers is labor-intensive and error-prone.

Furthermore, autonomous coding agents run in stateless, hourly batches without persistent execution memory. Without a deterministic queue ledger, standardized image processing tools, and specialized prompt pairs (one for extraction, one for verification and repair), agents cannot reliably collaborate to extract and verify question assets at scale.

## Solution

A decoupled, autonomous extraction and verification architecture designed for scheduled execution. The repository provides:
1. A file-based processing queue tracking every Question Paper from discovery to verification.
2. Fast, deterministic command-line tools to render PDFs into high-resolution page images and perform standardized full-width vertical crops excising student answer workspaces.
3. An Extractor Agent prompt driving multimodal LLMs to identify vertical bounds $[ymin, 0, ymax, 1000]$ for preambles, questions, and parts.
4. A Verifier Agent prompt performing automated mathematical invariant validation (mark sum parity) and visual audits against source pages, with autonomous remediation capabilities.
5. Standardized output image assets: standalone question part images (with preambles attached) and stitched composite question images without handwriting lines, cataloged in structured per-paper manifests.

## User Stories

1. As an educator or student, I want each question subpart extracted as an individual image (`q01_a.png`, `q01_b.png`), so that I can practice specific sub-topics without seeing other parts.
2. As a student solving a subpart, I want the question preamble and context diagrams automatically included in my subpart image, so that I don't have to refer to a separate image to understand the problem stem.
3. As an educator compiling test papers, I want a composite question image (`q01_full.png`) containing the entire question tightly stitched together without handwriting lines, so that I can assemble compact problem sets.
4. As a user viewing question images, I want all cropped images to have uniform horizontal width spanning the entire page content, so that the visual presentation is clean and consistent across questions.
5. As an autonomous agent running without persistent session memory, I want a file-based master queue (`.pipeline/queue.json`), so that I can deterministically pick the next available paper without human coordination.
6. As an autonomous agent, I want papers flagged as `needs_rework` to take priority over new unprocessed papers, so that quality defects are resolved before new work begins.
7. As an Extractor Agent, I want a CLI command to render PDF pages to crisp 200 DPI PNG images using native system utilities, so that image extraction is fast and reliable.
8. As an Extractor Agent, I want a standardized multimodal prompt format to output vertical bounds on a 0–1000 scale, so that coordinate prediction is normalized and consistent across model architectures.
9. As an Extractor Agent, I want candidate handwriting lines and dotted answer grids excised automatically, so that the output contains only official question text, formulas, and diagrams.
10. As an Extractor Agent, I want the cover page instructions, blank pages, and "Additional Page" sections automatically excluded, so that no junk images pollute the question catalog.
11. As a Verifier Agent, I want an automated mark-sum verification check comparing total extracted marks against syllabus expectations (e.g., 75 marks for Pure 1, 50 marks for Mechanics), so that missing subparts are immediately identified.
12. As a Verifier Agent, I want to compare extracted question crops against the original rendered PDF pages, so that I can visually verify that no formulas, exponents, or diagrams were clipped.
13. As a Verifier Agent, I want the ability to autonomously adjust bounding coordinates in the manifest and regenerate crops when minor errors are found, so that human intervention is minimized.
14. As a repository maintainer, I want every agent session to commit its progress atomically with conventional commit messages, so that the git history provides a clean audit log of all extractions.
15. As a maintainer, I want the system architecture and directory layouts to be syllabus-parameterized, so that the pipeline can seamlessly expand from 9709 to other A-Level and IGCSE subjects in the future.

## Implementation Decisions

### 1. Master Ledger and Queue Schema
The queue resides at `.pipeline/queue.json` tracking papers through states: `unprocessed` ➔ `extracted` ➔ `verified` or `needs_rework`.
```json
{
  "version": "1.0",
  "summary": { "total": 0, "unprocessed": 0, "extracted": 0, "verified": 0, "needs_rework": 0 },
  "papers": [
    {
      "id": "9709_w24_qp_12",
      "syllabus": "9709",
      "year": 2024,
      "session": "w",
      "component": 1,
      "variant": 2,
      "source_pdf": "9709/2024/2024 Nov/9709_w24_qp_12.pdf",
      "status": "unprocessed",
      "total_pages": 20,
      "mode": "write_in",
      "expected_marks": 75,
      "output_dir": "data/extracted/9709/2024_w/12"
    }
  ]
}
```

### 2. High-Speed PDF Rendering Tool
- Module: `tools/pdf_to_images.py`.
- Invokes native `/usr/bin/pdftoppm -png -r 200` via Python standard library `subprocess`.
- Renders whole papers into `page_01.png`, `page_02.png`, etc., at 200 DPI in ~1 second with zero external library footprint.

### 3. Full-Width Slicing and Stitching Tool
- Module: `tools/crop_slices.py`.
- Reads `manifest.json`, source rendered page images, and generates crops into `crops/`.
- Slicing formula: $[y_1, 0, y_2, W]$ with configurable 10-pixel vertical buffer to preserve mathematical notation, fractions, and mark tags.
- Standalone Part Image Generation: Prepend shared stem preamble slices to subpart slices with a 20px clean margin.
- Composite Question Generation: Vertically stack preamble and all subparts, omitting answer workspace lines, separated by 20px padding.

### 4. Per-Paper Manifest Schema
- Stored at `data/extracted/<syllabus>/<year>_<session>/<variant>/manifest.json`.
- Records:
  - Component code, year, session, variant, total expected marks.
  - Array of questions with number, preamble bounds, part labels, part mark allocations, and slice definitions.
  - Verification block tracking approval timestamp, mark sum check, clipping check, and auditor notes.

### 5. Extractor Agent Runner & Vision Slicing Prompts
- System prompt at `prompts/extractor_agent.md` governing queue polling, CLI execution, and commit lifecycle.
- Multimodal LLM prompt at `prompts/vision_slicing.md` returning strict JSON with normalized $[ymin, 0, ymax, 1000]$ bounds and mark allocations, strictly excluding candidate answer lines.

### 6. Verifier Agent Runner & Remediation Prompt
- System prompt at `prompts/verifier_agent.md` governing audit checks (mark sum invariant, page reconciliation, clipping inspection) and self-repair capabilities (updating coordinates and re-invoking `tools/crop_slices.py`).

### 7. Agent Guidelines
- `AGENTS.md` at repository root defining pipeline roles, `GLOSSARY.md` adherence, CLI tooling mandates, and git conventions.

## Testing Decisions

### What Makes a Good Test
- Tests must verify external behavior through public CLI interfaces and file system outcomes, not internal helper functions.
- Tests will run against representative sample Cambridge past paper pages (both pre-2017 compact format and post-2017 write-in format).
- Tests must assert:
  1. PDF rendering produces valid PNGs with correct dimensions.
  2. Full-width cropping extracts exact bounding boxes with correct padding.
  3. Preamble concatenation produces an image containing both preamble and subpart.
  4. Composite question image matches the vertical sum of slices with answer lines stripped.
  5. Queue manager queries, claims, and updates paper states without corrupting the queue ledger.

### Modules Under Test
- `tests/test_pdf_to_images.py`: Validates PDF page image generation and return metadata.
- `tests/test_crop_slices.py`: Validates vertical slicing, padding, preamble prepending, and composite stitching.
- `tests/test_queue.py`: Validates queue scanning, state transitions, and priority ordering (`needs_rework` before `unprocessed`).

## Out of Scope

- Setting up external GitHub Actions cron jobs or cloud trigger runners.
- Building a frontend web UI or browser portal for students.
- Mark Scheme (`_ms_`) solution extraction and answer pairing (reserved for future milestone).
- Topic taxonomy and syllabus classification tagging.
- Model fine-tuning or training.

## Further Notes

- All code must run on standard Python 3.10+ using Pillow and system `pdftoppm` without requiring heavyweight machine learning frameworks.
- The pipeline begins with syllabus `9709` (Cambridge A-Level Mathematics) but the schemas and directory hierarchies are agnostic to syllabus code.
