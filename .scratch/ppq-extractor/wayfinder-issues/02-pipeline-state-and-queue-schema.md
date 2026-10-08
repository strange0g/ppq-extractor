# Ticket 02: Pipeline State and Queue Schema

Type: prototype
Status: resolved

## Question

What is the exact schema and filesystem layout for tracking paper processing across disconnected autonomous agent sessions (e.g., master queue in `.pipeline/queue.json` tracking papers through `unprocessed` -> `extracted` -> `verified` / `needs_rework`), and what is the per-paper `manifest.json` schema linking questions, subparts, full-width crop files, composite question files, mark counts, and verifier audit logs?

## Answer

### 1. Filesystem Layout

```
ppq-extractor/
├── .pipeline/
│   └── queue.json               # Master ledger of all papers across syllabuses
├── 9709/                        # Raw source PDFs
├── data/
│   └── extracted/
│       └── 9709/
│           └── <year>_<session>/ # e.g. 2024_w
│               └── <variant>/   # e.g. 12
│                   ├── manifest.json
│                   ├── pages/   # Rendered page images page_01.png ...
│                   └── crops/   # Question part and composite crops
│                       ├── q01_a.png
│                       ├── q01_b.png
│                       └── q01_full.png
└── tools/                       # Deterministic Python scripts
```

### 2. Master Queue Schema (`.pipeline/queue.json`)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "version": "1.0",
  "updated_at": "2026-10-08T19:00:00Z",
  "summary": {
    "total": 120,
    "unprocessed": 118,
    "extracted": 1,
    "verified": 1,
    "needs_rework": 0
  },
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
      "extracted_marks": null,
      "output_dir": "data/extracted/9709/2024_w/12",
      "extracted_at": null,
      "verified_at": null,
      "verifier_notes": null
    }
  ]
}
```

**State Transitions**:
- `unprocessed` ➔ `extracted` (set by Extractor Agent after generating crops & manifest)
- `extracted` ➔ `verified` (set by Verifier Agent after visual audit passes)
- `extracted` ➔ `needs_rework` (set by Verifier Agent if unfixable error found; prioritized by next Extractor)
- `needs_rework` ➔ `extracted` (re-extracted by Extractor Agent)

### 3. Per-Paper Manifest Schema (`manifest.json`)

```json
{
  "id": "9709_w24_qp_12",
  "syllabus": "9709",
  "year": 2024,
  "session": "w",
  "paper": 12,
  "source_pdf": "9709/2024/2024 Nov/9709_w24_qp_12.pdf",
  "status": "extracted",
  "mode": "write_in",
  "total_marks": 75,
  "extracted_marks_total": 75,
  "pages_processed": [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
  "questions": [
    {
      "number": 1,
      "has_preamble": true,
      "preamble_slice": {
        "page": 2,
        "ymin": 95,
        "xmin": 0,
        "ymax": 240,
        "xmax": 1000
      },
      "parts": [
        {
          "label": "a",
          "marks": 3,
          "slices": [
            {
              "page": 2,
              "ymin": 240,
              "xmin": 0,
              "ymax": 380,
              "xmax": 1000
            }
          ],
          "asset_path": "crops/q01_a.png"
        },
        {
          "label": "b",
          "marks": 4,
          "slices": [
            {
              "page": 3,
              "ymin": 110,
              "xmin": 0,
              "ymax": 320,
              "xmax": 1000
            }
          ],
          "asset_path": "crops/q01_b.png"
        }
      ],
      "composite_asset_path": "crops/q01_full.png",
      "total_question_marks": 7
    }
  ],
  "verification": {
    "status": "pending",
    "verified_by": null,
    "timestamp": null,
    "checks": {
      "mark_sum_matches": null,
      "no_answer_lines_detected": null,
      "no_clipping_detected": null
    },
    "audit_notes": []
  }
}
```

