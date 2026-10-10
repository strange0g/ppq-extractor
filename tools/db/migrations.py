"""Schema migration engine and DDL definitions for PPQ Extractor.

Tracks database schema revisions using SQLite's native PRAGMA user_version.
Applies migrations atomically inside BEGIN IMMEDIATE write transactions.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Callable

from tools.db.connection import atomic_transaction


def _split_sql_statements(script: str) -> list[str]:
    """Split a multi-statement SQL script into individual executable statements."""
    statements: list[str] = []
    current: list[str] = []
    in_quote = False
    quote_char = ""

    for char in script:
        if char in ('"', "'"):
            if not in_quote:
                in_quote = True
                quote_char = char
            elif quote_char == char:
                in_quote = False
        if char == ";" and not in_quote:
            cleaned = "".join(current).strip()
            if cleaned:
                statements.append(cleaned)
            current = []
        else:
            current.append(char)

    cleaned = "".join(current).strip()
    if cleaned:
        statements.append(cleaned)

    return statements


def _execute_sql_script(conn: sqlite3.Connection, script: str) -> None:
    """Execute a script statement by statement within the active transaction."""
    for stmt in _split_sql_statements(script):
        # Skip pure comment or whitespace blocks
        lines = [line.strip() for line in stmt.splitlines() if line.strip()]
        executable_lines = [line for line in lines if not line.startswith("--")]
        if executable_lines:
            conn.execute(stmt)


class Migration:
    """Represents a discrete, versioned database schema migration."""

    def __init__(
        self,
        version: int,
        name: str,
        up: str | Callable[[sqlite3.Connection], None],
    ) -> None:
        self.version = version
        self.name = name
        self.up = up

    def apply(self, conn: sqlite3.Connection) -> None:
        """Apply this migration to the database connection."""
        if callable(self.up):
            self.up(conn)
        else:
            _execute_sql_script(conn, self.up)


INITIAL_SCHEMA_V1 = """
-- 1. Papers: metadata, syllabus, session, variants, mark totals, queue status
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    syllabus TEXT NOT NULL,
    year INTEGER NOT NULL,
    session TEXT NOT NULL,
    session_slug TEXT NOT NULL,
    component INTEGER NOT NULL,
    variant INTEGER,
    source_pdf TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('unprocessed', 'extracted', 'verified', 'needs_rework')),
    total_pages INTEGER NOT NULL,
    mode TEXT NOT NULL,
    expected_marks INTEGER NOT NULL,
    extracted_marks INTEGER,
    output_dir TEXT NOT NULL,
    extracted_at TEXT,
    verified_at TEXT,
    verifier_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(status);
CREATE INDEX IF NOT EXISTS idx_papers_order ON papers(year DESC, session DESC, component ASC, variant ASC);
CREATE INDEX IF NOT EXISTS idx_papers_syllabus_year ON papers(syllabus, year);

-- 2. Topics: syllabus curriculum topic definitions
CREATE TABLE IF NOT EXISTS topics (
    topic_code TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    syllabus TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_topics_syllabus ON topics(syllabus);

-- 3. Questions: question items, total marks, asset paths, paper foreign key
CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    question_number INTEGER NOT NULL,
    total_marks INTEGER NOT NULL DEFAULT 0,
    has_preamble INTEGER NOT NULL DEFAULT 0,
    composite_image_path TEXT,
    preamble_image_path TEXT,
    UNIQUE(paper_id, question_number)
);

CREATE INDEX IF NOT EXISTS idx_questions_paper_id ON questions(paper_id);
CREATE INDEX IF NOT EXISTS idx_questions_number ON questions(question_number);

-- 4. Question Parts: subparts with labels, marks, isolated asset path, preamble context
CREATE TABLE IF NOT EXISTS question_parts (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    part_label TEXT,
    marks INTEGER NOT NULL DEFAULT 0,
    part_image_path TEXT,
    asset_path TEXT,
    has_preamble_context INTEGER NOT NULL DEFAULT 0,
    UNIQUE(question_id, label)
);

CREATE INDEX IF NOT EXISTS idx_question_parts_question_id ON question_parts(question_id);

