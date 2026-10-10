# Past Paper Question (PPQ) Extractor

An autonomous extraction and verification system for extracting past paper questions from Cambridge A-Level PDFs into structured image and metadata assets.

## Language

### Agents & Pipeline

**Extractor Agent**:
An autonomous agent responsible for converting an unworked Question Paper into images, locating question/part vertical bounds, cropping out questions while omitting blank answer workspace lines, and cataloging crops for verification.
_Avoid_: Parser agent, scraper agent

**Verifier Agent**:
An autonomous agent that inspects crops produced by the Extractor Agent against the source Question Paper pages, validating boundary accuracy, completeness of Question Parts, and lack of text clipping before marking the paper verified.
_Avoid_: Reviewer agent, auditor agent

**Processing Queue**:
The file-based asynchronous state ledger tracking each past paper through distinct pipeline states (`unprocessed`, `extracted`, `verified`, `needs_rework`).
_Avoid_: Job table, database queue

### Past Paper Domain

**Question Paper**:
A Cambridge examination paper containing question prompts, diagrams, and student working spaces (identified by `_qp_` in filename).
_Avoid_: Exam sheet, test booklet

**Question**:
A top-level numbered problem in a Question Paper (e.g., Question 1, Question 2) which may contain preamble and one or more Question Parts.
_Avoid_: Problem, item

**Question Part**:
A specific sub-component of a question denoted by letters or roman numerals (e.g., `(a)`, `(b)(i)`), carrying distinct mark allocations.
_Avoid_: Sub-question, subpart

**Question Preamble Image**:
An extracted image asset containing the introductory context, formulas, or diagrams of a question preceding the question parts (e.g., `preamble.png` under `questions/q{NN}/`).
_Avoid_: Stem crop, header snippet

**Question Part Image**:
An extracted image asset containing an individual Question Part (e.g., `part_a.png` under `questions/q{NN}/`), strictly isolating that specific sub-component without prepending the question preamble.
_Avoid_: Subpart snippet, partial crop

**Question Package**:
A structured bundle representing a complete question, encapsulating its Question Preamble Image, individual Question Part Images, and Composite Question Image (with metadata indexed in `manifest.json` and the unified SQLite database).
_Avoid_: Question folder, problem bundle

**Standalone Question**:
A question containing no divided Question Parts (e.g. an unpartitioned question carrying all marks directly). Stored as an isolated Question Package containing `full.png` (with metadata persisted in `manifest.json` and SQLite; legacy `question.json` deprecated) without separate preamble or part image files.
_Avoid_: Single problem, unpartitioned problem

**Composite Question Image**:
A stitched, unified image asset of an entire question (`full.png` under `questions/q{NN}/`). For multipart questions, contains all preamble and Question Parts tightly joined with student answer workspace excised. For Standalone Questions, contains the entire unpartitioned question.
_Avoid_: Merged image, stitched page

**Full-Width Crop**:
An extracted image slice that spans the full standardized horizontal page margins from left to right (normalized width 0 to 1000), maintaining consistent width across all output images while varying only in vertical height.
_Avoid_: Tight box, arbitrary crop

**Answer Workspace**:
The blank, dotted, or lined space reserved on an exam paper for candidate handwriting, which must be excised during extraction.
_Avoid_: Blank space, write area, dead zone

**Syllabus Topic Code**:
The official two-level hierarchical dot notation identifier (e.g., `1.1` for Quadratics, `1.7` for Differentiation) defined in the syllabus registry (`data/syllabus/<syllabus>.json`) linking Question Packages to curriculum topics.
_Avoid_: Chapter tag, subject category, math unit

**Margin Trimming**:
The automatic horizontal suppression of outer margin artifacts (such as vertical "DO NOT WRITE IN THIS MARGIN" warnings) during full-width image cropping without clipping mathematical content.
_Avoid_: Edge crop, side clipping, arbitrary margin cut

