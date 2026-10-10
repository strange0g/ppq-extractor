#!/usr/bin/env python3
"""Master Queue Ledger & Pipeline Manager for PPQ Extractor.

Tracks past paper processing states across autonomous agent sessions in .pipeline/queue.json.
Provides CLI subcommands:
  - scan: Discovers all *_qp_*.pdf Question Papers and initializes/merges the ledger.
  - next: Claims the next candidate paper prioritized by role.
  - update: Atomically updates paper status, notes, and summary counts.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.pdf_utils import get_pdf_page_count

SCHEMA_URL = "https://json-schema.org/draft/2020-12/schema"
QUEUE_VERSION = "1.0"
VALID_STATUSES = {"unprocessed", "extracted", "verified", "needs_rework"}
QP_FILENAME_PATTERN = re.compile(r"^([a-zA-Z0-9]+)_([a-zA-Z]+)(\d{2})_qp_(\d+)\.pdf$")

CAIE_SESSION_MAP: dict[str, str] = {
    "m": "feb_march",
    "s": "may_june",
    "w": "oct_nov",
}


def get_session_slug(session: str) -> str:
    """Map CAIE single-letter session code to human-readable slug.

    'm' -> 'feb_march'
    's' -> 'may_june'
    'w' -> 'oct_nov'
    """
    return CAIE_SESSION_MAP.get(session.lower(), session.lower())


def get_paper_output_dir(
    syllabus: str | int,
    year: int,
    session: str,
    paper_code: str | int,
) -> str:
    """Construct standard CAIE output directory for a paper.

    Format: data/extracted/<syllabus>/<year>/<session_slug>/paper_<paper_code>
    """
    session_slug = get_session_slug(str(session))
    return f"data/extracted/{syllabus}/{year}/{session_slug}/paper_{paper_code}"


def normalize_paper_entry(paper: dict[str, Any]) -> dict[str, Any]:
    """Ensure paper entry conforms to standard CAIE directory taxonomy."""
    if "session" in paper and "session_slug" not in paper:
        paper["session_slug"] = get_session_slug(str(paper["session"]))
    if (
        "syllabus" in paper
        and "year" in paper
        and "session" in paper
        and ("component" in paper or "output_dir" in paper)
    ):
        paper_code = None
        if paper.get("variant") is not None:
            paper_code = f"{paper['component']}{paper['variant']}"
        elif paper.get("component") is not None:
            paper_code = str(paper["component"])
        elif "output_dir" in paper:
            parts = str(paper["output_dir"]).rstrip("/").split("/")
            if parts:
                last_part = parts[-1]
                if last_part.startswith("paper_"):
                    paper_code = last_part.replace("paper_", "")
                else:
                    paper_code = last_part

        if paper_code:
            expected_output_dir = get_paper_output_dir(
                paper["syllabus"], paper["year"], paper["session"], paper_code
            )
            if paper.get("output_dir") != expected_output_dir:
                paper["output_dir"] = expected_output_dir
    return paper


def determine_mode(total_pages: int, year: int) -> str:
    """Determine extraction mode: compact (pre-2017 / <=9 pages) vs write_in."""
    if total_pages < 10 or year < 2017:
        return "compact"
    return "write_in"


def determine_expected_marks(
    syllabus: str | int,
    component: int | None = None,
) -> int:
    """Determine expected total marks for a paper given its syllabus and component.

    For syllabus 9709 (Cambridge International AS & A Level Mathematics):
      - Component 1 (Pure Mathematics 1): 75 marks
      - Component 3 (Pure Mathematics 3): 75 marks
      - Component 2 (Pure Mathematics 2): 50 marks
      - Component 4 (Mechanics): 50 marks
      - Component 5 (Probability & Statistics 1): 50 marks
      - Component 6 (Probability & Statistics 2): 50 marks
      - Component 7 (historical Statistics 2): 50 marks

    For other/unspecified syllabuses, provides extensible component-based defaults.
    """
    if component is None and isinstance(syllabus, int):
        # Backward-compatible support if invoked as determine_expected_marks(component)
        component = syllabus
        syllabus_str = "9709"
    else:
        syllabus_str = str(syllabus).strip()

    comp_num = int(component) if component is not None else 1

    if syllabus_str == "9709":
        if comp_num in (1, 3):
            return 75
        return 50

    # Extensible fallbacks for other Cambridge syllabuses
    if syllabus_str in ("9231",):  # Further Mathematics
        if comp_num in (1, 2):
            return 75
        return 50
    elif syllabus_str in ("9701", "9702", "9700"):  # Chemistry, Physics, Biology
        if comp_num == 1:
            return 40  # Multiple Choice
        elif comp_num in (2, 3):
            return 60  # AS Level Structured Questions / Practical
        elif comp_num == 4:
            return 100  # A Level Structured Questions
        elif comp_num == 5:
            return 30  # Planning, Analysis and Evaluation

    if comp_num in (1, 3):
        return 75
    return 50


def parse_paper_metadata(
    pdf_path: str | Path,
    source_dir: str | Path,
    total_pages: int | None = None,
) -> dict[str, Any] | None:
    """Parse Question Paper metadata from filename and path."""
    path = Path(pdf_path)
    match = QP_FILENAME_PATTERN.match(path.name)
    if not match:
        return None

    syllabus = match.group(1)
    session = match.group(2)
    yy = int(match.group(3))
    paper_code = match.group(4)

    # 2-digit year conversion
    year = 2000 + yy if yy < 80 else 1900 + yy

    # Component and variant
    if len(paper_code) > 1:
        component = int(paper_code[0])
        variant: int | None = int(paper_code[1:])
    else:
        component = int(paper_code[0])
        variant = None

    session_slug = get_session_slug(session)
    if total_pages is None:
        total_pages = get_pdf_page_count(path)

    mode = determine_mode(total_pages, year)
    expected_marks = determine_expected_marks(syllabus, component)
    output_dir = get_paper_output_dir(syllabus, year, session, paper_code)

    # Determine relative source_pdf path
    try:
        source_pdf = os.path.relpath(path, os.getcwd())
        if source_pdf.startswith(".."):
            source_pdf = os.path.relpath(
                path, os.path.dirname(os.path.abspath(source_dir))
            )
    except ValueError:
        source_pdf = str(path)

    paper_id = path.stem

    return {
        "id": paper_id,
        "syllabus": syllabus,
        "year": year,
        "session": session,
        "session_slug": session_slug,
        "component": component,
        "variant": variant,
        "source_pdf": source_pdf,
        "status": "unprocessed",
        "total_pages": total_pages,
        "mode": mode,
        "expected_marks": expected_marks,
        "extracted_marks": None,
        "output_dir": output_dir,
        "extracted_at": None,
        "verified_at": None,
        "verifier_notes": None,
    }


def recalculate_summary(papers: list[dict[str, Any]]) -> dict[str, int]:
    """Calculate summary counts from papers list."""
    summary = {
        "total": len(papers),
        "unprocessed": 0,
        "extracted": 0,
        "verified": 0,
        "needs_rework": 0,
    }
    for paper in papers:
        st = paper.get("status", "unprocessed")
        if st in summary:
            summary[st] += 1
        else:
            summary["unprocessed"] += 1
    return summary


def load_queue(queue_file: str | Path) -> dict[str, Any]:
    """Load queue data from file or return a fresh queue structure."""
    path = Path(queue_file)
    if path.is_file():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for p in data.get("papers", []):
            normalize_paper_entry(p)
        return data
    return {
        "$schema": SCHEMA_URL,
        "version": QUEUE_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": 0,
            "unprocessed": 0,
            "extracted": 0,
            "verified": 0,
            "needs_rework": 0,
        },
        "papers": [],
    }


def get_paper(queue_data: dict[str, Any], paper_id: str) -> dict[str, Any] | None:
    """Find paper in queue by ID."""
    for p in queue_data.get("papers", []):
        if p.get("id") == paper_id:
            return p
    return None


def save_queue(queue_file: str | Path, queue_data: dict[str, Any]) -> None:
    """Atomically save queue data to file using temp file and os.replace."""
    path = Path(queue_file).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".{path.name}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(queue_data, f, indent=2)
        f.write("\n")
    os.replace(tmp_path, path)


class QueueDatabase:
    """SQLite database ledger for PPQ Extractor queue management."""

    def __init__(self, db_path: str | Path = ".pipeline/queue.db") -> None:
        self.db_path = Path(db_path).resolve()
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        from tools.db.connection import get_connection

        return get_connection(self.db_path, auto_migrate=False)

    def init_db(self) -> None:
        from tools.db.migrations import run_migrations

        with self.get_connection() as conn:
            run_migrations(conn)

    def get_paper(self, paper_id: str) -> dict[str, Any] | None:
        with self.get_connection() as conn:
            cur = conn.execute("SELECT * FROM papers WHERE id = ?;", (paper_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_next_paper(self, role: str) -> dict[str, Any] | None:
        with self.get_connection() as conn:
            if role == "extractor":
                query = """
                    SELECT * FROM papers
                    WHERE status IN ('needs_rework', 'unprocessed')
                    ORDER BY CASE status WHEN 'needs_rework' THEN 1 ELSE 2 END,
                             year DESC,
                             CASE session WHEN 'w' THEN 3 WHEN 's' THEN 2 WHEN 'm' THEN 1 ELSE 0 END DESC,
                             component ASC,
                             COALESCE(variant, -1) ASC,
                             id ASC
                    LIMIT 1;
                """
            elif role == "verifier":
                query = """
                    SELECT * FROM papers
                    WHERE status = 'extracted'
                    ORDER BY year DESC,
                             CASE session WHEN 'w' THEN 3 WHEN 's' THEN 2 WHEN 'm' THEN 1 ELSE 0 END DESC,
                             component ASC,
                             COALESCE(variant, -1) ASC,
                             id ASC
                    LIMIT 1;
                """
            else:
                return None

            cur = conn.execute(query)
            row = cur.fetchone()
            return dict(row) if row else None

    def update_paper_status(
        self,
        paper_id: str,
        status: str,
        notes: str | None = None,
        extracted_marks: int | None = None,
    ) -> dict[str, Any]:
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status: '{status}'. Valid statuses are: {VALID_STATUSES}"
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        from tools.db.connection import atomic_transaction

        with self.get_connection() as conn:
            with atomic_transaction(conn):
                cur = conn.execute("SELECT * FROM papers WHERE id = ?;", (paper_id,))
                existing = cur.fetchone()
                if existing is None:
                    raise KeyError(f"Paper '{paper_id}' not found in database.")

                extracted_at = existing["extracted_at"]
                verified_at = existing["verified_at"]
                verifier_notes = (
                    notes if notes is not None else existing["verifier_notes"]
                )
                final_marks = (
                    extracted_marks
                    if extracted_marks is not None
                    else existing["extracted_marks"]
                )

                if status == "extracted":
                    extracted_at = now_iso
                elif status == "verified":
                    verified_at = now_iso

                conn.execute(
                    """
                    UPDATE papers
                    SET status = ?,
                        extracted_at = ?,
                        verified_at = ?,
                        verifier_notes = ?,
                        extracted_marks = ?
                    WHERE id = ?;
                    """,
                    (
                        status,
                        extracted_at,
                        verified_at,
                        verifier_notes,
                        final_marks,
                        paper_id,
                    ),
                )
                cur = conn.execute("SELECT * FROM papers WHERE id = ?;", (paper_id,))
                return dict(cur.fetchone())

    def upsert_papers(self, papers: list[dict[str, Any]]) -> int:
        count = 0
        from tools.db.connection import atomic_transaction

        with self.get_connection() as conn:
            with atomic_transaction(conn):
                for p in papers:
                    conn.execute(
                        """
                        INSERT INTO papers (
                            id, syllabus, year, session, session_slug, component, variant,
                            source_pdf, status, total_pages, mode, expected_marks,
                            extracted_marks, output_dir, extracted_at, verified_at, verifier_notes
                        ) VALUES (
                            :id, :syllabus, :year, :session, :session_slug, :component, :variant,
                            :source_pdf, :status, :total_pages, :mode, :expected_marks,
                            :extracted_marks, :output_dir, :extracted_at, :verified_at, :verifier_notes
                        )
                        ON CONFLICT(id) DO UPDATE SET
                            source_pdf = excluded.source_pdf,
                            total_pages = excluded.total_pages,
                            mode = excluded.mode,
                            expected_marks = excluded.expected_marks,
                            output_dir = excluded.output_dir;
                        """,
                        p,
                    )
                    count += 1
        return count

    def get_summary(self) -> dict[str, int]:
        with self.get_connection() as conn:
            cur = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'unprocessed' THEN 1 ELSE 0 END) as unprocessed,
                    SUM(CASE WHEN status = 'extracted' THEN 1 ELSE 0 END) as extracted,
                    SUM(CASE WHEN status = 'verified' THEN 1 ELSE 0 END) as verified,
                    SUM(CASE WHEN status = 'needs_rework' THEN 1 ELSE 0 END) as needs_rework
                FROM papers;
            """)
            row = cur.fetchone()
            if not row:
                return {
                    "total": 0,
                    "unprocessed": 0,
                    "extracted": 0,
                    "verified": 0,
                    "needs_rework": 0,
                }
            return {
                "total": row["total"] or 0,
                "unprocessed": row["unprocessed"] or 0,
                "extracted": row["extracted"] or 0,
                "verified": row["verified"] or 0,
                "needs_rework": row["needs_rework"] or 0,
            }

    def migrate_from_json(self, json_path: str | Path) -> int:
        path = Path(json_path)
        if not path.is_file():
            raise FileNotFoundError(f"JSON file '{json_path}' does not exist.")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        papers = data.get("papers", [])
        for p in papers:
            normalize_paper_entry(p)
        from tools.db.connection import atomic_transaction

        with self.get_connection() as conn:
            with atomic_transaction(conn):
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO papers (
                        id, syllabus, year, session, session_slug, component, variant,
                        source_pdf, status, total_pages, mode, expected_marks,
                        extracted_marks, output_dir, extracted_at, verified_at, verifier_notes
                    ) VALUES (
                        :id, :syllabus, :year, :session, :session_slug, :component, :variant,
                        :source_pdf, :status, :total_pages, :mode, :expected_marks,
                        :extracted_marks, :output_dir, :extracted_at, :verified_at, :verifier_notes
                    );
                    """,
                    papers,
                )
        return len(papers)


def scan_queue(source_dir: str | Path, queue_file: str | Path) -> dict[str, Any]:
    """Scan source_dir for Question Papers and merge into queue_file."""
    existing_queue = load_queue(queue_file)
    existing_by_id = {p["id"]: p for p in existing_queue.get("papers", [])}

    discovered_papers: list[dict[str, Any]] = []

    for root, _, files in os.walk(str(source_dir)):
        for fname in files:
            if "_qp_" in fname and fname.endswith(".pdf"):
                full_path = Path(root) / fname
                meta = parse_paper_metadata(full_path, source_dir)
                if meta:
                    paper_id = meta["id"]
                    if paper_id in existing_by_id:
                        # Preserve progress and status
                        old = existing_by_id[paper_id]
                        meta["status"] = old.get("status", meta["status"])
                        meta["extracted_marks"] = old.get("extracted_marks")
                        meta["extracted_at"] = old.get("extracted_at")
                        meta["verified_at"] = old.get("verified_at")
                        meta["verifier_notes"] = old.get("verifier_notes")
                    discovered_papers.append(meta)

    # Sort deterministically latest to oldest (descending year, descending session, component, variant, id)
    # Session ordering: 'w' (winter/nov) > 's' (summer/june) > 'm' (march)
    session_order = {"w": 3, "s": 2, "m": 1}
    discovered_papers.sort(
        key=lambda p: (
            -p["year"],
            -session_order.get(p["session"], 0),
            p["component"],
            p["variant"] if p["variant"] is not None else -1,
            p["id"],
        )
    )

    summary = recalculate_summary(discovered_papers)
    queue_data = {
        "$schema": SCHEMA_URL,
        "version": QUEUE_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "papers": discovered_papers,
    }

    save_queue(queue_file, queue_data)
    return queue_data


def get_next_paper(queue_data: dict[str, Any], role: str) -> dict[str, Any] | None:
    """Find next paper based on role and priority."""
    papers = queue_data.get("papers", [])
    if role == "extractor":
        # Priority 1: needs_rework
        for p in papers:
            if p.get("status") == "needs_rework":
                return p
        # Priority 2: unprocessed
        for p in papers:
            if p.get("status") == "unprocessed":
                return p
        return None
    elif role == "verifier":
        # Next paper with status extracted
        for p in papers:
            if p.get("status") == "extracted":
                return p
        return None
    return None


def update_paper_status(
    queue_data: dict[str, Any],
    paper_id: str,
    status: str,
    notes: str | None = None,
    extracted_marks: int | None = None,
) -> dict[str, Any]:
    """Atomically update a paper's status, notes, and timestamps."""
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status: '{status}'. Valid statuses are: {VALID_STATUSES}"
        )

    papers = queue_data.get("papers", [])
    target: dict[str, Any] | None = None
    for p in papers:
        if p.get("id") == paper_id:
            target = p
            break

    if target is None:
        raise KeyError(f"Paper '{paper_id}' not found in queue.")

    now_iso = datetime.now(timezone.utc).isoformat()
    target["status"] = status

    if status == "extracted":
        target["extracted_at"] = now_iso
    elif status == "verified":
        target["verified_at"] = now_iso

    if notes is not None:
        target["verifier_notes"] = notes

    if extracted_marks is not None:
        target["extracted_marks"] = extracted_marks

    queue_data["updated_at"] = now_iso
    queue_data["summary"] = recalculate_summary(papers)
    return queue_data