-- 5. Question Topics: many-to-many junction indexing questions and subparts by Syllabus Topic Codes
CREATE TABLE IF NOT EXISTS question_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    topic_code TEXT NOT NULL REFERENCES topics(topic_code) ON DELETE CASCADE,
    part_id TEXT REFERENCES question_parts(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_question_topics_unique ON question_topics(question_id, topic_code, IFNULL(part_id, ''));
CREATE INDEX IF NOT EXISTS idx_question_topics_topic ON question_topics(topic_code);
CREATE INDEX IF NOT EXISTS idx_question_topics_question ON question_topics(question_id);
CREATE INDEX IF NOT EXISTS idx_question_topics_part ON question_topics(part_id);

-- 6. Slices: bounding box coordinates (ymin, ymax, xmin, xmax, page, kind)
CREATE TABLE IF NOT EXISTS slices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    part_id TEXT REFERENCES question_parts(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    page INTEGER NOT NULL,
    ymin REAL NOT NULL,
    ymax REAL NOT NULL,
    xmin REAL NOT NULL DEFAULT 0,
    xmax REAL NOT NULL DEFAULT 1000,
    sequence INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_slices_question ON slices(question_id);
CREATE INDEX IF NOT EXISTS idx_slices_part ON slices(part_id);
CREATE INDEX IF NOT EXISTS idx_slices_page ON slices(page);
"""

MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        name="0001_unified_relational_schema",
        up=INITIAL_SCHEMA_V1,
    )
]


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Retrieve the current schema version from PRAGMA user_version."""
    cur = conn.execute("PRAGMA user_version;")
    row = cur.fetchone()
    return int(row[0]) if row else 0


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Update PRAGMA user_version to the specified version."""
    conn.execute(f"PRAGMA user_version = {int(version)};")


def run_migrations(
    conn: sqlite3.Connection,
    target_version: int | None = None,
    custom_migrations: list[Migration] | None = None,
) -> int:
    """Apply pending migrations up to target_version atomically.

    Args:
        conn: Target SQLite connection.
        target_version: Maximum version to apply. Defaults to the latest available migration.
        custom_migrations: Optional custom list of migrations for testing or extension.

    Returns:
        The current schema version after migrations have been applied.
    """
    migration_list = custom_migrations if custom_migrations is not None else MIGRATIONS
    if not migration_list:
        return get_schema_version(conn)

    max_available = max(m.version for m in migration_list)
    limit_version = target_version if target_version is not None else max_available

    current_version = get_schema_version(conn)
    if current_version >= limit_version:
        return current_version

    # Filter and sort migrations to apply in ascending order
    pending = sorted(
        [m for m in migration_list if current_version < m.version <= limit_version],
        key=lambda m: m.version,
    )

    for migration in pending:
        with atomic_transaction(conn):
            migration.apply(conn)
            set_schema_version(conn, migration.version)
        current_version = migration.version

    return current_version


def seed_syllabus_topics(
    conn: sqlite3.Connection,
    syllabus_json_path: Path | str | None = None,
) -> int:
    """Populate the topics table with definitions from a syllabus JSON file.

    Args:
        conn: SQLite connection.
        syllabus_json_path: Path to syllabus JSON file. If None, looks for default `data/syllabus/9709.json`.

    Returns:
        Number of topics seeded.
    """
    if syllabus_json_path is None:
        candidate = Path("data/syllabus/9709.json")
        if not candidate.is_file():
            return 0
        syllabus_json_path = candidate

    path = Path(syllabus_json_path)
    if not path.is_file():
        return 0

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    syllabus = str(data.get("syllabus", "9709"))
    components = data.get("components", {})
    count = 0

    with atomic_transaction(conn):
        for comp_data in components.values():
            if not isinstance(comp_data, dict):
                continue
            topics = comp_data.get("topics", [])
            for t in topics:
                if not isinstance(t, dict):
                    continue
                code = t.get("code")
                title = t.get("title")
                if code and title:
                    conn.execute(
                        """
                        INSERT INTO topics (topic_code, title, syllabus)
                        VALUES (?, ?, ?)
                        ON CONFLICT(topic_code) DO UPDATE SET
                            title = excluded.title,
                            syllabus = excluded.syllabus;
                    """,
                        (str(code), str(title), syllabus),
                    )
                    count += 1

    return count
