# 02: Full-Width Slicing and Composite Stitching Tool

**What to build:** A command-line Python tool that reads a paper's `manifest.json` and rendered page images, performs full-width horizontal crops from normalized 0–1000 vertical bounding coordinates $[ymin, 0, ymax, 1000]$, prepends stem preambles to standalone subpart crops (`q01_a.png`), excises candidate answer workspace lines, and stitches composite question images (`q01_full.png`).

**Blocked by:** 01: PDF to High-Resolution Page Image Tool

**Status:** resolved

- [x] Command `python3 -m tools.crop_slices --manifest <manifest_path> --pages-dir <pages_dir> --out-dir <crops_dir>` executes cleanly.
- [x] Transforms normalized $[ymin, 0, ymax, 1000]$ into pixel coordinates with +10px vertical safety padding.
- [x] Forces full-width crop ($x_1 = 0, x_2 = \text{width}$) so all generated crops have identical horizontal width.
- [x] Automatically prepends shared stem preamble slices (with 20px clean divider) to subpart crops so every `qXX_<part>.png` is self-contained.
- [x] Concatenates all subpart slices into `crops/qXX_full.png` while completely omitting answer workspace between them.
- [x] Updates `manifest.json` with generated asset file paths and pixel dimensions.
- [x] End-to-end test validates multi-part questions, preamble attachment, and composite stitching.

