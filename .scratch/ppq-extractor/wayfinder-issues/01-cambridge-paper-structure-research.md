# Ticket 01: Cambridge Paper Structure and Layout Research

Type: research
Status: resolved

## Question

How has Cambridge International A-Level Mathematics (9709) Question Paper structure evolved across historical eras (especially pre-2020 question-only booklets vs. 2020+ write-in answer-space booklets), and what exact structural rules govern headers, footers, blank pages, question numbering, subpart designations, mark indicators (e.g. `[1]`, `[4]`), and diagrams across different components (Paper 1 Pure 1, Paper 2 Pure 2, Paper 3 Pure 3, Paper 4 Mechanics, Paper 5 Probability & Statistics 1, Paper 6 Probability & Statistics 2)?

## Answer

### 1. Historical Era Transition (Crucial Finding: 2017 Cutover)

Primary source inspection across `9709/` (2001–2025) reveals two distinct architectural eras:
1. **Pre-2017 Era (2001–2016) — Compact Question-Only Booklets**:
   - Total pages: **4 to 6 pages**.
   - Characteristics: Candidates were provided separate answer paper booklets. The question paper contains **zero blank answer lines**. Questions immediately follow one another with tight vertical spacing.
   - Slicing implication: Extraction only needs to separate adjacent questions/subparts without excising interior answer lines.
2. **Post-2017 Era (2017–Present) — Write-in Question & Answer Booklets**:
   - Total pages: **12 to 24 pages** (typically 12 for 50-mark papers like P4/P5/P6; 16–20 for 75-mark papers like P1/P3).
   - Characteristics: Each question has dedicated ruled/dotted answer workspace (`......................................................................`).
   - Slicing implication: The multimodal vision extractor **must excise** this answer workspace between questions and subparts.

### 2. Syllabus & Component Structure Evolution (2020 Reform)

- **2002–2019 Components**: 7 papers:
  - P1: Pure 1 (75 marks, 10–12 questions)
  - P2: Pure 2 (50 marks, 7–8 questions)
  - P3: Pure 3 (75 marks, 10–11 questions)
  - P4: Mechanics 1 (50 marks, 7 questions)
  - P5: Mechanics 2 (50 marks) — *discontinued post-2019*
  - P6: Probability & Statistics 1 (50 marks, 7 questions) — *renumbered to P5 in 2020*
  - P7: Probability & Statistics 2 (50 marks, 7 questions) — *renumbered to P6 in 2020*
- **2020–Present Components**: 6 active papers:
  - P1 (Pure 1), P2 (Pure 2), P3 (Pure 3), P4 (Mechanics), P5 (Stats 1), P6 (Stats 2).
- Filename pattern: `9709_<s|w|m><yy>_qp_<component><variant>.pdf` (e.g. `9709_s24_qp_12.pdf`).

### 3. Page Layout Anatomy & Elements

On any modern post-2017 Question Paper:
1. **Page 1 (Cover Page)**:
   - Header barcode `* 0000800000001 *`, Candidate Name / Centre Number blocks.
   - Standard instructions ("Answer all questions", "Use a black or dark blue pen...").
   - Total marks statement ("The total mark for this paper is 75/50").
   - **Action**: Always skipped by the extractor.
2. **Body Pages (Pages 2 through N-1)**:
   - **Top Header**: Page number (centered or corner), barcode string, and margin guidance `DO NOT WRITE IN THIS MARGIN` on left and right outer margins.
   - **Question Root**: Bold integer at left margin (e.g., `1`, `2`, `3...`) followed by stem text/equation or diagram.
   - **Subparts**: Indented labels `(a)`, `(b)`, `(c)` or older Roman numerals `(i)`, `(ii)`.
   - **Mark Allocations**: Right-aligned bracketed integers `[1]`, `[2]`, `[4]` marking marks for that part/page.
   - **Answer Workspace**: Variable-height block of horizontal dotted lines (`...`) for student handwriting.
   - **Bottom Footer**: Syllabus/component code (e.g. `9709/12/O/N/24`), copyright notice (`© UCLES 2024`), and page turnover indicator `[Turn over`.
3. **End Pages (Trailing 1–3 pages)**:
   - **Additional Page**: Header stating *"Additional Page: If you use the following lined page to complete the answer(s)..."* — pure lined space.
   - **BLANK PAGE**: Copyright notices or blank buffer pages.
   - **Action**: Slicing terminates when the final question mark tally matches total paper marks.

### 4. Direct Impact on Extractor & Verifier Rules

1. **Era Detection**: If total pages <= 6, run in **Compact Mode** (no answer lines to excise); if total pages >= 10, run in **Write-in Mode** (excise dotted lines).
2. **Crop Boundaries**: Vertical slices must start below page headers (typically y > 80/1000) and end above page footers (typically y < 940/1000).
3. **Preamble Attachment**: When question has a root stem/diagram before part `(a)`, attach root slice to `qXX_a` and retain in the composite `qXX_full`.
4. **Mark Completeness Check**: Verifier computes sum of extracted marks against the paper's standard total (75 for P1/P3, 50 for P2/P4/P5/P6). If sum != expected, verifier flags missing subpart.

