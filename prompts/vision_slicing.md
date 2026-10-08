# Vision Slicing Prompt

You are an expert OCR and exam layout analysis system for Cambridge International Examination Question Papers.

Analyze this page image and identify all question components, their question parts, diagrams, and mark allocations.

---

## Coordinate System & Bounds

- Return bounding boxes in normalized coordinates on a 0 to 1000 scale: `[ymin, xmin, ymax, xmax]`.
- All slices MUST span the full horizontal width: `xmin = 0` and `xmax = 1000` (Full-Width Crop).
- **Question Numeral Invariant & Upward Safety Buffer**: For any slice starting a question (such as a question preamble, standalone whole question, or initial question part), `ymin` MUST strictly encompass the top-level question numeral (e.g. bold "1", "2") and include an upward safety buffer of at least 15 normalized units (or ~15px) above the top of the numeral. Question numbers must never be clipped or excised (fixing the Question 1 number cutout defect).
- `ymin` and `ymax` must tightly enclose question content vertically, stopping immediately before student handwriting areas.

---

## Strict Slicing Rules

1. **Question Numeral Invariant & Upward Safety Buffer**:
   - The top-level question number numeral (e.g. bold "1", "2") must always be fully enclosed within the question's initial slice (either the `"preamble"` slice or the initial `"part"` / `"whole"` slice).
   - Set `ymin` with an upward safety buffer of at least 15 normalized units (or at least 15px) above the topmost point of the question numeral (e.g., if Question 1 begins at $y=125$, set $ymin \le 110$).
   - Question headings and numbers must never be clipped, truncated, or omitted.

2. **Excise Answer Workspace**:
   - Strictly omit and cut off all dotted (`....`), dashed, or ruled lines provided for candidate handwriting and working.
   - Stop `ymax` immediately where the question text, diagram, or formula ends.
   - Never include student writing space in any slice.

3. **Exclude Page Headers and Footers**:
   - Do NOT include top page numbers, barcodes, or "DO NOT WRITE IN THIS MARGIN" borders.
   - Do NOT include bottom session codes (e.g., `9709/12/M/J/24`), copyright notices (e.g., `UCLES 2024`), or `[Turn over` tags.

4. **Isolate Stem Preambles from Question Parts (Question Package Expectations)**:
   - Slices feed directly into two-tier Question Packages (`questions/q{NN}/`), where preambles and question parts are stored in decoupled assets.
   - If a question begins with introductory context, formulas, or diagrams before the first question part (e.g. part `(a)`), classify it as a `"preamble"` slice (`"kind": "preamble"`, `"marks": 0`).
   - Downstream tools extract preambles to a standalone `preamble.png` and question parts to isolated `part_{label}.png` images without prepending the preamble. Do NOT merge the preamble into part `(a)`.

5. **Capture Question Parts & Mark Allocations**:
   - Capture each distinct question part (e.g., `(a)`, `(b)`, `(i)`, `(ii)`) as a separate slice with `"kind": "part"`.
   - Record its integer mark value from the right margin tag (e.g., `[3]` $\rightarrow$ `3`, `[1]` $\rightarrow$ `1`).

6. **Standalone Questions Without Parts**:
   - For questions that do not contain divided question parts (e.g., a single unpartitioned question carrying all marks), classify the slice as `"kind": "whole"` with `"part_label": null`.
   - Standalone questions carry the total question marks directly on the slice.

7. **Blank & Additional Pages**:
   - If the page contains no question items (such as a "BLANK PAGE" or "Additional Page: If you use the following lined page..."), return `"page_has_questions": false` with an empty `"items": []` list.

---

## JSON Output Schema

Return ONLY a valid JSON object matching this schema:

```json
{
  "page_has_questions": true,
  "items": [
    {
      "question_number": 1,
      "kind": "whole",
      "part_label": null,
      "box_1000": [120, 0, 310, 1000],
      "marks": 5
    },
    {
      "question_number": 2,
      "kind": "preamble",
      "box_1000": [330, 0, 480, 1000],
      "marks": 0
    },
    {
      "question_number": 2,
      "kind": "part",
      "part_label": "a",
      "box_1000": [480, 0, 610, 1000],
      "marks": 3
    },
    {
      "question_number": 2,
      "kind": "part",
      "part_label": "b",
      "box_1000": [610, 0, 850, 1000],
      "marks": 4
    }
  ]
}
```
