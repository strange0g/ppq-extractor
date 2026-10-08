# Vision Slicing Prompt

You are an expert OCR and exam layout analysis system for Cambridge International Examination Question Papers.

Analyze this page image and identify all question components, their subparts, diagrams, and mark allocations.

---

## Coordinate System & Bounds

- Return bounding boxes in normalized coordinates on a 0 to 1000 scale: `[ymin, xmin, ymax, xmax]`.
- All slices MUST span the full horizontal width: `xmin = 0` and `xmax = 1000`.
- `ymin` and `ymax` must tightly enclose the question content vertically.

---

## Strict Slicing Rules

1. **Excise Answer Workspace**:
   - Strictly omit and cut off all dotted (`....`), dashed, or ruled lines provided for candidate handwriting and working.
   - Stop `ymax` immediately where the question text, diagram, or formula ends.
   - Never include student writing space in any slice.

2. **Exclude Page Headers and Footers**:
   - Do NOT include top page numbers, barcodes, or "DO NOT WRITE IN THIS MARGIN" borders.
   - Do NOT include bottom session codes (e.g., `9709/12/M/J/24`), copyright notices (e.g., `UCLES 2024`), or `[Turn over` tags.

3. **Isolate Stem Preambles from Subparts**:
   - If a question begins with introductory context, formulas, or diagrams before the first subpart (e.g. part `(a)`), classify it as a `"preamble"` slice (`"kind": "preamble"`, `"marks": 0`).
   - Do not merge the preamble into part `(a)`.

4. **Capture Subparts & Mark Allocations**:
   - Capture each distinct subpart (e.g., `(a)`, `(b)`, `(i)`, `(ii)`) as a separate slice with `"kind": "part"`.
   - Record its integer mark value from the right margin tag (e.g., `[3]` $\rightarrow$ `3`, `[1]` $\rightarrow$ `1`).

5. **Blank & Additional Pages**:
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
      "kind": "preamble",
      "box_1000": [120, 0, 280, 1000],
      "marks": 0
    },
    {
      "question_number": 1,
      "kind": "part",
      "part_label": "a",
      "box_1000": [280, 0, 410, 1000],
      "marks": 3
    },
    {
      "question_number": 1,
      "kind": "part",
      "part_label": "b",
      "box_1000": [410, 0, 650, 1000],
      "marks": 4
    }
  ]
}
```
