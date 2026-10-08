# 03: Master Queue Ledger & Pipeline Manager

**What to build:** A scanner and queue management utility `tools/queue_manager.py` that discovers all Question Papers under `9709/`, initializes `.pipeline/queue.json`, provides CLI subcommands for agents to claim the next paper (prioritizing `needs_rework` before `unprocessed`), and updates status (`unprocessed` ➔ `extracted` ➔ `verified` / `needs_rework`).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Command `python3 -m tools.queue_manager scan --source-dir 9709 --queue-file .pipeline/queue.json` discovers all `*_qp_*.pdf` files.
- [ ] Correctly populates metadata: `syllabus`, `year`, `session`, `component`, `variant`, `total_pages`, `mode` (`compact` vs `write_in`), `expected_marks` (75 for P1/P3, 50 for P2/P4/P5/P6).
- [ ] Command `python3 -m tools.queue_manager next --role extractor` returns the next paper, prioritizing `needs_rework` ahead of `unprocessed`.
- [ ] Command `python3 -m tools.queue_manager next --role verifier` returns the next paper with status `extracted`.
- [ ] Command `python3 -m tools.queue_manager update --id <paper_id> --status <status> [--notes <notes>]` updates the ledger and summary counts atomically.
- [ ] Unit tests cover queue scanning, prioritization, and state transitions.
