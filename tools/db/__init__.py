"""Unified Database Package for PPQ Extractor.

Provides connection factory, atomic transaction helper, versioned migration runner,
and unified relational schema DDL.
"""

from __future__ import annotations

from tools.db.connection import atomic_transaction, get_connection, transaction
from tools.db.migrations import (
    MIGRATIONS,
    Migration,
    get_schema_version,
    run_migrations,
    seed_syllabus_topics,
    set_schema_version,
)

__all__ = [
    "get_connection",
    "atomic_transaction",
    "transaction",
    "run_migrations",
    "get_schema_version",
    "set_schema_version",
    "seed_syllabus_topics",
    "Migration",
    "MIGRATIONS",
]
