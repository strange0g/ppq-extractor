# Past Paper Question (PPQ) Extractor

An autonomous extraction and verification system for extracting past paper questions from Cambridge A-Level PDFs into structured image and metadata assets.

## Language

### Agents & Pipeline

**Extractor Agent**:
An autonomous agent responsible for converting an unworked Question Paper into images, locating question/part vertical bounds, cropping out questions while omitting blank answer workspace lines, and cataloging crops for verification.
_Avoid_: Parser agent, scraper agent

**Verifier Agent**:
An autonomous agent that inspects crops produced by the Extractor Agent against the source Question Paper pages, validating boundary accuracy, completeness of subparts, and lack of text clipping before marking the paper verified.
_Avoid_: Reviewer agent, auditor agent

**Processing Queue**:
The file-based asynchronous state ledger tracking each past paper through distinct pipeline states (`unprocessed`, `extracted`, `verified`, `needs_rework`).
_Avoid_: Job table, database queue

### Past Paper Domain

**Question Paper**:
A Cambridge examination paper containing question prompts, diagrams, and student working spaces (identified by `_qp_` in filename).
_Avoid_: Exam sheet, test booklet

**Question**:
A top-level numbered problem in a Question Paper (e.g., Question 1, Question 2) which may contain preamble and one or more subparts.
_Avoid_: Problem, item

**Question Part**:
A specific sub-component of a question denoted by letters or roman numerals (e.g., `(a)`, `(b)(i)`), carrying distinct mark allocations.
_Avoid_: Sub-question, subpart

**Question Part Image**:
An extracted image asset containing an individual subpart (e.g., `q01_a.png`), including any necessary shared preamble or context diagrams.
_Avoid_: Subpart snippet, partial crop

**Composite Question Image**:
A stitched, unified image asset of an entire question (`q01_full.png`) containing all preamble and subparts tightly joined with student answer workspace excised.
_Avoid_: Merged image, stitched page

**Full-Width Crop**:
An extracted image slice that spans the full standardized horizontal page margins from left to right (normalized width 0 to 1000), maintaining consistent width across all output images while varying only in vertical height.
_Avoid_: Tight box, arbitrary crop

**Answer Workspace**:
The blank, dotted, or lined space reserved on an exam paper for candidate handwriting, which must be excised during extraction.
_Avoid_: Blank space, write area, dead zone
