# Unified Relational SQLite Question Bank and Asset Storage Overhaul

We establish a unified, zero-dependency SQLite database foundation (`.pipeline/queue.db`) incorporating a 6-table relational schema, an atomic manifest synchronization seam in `tools.crop_slices` (`sync_manifest_to_db`), and deprecate redundant per-question `question.json` descriptors by default to eliminate thousands of duplicate files and inode churn.

## Context & Problem

1. **Inode Churn & Asset Redundancy**:
   Under ADR 0001 and ADR 0003, every Question Package under `questions/q{NN}/` wrote a redundant atomic `question.json` descriptor file alongside pure media assets (`full.png`, `part_*.png`, `preamble.png`). Across hundreds of examination papers and thousands of questions, this generated thousands of duplicate JSON files that duplicated metadata already tracked in the paper-level `manifest.json`.
2. **Topic-Based Querying Limitations**:
   Curriculum researchers and downstream systems need to query questions and isolated Question Parts across papers by Cambridge Syllabus Topic Codes (e.g. `1.1`, `1.7`), component, year range, session, and marks. Querying loose JSON files required scanning entire directory trees.
3. **Database Concurrency & Lock Escalation**:
   Multi-agent execution requires high-concurrency access without write lock contention or deadlocks during parallel Extractor and Verifier runs.

## Decision

1. **Unified Relational SQLite Foundation**:
   - Store all papers, questions, question parts, syllabus topic taxonomy, question-topic associations, and coordinate slices in `.pipeline/queue.db` using Python's standard library `sqlite3` and Pydantic v2 domain models (`tools.db.models`).
   - Configure WAL mode (`PRAGMA journal_mode = WAL;`), 10-second busy timeout (`PRAGMA busy_timeout = 10000;`), and foreign key enforcement (`PRAGMA foreign_keys = ON;`) on all connections.
   - Execute all write operations inside `atomic_transaction(conn)` via `BEGIN IMMEDIATE;` to prevent lock escalation deadlocks.
   - Manage schema versions atomically using `PRAGMA user_version` migrations (`tools.db.migrations`).

2. **Streamlined Question Packages & question.json Deprecation**:
   - Question Packages under `<paper_dir>/questions/q{NN}/` contain purely clean media assets (`full.png`, `part_{label}.png`, `preamble.png`).
   - Generation of per-question `question.json` is deprecated by default. For backward compatibility, `--emit-question-json` preserves legacy generation.
   - `manifest.json`'s `question_index` format is updated to reference package directories (`questions/q{NN}`) and composite assets (`questions/q{NN}/full.png`) directly.

3. **Atomic Cropping & Manifest Synchronization Seam**:
   - Ingest manifest data into SQLite via `sync_manifest_to_db(manifest_path, db_path)` invoked at the conclusion of image cropping in `tools.crop_slices` (controllable via `--db-path` / `--no-db`).
   - Cropping errors abort before opening a database write transaction, preventing partial ingestion.
   - Verifier repair re-runs execute an idempotent delete-and-replace for the specific `paper_id`.

4. **Curriculum Topic Query Repository**:
   - Provide `QuestionRepository` in `tools.db.repository` supporting sub-10ms multi-attribute queries across questions and Question Parts by Syllabus Topic Code, component, year range, session, and marks.
   - Expose CLI querying via `uv run ppq-queue query` and `uv run python -m tools.db.repository query`.

## Consequences

- Inode bloat and duplicate metadata files are eliminated across all Question Packages.
- `manifest.json` remains the authoritative file-based source of truth during vision slicing and verifier checks without requiring live database connections during visual inspection.
- The SQLite question bank enables sub-10ms querying by Cambridge Syllabus Topic Code and multi-attribute filters with typed Pydantic v2 domain models.
