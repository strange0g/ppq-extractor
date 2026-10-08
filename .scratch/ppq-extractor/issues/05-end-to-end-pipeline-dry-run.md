# 05: End-to-End Pipeline Dry Run & Verification

**What to build:** An end-to-end verification run executing the full pipeline against an actual Cambridge 9709 past paper (e.g., `9709/2024/2024 Nov/9709_w24_qp_12.pdf`), validating that page conversion, slicing, preamble prepending, answer line excision, composite stitching, manifest generation, and verifier audit checks function seamlessly together.

**Blocked by:** 04: Autonomous Prompts Suite & AGENTS.md Guidelines

**Status:** claimed

- [ ] Complete PDF page images are rendered into `data/extracted/9709/2024_w/12/pages/`.
- [ ] Representative questions are extracted with standalone subpart crops (`qXX_a.png`) and composite full question crops (`qXX_full.png`) in `crops/`.
- [ ] Cropped images have identical horizontal width ($W$) and zero dotted answer workspace lines.
- [ ] `manifest.json` matches the prototype schema with questions, subparts, marks, and verification checks.
- [ ] Mark-sum invariant check passes (sums to expected paper marks).
- [ ] Queue entry in `.pipeline/queue.json` transitions cleanly to `verified`.
