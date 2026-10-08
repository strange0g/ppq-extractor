# 09: End-to-End Pipeline Integration and Verification Test Suite

**What to build:** An updated end-to-end test and validation pipeline exercising the full lifecycle on test paper `9709_w24_qp_12.pdf`. Validates that the Question 1 number is preserved, Question 10 has cleanly decoupled preamble and parts, all 10 Question Packages contain valid `question.json` metadata, mark sums balance to 75 marks, and the queue ledger transitions cleanly.

**Blocked by:** 06: Standard CAIE Directory Taxonomy in Queue Manager, 07: Two-Tier Question Package Slicing Engine, 08: Standalone Hourly Agent Prompts & Question Number Invariants

**Status:** resolved

- [x] End-to-end integration test runs against test paper `9709_w24_qp_12.pdf` under the new taxonomy `data/extracted/9709/2024/oct_nov/paper_12/`.
- [x] Question 1 assets verify that the top question numeral "1" is visible and not excised.
- [x] Question 10 assets verify decoupled `preamble.png`, isolated `part_a.png`, `part_b.png`, `part_c.png`, and composite `full.png`.
- [x] All 10 question packages contain valid `question.json` files conforming to the schema and linked to the paper `manifest.json`.
- [x] Verification audit confirms extracted mark total balances exactly to expected syllabus total (75 marks).
- [x] Test suite in `tests/test_end_to_end_pipeline.py` passes completely with green CI.
