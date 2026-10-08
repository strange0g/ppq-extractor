# 06: Standard CAIE Directory Taxonomy in Queue Manager

**What to build:** The queue manager and paper discovery tools catalog past papers into standard, human-readable directories (`data/extracted/<syllabus>/<year>/<session>/paper_<paper_code>/`) mapping Cambridge examination sessions (`m` -> `feb_march`, `s` -> `may_june`, `w` -> `oct_nov`), eliminating cryptic path segments like `2024_w/12`.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Paper scanning maps Cambridge series codes (`m`, `s`, `w`) to human-readable session slugs (`feb_march`, `may_june`, `oct_nov`).
- [ ] Queue paper records construct `output_dir` in the format `data/extracted/<syllabus>/<year>/<session_slug>/paper_<paper_code>`.
- [ ] Queue manager commands (`scan`, `next`, `update`, `show`) resolve and operate on the standardized paths deterministically.
- [ ] Unit tests in `tests/test_queue.py` verify path generation, paper discovery, and queue serialization against the new directory taxonomy.
