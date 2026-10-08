# 01: PDF to High-Resolution Page Image Tool

**What to build:** A command-line Python tool that converts any Cambridge Question Paper PDF into standardized 200 DPI PNG page images (`page_01.png`, `page_02.png`, etc.) using system Poppler utilities, returning execution metrics and page count for downstream agent consumption.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Command `python3 -m tools.pdf_to_images --pdf <pdf_path> --out-dir <pages_dir> [--dpi 200]` executes successfully.
- [x] Uses native `/usr/bin/pdftoppm -png -r 200` via Python standard library `subprocess`.
- [x] Generates zero-padded page files (`page_01.png`, `page_02.png`, ...) in `<pages_dir>`.
- [x] Skips re-rendering if valid page images already exist unless `--force` is specified.
- [x] Emits JSON summary on stdout containing `page_count`, `dpi`, `width`, and `height`.
- [x] End-to-end test validates rendering against a sample Cambridge paper from `9709/`.