def _resolve_backend(args: argparse.Namespace) -> tuple[str, Path]:
    """Resolve whether to use sqlite db or json file backend."""
    db_path = getattr(args, "db_path", None)
    if db_path is not None:
        return "db", Path(db_path)
    q_file = getattr(args, "queue_file", None)
    if q_file:
        p = Path(q_file)
        if p.suffix == ".db":
            return "db", p
        if p.suffix == ".json":
            return "json", p
    default_db = Path(".pipeline/queue.db")
    if default_db.is_file():
        return "db", default_db
    return "json", Path(".pipeline/queue.json")


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint for queue_manager."""
    parser = argparse.ArgumentParser(
        prog="python3 -m tools.queue_manager",
        description="Master Queue Ledger & Pipeline Manager",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Subcommand: migrate-json
    migrate_parser = subparsers.add_parser(
        "migrate-json",
        help="Migrate JSON ledger to SQLite database (.pipeline/queue.db)",
    )
    migrate_parser.add_argument(
        "--json-file",
        default=".pipeline/queue.json",
        help="Source JSON ledger path (default: .pipeline/queue.json)",
    )
    migrate_parser.add_argument(
        "--db-path",
        default=".pipeline/queue.db",
        help="Target SQLite database path (default: .pipeline/queue.db)",
    )

    # Subcommand: scan
    scan_parser = subparsers.add_parser(
        "scan", help="Scan directory for Question Papers and build/merge queue"
    )
    scan_parser.add_argument(
        "--source-dir",
        default="9709",
        help="Root directory containing raw PDFs (default: 9709)",
    )
    scan_parser.add_argument(
        "--queue-file",
        default=".pipeline/queue.json",
        help="Queue ledger JSON path (default: .pipeline/queue.json)",
    )
    scan_parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite database ledger path (e.g. .pipeline/queue.db)",
    )

    # Subcommand: next
    next_parser = subparsers.add_parser(
        "next", help="Get next paper candidate for a given agent role"
    )
    next_parser.add_argument(
        "--role",
        required=True,
        choices=["extractor", "verifier"],
        help="Role requesting next work item (extractor or verifier)",
    )
    next_parser.add_argument(
        "--queue-file",
        default=".pipeline/queue.json",
        help="Queue ledger JSON path (default: .pipeline/queue.json)",
    )
    next_parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite database ledger path (e.g. .pipeline/queue.db)",
    )

    # Subcommand: update
    update_parser = subparsers.add_parser(
        "update", help="Update paper status and audit notes in the ledger"
    )
    update_parser.add_argument("--id", required=True, dest="paper_id", help="Paper ID")
    update_parser.add_argument(
        "--status",
        required=True,
        choices=sorted(VALID_STATUSES),
        help="New status for paper",
    )
    update_parser.add_argument(
        "--notes", default=None, help="Verifier audit notes / error description"
    )
    update_parser.add_argument(
        "--extracted-marks",
        type=int,
        default=None,
        help="Total extracted marks recorded by extractor",
    )
    update_parser.add_argument(
        "--queue-file",
        default=".pipeline/queue.json",
        help="Queue ledger JSON path (default: .pipeline/queue.json)",
    )
    update_parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite database ledger path (e.g. .pipeline/queue.db)",
    )

    # Subcommand: show
    show_parser = subparsers.add_parser(
        "show", help="Show details of a paper or queue summary"
    )
    show_parser.add_argument(
        "--id", default=None, dest="paper_id", help="Paper ID to inspect"
    )
    show_parser.add_argument(
        "--queue-file",
        default=".pipeline/queue.json",
        help="Queue ledger JSON path (default: .pipeline/queue.json)",
    )
    show_parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite database ledger path (e.g. .pipeline/queue.db)",
    )

    # Subcommand: summary (or status)
    summary_parser = subparsers.add_parser(
        "summary",
        aliases=["status"],
        help="Print concise summary table of queue status",
    )
    summary_parser.add_argument(
        "--queue-file",
        default=".pipeline/queue.json",
        help="Queue ledger JSON path (default: .pipeline/queue.json)",
    )
    summary_parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite database ledger path (e.g. .pipeline/queue.db)",
    )

    # Subcommand: query
    query_parser = subparsers.add_parser(
        "query",
        help="Query questions or parts from the SQLite question bank by topic/metadata",
    )
    query_parser.add_argument(
        "--db-path",
        default=None,
        help="Target SQLite database path (default: .pipeline/queue.db)",
    )
    query_parser.add_argument(
        "--topic",
        dest="topic_code",
        help="Syllabus Topic Code (e.g. '1.1', '1.8')",
    )
    query_parser.add_argument(
        "--syllabus",
        help="Syllabus identifier (e.g. '9709')",
    )
    query_parser.add_argument(
        "--component",
        type=int,
        help="Component paper number (e.g. 1, 3)",
    )
    query_parser.add_argument(
        "--variant",
        type=int,
        help="Paper variant number",
    )
    query_parser.add_argument(
        "--year",
        type=int,
        help="Exam year (e.g. 2024)",
    )
    query_parser.add_argument(
        "--year-min",
        type=int,
        help="Minimum exam year filter",
    )
    query_parser.add_argument(
        "--year-max",
        type=int,
        help="Maximum exam year filter",
    )
    query_parser.add_argument(
        "--session",
        help="Exam session code ('m', 's', 'w')",
    )
    query_parser.add_argument(
        "--marks-min",
        type=int,
        help="Minimum mark threshold",
    )
    query_parser.add_argument(
        "--marks-max",
        type=int,
        help="Maximum mark threshold",
    )
    query_parser.add_argument(
        "--parts",
        action="store_true",
        help="Query at the Question Part level rather than whole questions",
    )
    query_parser.add_argument(
        "--format",
        choices=["json", "table", "plain"],
        default="json",
        help="Output format (default: json)",
    )

    args = parser.parse_args(argv)
    backend, target_path = _resolve_backend(args)

    if args.subcommand == "migrate-json":
        db = QueueDatabase(args.db_path)
        count = db.migrate_from_json(args.json_file)
        summary = db.get_summary()
        print(f"Successfully migrated {count} papers to '{args.db_path}'.")
        print(
            f"Status Summary: Total={summary['total']}, "
            f"Unprocessed={summary['unprocessed']}, "
            f"Extracted={summary['extracted']}, "
            f"Verified={summary['verified']}, "
            f"Needs Rework={summary['needs_rework']}"
        )
        return 0

    elif args.subcommand == "scan":
        if backend == "db":
            db = QueueDatabase(target_path)
            discovered_papers: list[dict[str, Any]] = []
            for root, _, files in os.walk(str(args.source_dir)):
                for fname in files:
                    if "_qp_" in fname and fname.endswith(".pdf"):
                        full_path = Path(root) / fname
                        meta = parse_paper_metadata(full_path, args.source_dir)
                        if meta:
                            discovered_papers.append(meta)
            session_order = {"w": 3, "s": 2, "m": 1}
            discovered_papers.sort(
                key=lambda p: (
                    -p["year"],
                    -session_order.get(p["session"], 0),
                    p["component"],
                    p["variant"] if p["variant"] is not None else -1,
                    p["id"],
                )
            )
            db.upsert_papers(discovered_papers)
            summary = db.get_summary()
            print(
                f"Scan complete. Total: {summary['total']}, "
                f"Unprocessed: {summary['unprocessed']}, "
                f"Extracted: {summary['extracted']}, "
                f"Verified: {summary['verified']}, "
                f"Needs rework: {summary['needs_rework']}"
            )
            return 0
        else:
            queue_data = scan_queue(args.source_dir, target_path)
            summary = queue_data["summary"]
            print(
                f"Scan complete. Total: {summary['total']}, "
                f"Unprocessed: {summary['unprocessed']}, "
                f"Extracted: {summary['extracted']}, "
                f"Verified: {summary['verified']}, "
                f"Needs rework: {summary['needs_rework']}"
            )
            return 0

    elif args.subcommand == "next":
        if backend == "db":
            if not target_path.is_file():
                sys.stderr.write(f"Database file '{target_path}' does not exist.\n")
                return 1
            db = QueueDatabase(target_path)
            paper = db.get_next_paper(args.role)
            if paper is None:
                sys.stderr.write(f"No papers available for role '{args.role}'.\n")
                return 1
            print(json.dumps(paper, indent=2))
            return 0
        else:
            if not target_path.is_file():
                sys.stderr.write(f"Queue file '{target_path}' does not exist.\n")
                return 1
            queue_data = load_queue(target_path)
            paper = get_next_paper(queue_data, args.role)
            if paper is None:
                sys.stderr.write(f"No papers available for role '{args.role}'.\n")
                return 1
            print(json.dumps(paper, indent=2))
            return 0

    elif args.subcommand == "update":
        if backend == "db":
            if not target_path.is_file():
                sys.stderr.write(f"Database file '{target_path}' does not exist.\n")
                return 1
            db = QueueDatabase(target_path)
            try:
                db.update_paper_status(
                    args.paper_id,
                    args.status,
                    notes=args.notes,
                    extracted_marks=args.extracted_marks,
                )
            except (KeyError, ValueError) as err:
                sys.stderr.write(f"Update error: {err}\n")
                return 1
            print(f"Paper '{args.paper_id}' successfully updated to '{args.status}'.")
            return 0
        else:
            if not target_path.is_file():
                sys.stderr.write(f"Queue file '{target_path}' does not exist.\n")
                return 1
            queue_data = load_queue(target_path)
            try:
                update_paper_status(
                    queue_data,
                    args.paper_id,
                    args.status,
                    notes=args.notes,
                    extracted_marks=args.extracted_marks,
                )
            except (KeyError, ValueError) as err:
                sys.stderr.write(f"Update error: {err}\n")
                return 1
            save_queue(target_path, queue_data)
            print(f"Paper '{args.paper_id}' successfully updated to '{args.status}'.")
            return 0

    elif args.subcommand == "show":
        if backend == "db":
            if not target_path.is_file():
                sys.stderr.write(f"Database file '{target_path}' does not exist.\n")
                return 1
            db = QueueDatabase(target_path)
            if args.paper_id:
                paper = db.get_paper(args.paper_id)
                if paper is None:
                    sys.stderr.write(f"Paper '{args.paper_id}' not found in queue.\n")
                    return 1
                print(json.dumps(paper, indent=2))
                return 0
            else:
                summary = db.get_summary()
                print(
                    json.dumps(
                        {"database": str(target_path), "summary": summary}, indent=2
                    )
                )
                return 0
        else:
            if not target_path.is_file():
                sys.stderr.write(f"Queue file '{target_path}' does not exist.\n")
                return 1
            queue_data = load_queue(target_path)
            if args.paper_id:
                paper = get_paper(queue_data, args.paper_id)
                if paper is None:
                    sys.stderr.write(f"Paper '{args.paper_id}' not found in queue.\n")
                    return 1
                print(json.dumps(paper, indent=2))
                return 0
            else:
                print(json.dumps(queue_data, indent=2))
                return 0

    elif args.subcommand in ("summary", "status"):
        if backend == "db":
            if not target_path.is_file():
                sys.stderr.write(f"Database file '{target_path}' does not exist.\n")
                return 1
            db = QueueDatabase(target_path)
            summary = db.get_summary()
            print("=== Processing Queue Status Summary ===")
            print(f"Total Papers  : {summary.get('total', 0)}")
            print(f"Unprocessed   : {summary.get('unprocessed', 0)}")
            print(f"Extracted     : {summary.get('extracted', 0)}")
            print(f"Verified      : {summary.get('verified', 0)}")
            print(f"Needs Rework  : {summary.get('needs_rework', 0)}")
            return 0
        else:
            if not target_path.is_file():
                sys.stderr.write(f"Queue file '{target_path}' does not exist.\n")
                return 1
            queue_data = load_queue(target_path)
            summary = queue_data.get("summary", {})
            print("=== Processing Queue Status Summary ===")
            print(f"Total Papers  : {summary.get('total', 0)}")
            print(f"Unprocessed   : {summary.get('unprocessed', 0)}")
            print(f"Extracted     : {summary.get('extracted', 0)}")
            print(f"Verified      : {summary.get('verified', 0)}")
            print(f"Needs Rework  : {summary.get('needs_rework', 0)}")
            return 0

    elif args.subcommand == "query":
        from tools.db.repository import QuestionRepository, _format_table

        db_file = (
            target_path
            if backend == "db"
            else (Path(args.db_path) if args.db_path else Path(".pipeline/queue.db"))
        )
        if not db_file.is_file():
            sys.stderr.write(f"Database file '{db_file}' does not exist.\n")
            return 1

        with QuestionRepository(db_file) as repo:
            if getattr(args, "parts", False):
                results = repo.query_parts(
                    topic_code=getattr(args, "topic_code", None),
                    syllabus=getattr(args, "syllabus", None),
                    component=getattr(args, "component", None),
                    variant=getattr(args, "variant", None),
                    year=getattr(args, "year", None),
                    year_min=getattr(args, "year_min", None),
                    year_max=getattr(args, "year_max", None),
                    session=getattr(args, "session", None),
                    min_marks=getattr(args, "marks_min", None),
                    max_marks=getattr(args, "marks_max", None),
                )
                is_parts = True
            else:
                results = repo.query_questions(
                    topic_code=getattr(args, "topic_code", None),
                    syllabus=getattr(args, "syllabus", None),
                    component=getattr(args, "component", None),
                    variant=getattr(args, "variant", None),
                    year=getattr(args, "year", None),
                    year_min=getattr(args, "year_min", None),
                    year_max=getattr(args, "year_max", None),
                    session=getattr(args, "session", None),
                    min_marks=getattr(args, "marks_min", None),
                    max_marks=getattr(args, "marks_max", None),
                )
                is_parts = False

            output_format = getattr(args, "format", "json")
            if output_format == "json":
                print(json.dumps(results, indent=2))
            else:
                print(_format_table(results, is_parts=is_parts))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
