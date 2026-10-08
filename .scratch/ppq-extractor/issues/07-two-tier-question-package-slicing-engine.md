# 07: Two-Tier Question Package Slicing Engine

**What to build:** The full-width cropping and slicing CLI tool generates self-contained Question Packages under `questions/q{NN}/`. Shared stem preambles are cropped once into `preamble.png`, Question Parts are cropped strictly in isolation into `part_{label}.png` without repeating the preamble, composite questions are stitched into `full.png` with workspace excised, and an atomic `question.json` metadata file is written per package alongside the whole-paper `manifest.json`.

**Blocked by:** 06: Standard CAIE Directory Taxonomy in Queue Manager

**Status:** ready-for-agent

- [ ] Question stem preambles are sliced into a standalone `preamble.png` when present and not redundantly prepended onto subpart crops.
- [ ] Each Question Part is sliced strictly in isolation as `part_{label}.png` (`part_a.png`, `part_b.png`, etc.).
- [ ] Each question has a stitched `full.png` combining preamble and all parts with 20px padding dividers and student answer workspaces excised.
- [ ] Each question produces an atomic `questions/q{NN}/question.json` file declaring question ID, total marks, preamble presence, parts array with coordinates and `dependencies: ["preamble"]`.
- [ ] Paper-level `manifest.json` indexes all question packages and records whole-paper mark sums and verification attributes.
- [ ] Unit tests in `tests/test_crop_slices.py` assert directory structure, decoupled assets, and metadata schema validation.
