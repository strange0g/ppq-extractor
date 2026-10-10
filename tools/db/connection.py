"""Database connection factory and transaction management for PPQ Extractor.

Configures SQLite connections for multi-agent WAL concurrency:
  - PRAGMA journal_mode = WAL;
  - PRAGMA busy_timeout = 10000; (10s busy timeout)
  - PRAGMA foreign_keys = ON;
Provides atomic write transaction helper using BEGIN IMMEDIATE to prevent lock escalation conflicts.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

DEFAULT_DB_PATH = Path(".pipeline/queue.db")


def get_connection(
    db_path: str | Path | None = None,
    auto_migrate: bool = True,
) -> sqlite3.Connection:
    """Create and configure a SQLite database connection.

    Args:
        db_path: Target SQLite database path. Defaults to `.pipeline/queue.db`.
                 Pass `":memory:"` for an in-memory database.
        auto_migrate: If True, applies any pending schema migrations automatically.

    Returns:
        Configured sqlite3.Connection with WAL mode, busy timeout, and foreign keys.
    """
    if db_path is None:
        target_path = DEFAULT_DB_PATH
    else:
        target_path = db_path

    if str(target_path) == ":memory:":
        conn = sqlite3.connect(":memory:", timeout=10.0)
    else:
        resolved = Path(target_path).resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(resolved), timeout=10.0)

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    conn.execute("PRAGMA foreign_keys = ON;")

    if auto_migrate:
        from tools.db.migrations import run_migrations

        run_migrations(conn)

    return conn


@contextmanager
def atomic_transaction(
    conn: sqlite3.Connection,
) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for atomic write transactions using BEGIN IMMEDIATE.

    Prevents lock escalation conflicts during concurrent operations in WAL mode.
    Rolls back automatically on exception and commits on success.
    Supports nested transactions via SQLite SAVEPOINT.
    """
    if conn.in_transaction:
        savepoint_id = f"sp_{uuid.uuid4().hex}"
        conn.execute(f"SAVEPOINT {savepoint_id};")
        try:
            yield conn
            conn.execute(f"RELEASE SAVEPOINT {savepoint_id};")
        except Exception:
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_id};")
            raise
        return

    orig_isolation = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE;")
        try:
            yield conn
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise
    finally:
        conn.isolation_level = orig_isolation


# Backward-compatible alias
transaction = atomic_transaction
