"""Question repository and syllabus topic query interface for PPQ Extractor.

Provides high-performance query methods over the unified SQLite relational database:
  - Query questions and parts by Syllabus Topic Code (e.g. '1.1', '1.8')
  - Multi-attribute filtering (syllabus, component, year, year range, session, mark allocation)
  - Pre-joined question parts, topic tags, and relative image asset paths
  - Sub-10ms query execution latency using indexed SQLite queries
  - CLI query interface supporting formatted JSON and summary table outputs
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from tools.db.connection import get_connection

DEFAULT_DB_PATH = Path(".pipeline/queue.db")


class QuestionRepository:
    """Repository interface for querying past paper questions, parts, and topic taxonomies."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Initialize repository with a database path or active connection."""
        self._should_close = False
        if conn is not None:
            self._conn = conn
        elif isinstance(db_path, sqlite3.Connection):
            self._conn = db_path
        else:
            self._conn = get_connection(db_path or DEFAULT_DB_PATH)
            self._should_close = True

    @property
    def connection(self) -> sqlite3.Connection:
        """Return the underlying SQLite connection."""
        return self._conn

    def close(self) -> None:
        """Close connection if opened internally."""
        if self._should_close and self._conn:
            self._conn.close()

    def __enter__(self) -> QuestionRepository:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def query_questions(
        self,
        *,
        topic_code: str | None = None,
        syllabus: str | None = None,
        component: int | None = None,
        variant: int | None = None,
        year: int | None = None,
        year_min: int | None = None,
        year_max: int | None = None,
        session: str | None = None,
        min_marks: int | None = None,
        max_marks: int | None = None,
        paper_id: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Query questions matching filter criteria.

        Args:
            topic_code: Syllabus Topic Code (e.g. '1.1')
            syllabus: Syllabus identifier (e.g. '9709')
            component: Component number (e.g. 1)
            variant: Variant number (e.g. 2)
            year: Exact examination year (e.g. 2024)
            year_min: Start year filter (inclusive)
            year_max: End year filter (inclusive)
            session: Session single-letter code ('m', 's', 'w')
            min_marks: Minimum total question marks
            max_marks: Maximum total question marks
            paper_id: Exact paper identifier
            limit: Maximum records to return
            offset: Offset for pagination

        Returns:
            List of question dictionaries containing parts, topics, and paper metadata.
        """
        where_clauses: list[str] = []
        params: list[Any] = []

        if topic_code:
            where_clauses.append(
                """EXISTS (
                    SELECT 1 FROM question_topics qt
                    WHERE qt.question_id = q.id AND qt.topic_code = ?
                )"""
            )
            params.append(str(topic_code))

        if syllabus:
            where_clauses.append("p.syllabus = ?")
            params.append(str(syllabus))

        if component is not None:
            where_clauses.append("p.component = ?")
            params.append(int(component))

        if variant is not None:
            where_clauses.append("p.variant = ?")
            params.append(int(variant))

        if year is not None:
            where_clauses.append("p.year = ?")
            params.append(int(year))

        if year_min is not None:
            where_clauses.append("p.year >= ?")
            params.append(int(year_min))

        if year_max is not None:
            where_clauses.append("p.year <= ?")
            params.append(int(year_max))

        if session:
            where_clauses.append("p.session = ?")
            params.append(str(session).lower())

        if min_marks is not None:
            where_clauses.append("q.total_marks >= ?")
            params.append(int(min_marks))

        if max_marks is not None:
            where_clauses.append("q.total_marks <= ?")
            params.append(int(max_marks))

        if paper_id:
            where_clauses.append("q.paper_id = ?")
            params.append(str(paper_id))

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        limit_sql = f"LIMIT {int(limit)}" if limit is not None else ""
        offset_sql = f"OFFSET {int(offset)}" if offset is not None else ""

        sql = f"""
            SELECT
                q.id,
                q.paper_id,
                q.question_number,
                q.total_marks,
                q.has_preamble,
                q.composite_image_path,
                q.preamble_image_path,
                p.syllabus,
                p.year,
                p.session,
                p.session_slug,
                p.component,
                p.variant,
                p.output_dir
            FROM questions q
            JOIN papers p ON q.paper_id = p.id
            {where_sql}
            ORDER BY p.year DESC, p.session DESC, p.component ASC, p.variant ASC, q.question_number ASC
            {limit_sql} {offset_sql};
        """

        cur = self._conn.execute(sql, params)
        rows = cur.fetchall()
        if not rows:
            return []

        question_ids = [r["id"] for r in rows]

        # Fetch parts in bulk
        placeholders = ",".join("?" for _ in question_ids)
        parts_cur = self._conn.execute(
            f"""
            SELECT
                qp.id,
                qp.question_id,
                qp.label,
                qp.part_label,
                qp.marks,
                COALESCE(qp.part_image_path, qp.asset_path) as part_image_path,
                qp.has_preamble_context
            FROM question_parts qp
            WHERE qp.question_id IN ({placeholders})
            ORDER BY qp.question_id, qp.label ASC;
            """,
            question_ids,
        )
        parts_by_qid: dict[str, list[dict[str, Any]]] = {}
        for pr in parts_cur.fetchall():
            p_dict = {
                "id": pr["id"],
                "question_id": pr["question_id"],
                "label": pr["label"],
                "part_label": pr["part_label"],
                "marks": pr["marks"],
                "part_image_path": pr["part_image_path"],
                "has_preamble_context": bool(pr["has_preamble_context"]),
                "topics": [],
            }
            parts_by_qid.setdefault(pr["question_id"], []).append(p_dict)

        # Fetch topics for both questions and parts
        topics_cur = self._conn.execute(
            f"""
            SELECT qt.question_id, qt.topic_code, qt.part_id
            FROM question_topics qt
            WHERE qt.question_id IN ({placeholders})
            ORDER BY qt.topic_code ASC;
            """,
            question_ids,
        )
        q_topics_by_qid: dict[str, set[str]] = {}
        part_topics_by_pid: dict[str, list[str]] = {}
        for tr in topics_cur.fetchall():
            qid = tr["question_id"]
            code = tr["topic_code"]
            pid = tr["part_id"]
            q_topics_by_qid.setdefault(qid, set()).add(code)
            if pid:
                part_topics_by_pid.setdefault(pid, []).append(code)

        results: list[dict[str, Any]] = []
        for r in rows:
            qid = r["id"]
            parts = parts_by_qid.get(qid, [])
            for p in parts:
                p["topics"] = sorted(set(part_topics_by_pid.get(p["id"], [])))

            topics = sorted(q_topics_by_qid.get(qid, set()))
            results.append(
                {
                    "id": qid,
                    "paper_id": r["paper_id"],
                    "question_number": r["question_number"],
                    "total_marks": r["total_marks"],
                    "has_preamble": bool(r["has_preamble"]),
                    "composite_image_path": r["composite_image_path"],
                    "preamble_image_path": r["preamble_image_path"],
                    "syllabus": r["syllabus"],
                    "year": r["year"],
                    "session": r["session"],
                    "session_slug": r["session_slug"],
                    "component": r["component"],
                    "variant": r["variant"],
                    "output_dir": r["output_dir"],
                    "topics": topics,
                    "parts": parts,
                }
            )

        return results

    def query_parts(
        self,
        *,
        topic_code: str | None = None,
        syllabus: str | None = None,
        component: int | None = None,
        variant: int | None = None,
        year: int | None = None,
        year_min: int | None = None,
        year_max: int | None = None,
        session: str | None = None,
        min_marks: int | None = None,
        max_marks: int | None = None,
        paper_id: str | None = None,
        question_id: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Query individual Question Parts matching filter criteria.

        Args:
            topic_code: Syllabus Topic Code (e.g. '1.1')
            syllabus: Syllabus identifier (e.g. '9709')
            component: Component number (e.g. 1)
            variant: Variant number (e.g. 2)
            year: Exact examination year
            year_min: Start year filter
            year_max: End year filter
            session: Session single-letter code ('m', 's', 'w')
            min_marks: Minimum marks allocated to part
            max_marks: Maximum marks allocated to part
            paper_id: Exact paper identifier
            question_id: Exact question identifier
            limit: Maximum records to return
            offset: Offset for pagination

        Returns:
            List of Question Part dictionaries with asset paths and paper context.
        """
        where_clauses: list[str] = []
        params: list[Any] = []

        if topic_code:
            where_clauses.append(
                """(
                    EXISTS (
                        SELECT 1 FROM question_topics qt
                        WHERE qt.part_id = qp.id AND qt.topic_code = ?
                    ) OR EXISTS (
                        SELECT 1 FROM question_topics qt
                        WHERE qt.question_id = q.id AND qt.part_id IS NULL AND qt.topic_code = ?
                    )
                )"""
            )
            params.extend([str(topic_code), str(topic_code)])

        if syllabus:
            where_clauses.append("p.syllabus = ?")
            params.append(str(syllabus))

        if component is not None:
            where_clauses.append("p.component = ?")
            params.append(int(component))

        if variant is not None:
            where_clauses.append("p.variant = ?")
            params.append(int(variant))

        if year is not None:
            where_clauses.append("p.year = ?")
            params.append(int(year))

        if year_min is not None:
            where_clauses.append("p.year >= ?")
            params.append(int(year_min))

        if year_max is not None:
            where_clauses.append("p.year <= ?")
            params.append(int(year_max))

        if session:
            where_clauses.append("p.session = ?")
            params.append(str(session).lower())

        if min_marks is not None:
            where_clauses.append("qp.marks >= ?")
            params.append(int(min_marks))

        if max_marks is not None:
            where_clauses.append("qp.marks <= ?")
            params.append(int(max_marks))

        if paper_id:
            where_clauses.append("q.paper_id = ?")
            params.append(str(paper_id))

        if question_id:
            where_clauses.append("qp.question_id = ?")
            params.append(str(question_id))

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        limit_sql = f"LIMIT {int(limit)}" if limit is not None else ""
        offset_sql = f"OFFSET {int(offset)}" if offset is not None else ""

        sql = f"""
            SELECT
                qp.id,
                qp.question_id,
                qp.label,
                qp.part_label,
                qp.marks,
                COALESCE(qp.part_image_path, qp.asset_path) as part_image_path,
                qp.has_preamble_context,
                q.question_number,
                q.paper_id,
                q.has_preamble,
                q.composite_image_path,
                q.preamble_image_path,
                p.syllabus,
                p.year,
                p.session,
                p.session_slug,
                p.component,
                p.variant,
                p.output_dir
            FROM question_parts qp
            JOIN questions q ON qp.question_id = q.id
            JOIN papers p ON q.paper_id = p.id
            {where_sql}
            ORDER BY p.year DESC, p.session DESC, p.component ASC, p.variant ASC, q.question_number ASC, qp.label ASC
            {limit_sql} {offset_sql};
        """

        cur = self._conn.execute(sql, params)
        rows = cur.fetchall()
        if not rows:
            return []

        part_ids = [r["id"] for r in rows]
        question_ids = list({r["question_id"] for r in rows})

        # Fetch part-specific topics and question-level topics
        placeholders_parts = ",".join("?" for _ in part_ids)
        topics_cur = self._conn.execute(
            f"""
            SELECT topic_code, part_id, question_id
            FROM question_topics
            WHERE part_id IN ({placeholders_parts}) OR (part_id IS NULL AND question_id IN ({",".join("?" for _ in question_ids)}));
            """,
            part_ids + question_ids,
        )
        part_topics: dict[str, set[str]] = {}
        q_topics: dict[str, set[str]] = {}
        for tr in topics_cur.fetchall():
            code = tr["topic_code"]
            if tr["part_id"]:
                part_topics.setdefault(tr["part_id"], set()).add(code)
            else:
                q_topics.setdefault(tr["question_id"], set()).add(code)

        results: list[dict[str, Any]] = []
        for r in rows:
            pid = r["id"]
            qid = r["question_id"]
            topics = sorted(part_topics.get(pid, set()) or q_topics.get(qid, set()))
            results.append(
                {
                    "id": pid,
                    "question_id": qid,
                    "paper_id": r["paper_id"],
                    "question_number": r["question_number"],
                    "label": r["label"],
                    "part_label": r["part_label"],
                    "marks": r["marks"],
                    "part_image_path": r["part_image_path"],
                    "has_preamble_context": bool(r["has_preamble_context"]),
                    "preamble_image_path": r["preamble_image_path"],
                    "composite_image_path": r["composite_image_path"],
                    "syllabus": r["syllabus"],
                    "year": r["year"],
                    "session": r["session"],
                    "session_slug": r["session_slug"],
                    "component": r["component"],
                    "variant": r["variant"],
                    "output_dir": r["output_dir"],
                    "topics": topics,
                }
            )

        return results

    def query_by_topic(self, topic_code: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Convenience method to query questions by Syllabus Topic Code."""
        return self.query_questions(topic_code=topic_code, **kwargs)

    def get_question(self, question_id: str) -> dict[str, Any] | None:
        """Retrieve a single question by id, including its parts, topics, and slices."""
        cur = self._conn.execute(
            """
            SELECT
                q.id,
                q.paper_id,
                q.question_number,
                q.total_marks,
                q.has_preamble,
                q.composite_image_path,
                q.preamble_image_path,
                p.syllabus,
                p.year,
                p.session,
                p.session_slug,
                p.component,
                p.variant,
                p.output_dir
            FROM questions q
            JOIN papers p ON q.paper_id = p.id
            WHERE q.id = ?;
            """,
            (question_id,),
        )
        row = cur.fetchone()
        if not row:
            return None

        # Fetch parts
        parts_cur = self._conn.execute(
            """
            SELECT
                qp.id,
                qp.question_id,
                qp.label,
                qp.part_label,
                qp.marks,
                COALESCE(qp.part_image_path, qp.asset_path) as part_image_path,
                qp.has_preamble_context
            FROM question_parts qp
            WHERE qp.question_id = ?
            ORDER BY qp.label ASC;
            """,
            (question_id,),
        )
        parts = [
            {
                "id": pr["id"],
                "question_id": pr["question_id"],
                "label": pr["label"],
                "part_label": pr["part_label"],
                "marks": pr["marks"],
                "part_image_path": pr["part_image_path"],
                "has_preamble_context": bool(pr["has_preamble_context"]),
                "topics": [],
            }
            for pr in parts_cur.fetchall()
        ]

        # Fetch topics
        topics_cur = self._conn.execute(
            """
            SELECT topic_code, part_id
            FROM question_topics
            WHERE question_id = ?
            ORDER BY topic_code ASC;
            """,
            (question_id,),
        )
        all_topics: set[str] = set()
        part_topics_map: dict[str, list[str]] = {}
        for tr in topics_cur.fetchall():
            all_topics.add(tr["topic_code"])
            if tr["part_id"]:
                part_topics_map.setdefault(tr["part_id"], []).append(tr["topic_code"])

        for p in parts:
            p["topics"] = sorted(set(part_topics_map.get(p["id"], [])))

        return {
            "id": row["id"],
            "paper_id": row["paper_id"],
            "question_number": row["question_number"],
            "total_marks": row["total_marks"],
            "has_preamble": bool(row["has_preamble"]),
            "composite_image_path": row["composite_image_path"],
            "preamble_image_path": row["preamble_image_path"],
            "syllabus": row["syllabus"],
            "year": row["year"],
            "session": row["session"],
            "session_slug": row["session_slug"],
            "component": row["component"],
            "variant": row["variant"],
            "output_dir": row["output_dir"],
            "topics": sorted(all_topics),
            "parts": parts,
        }

    def get_paper(self, paper_id: str) -> dict[str, Any] | None:
        """Retrieve a paper record with its question count and total marks."""
        cur = self._conn.execute("SELECT * FROM papers WHERE id = ?;", (paper_id,))
        row = cur.fetchone()
        if not row:
            return None
        data = dict(row)

        q_cur = self._conn.execute(
            "SELECT count(*) as count, sum(total_marks) as marks FROM questions WHERE paper_id = ?;",
            (paper_id,),
        )
        q_row = q_cur.fetchone()
        data["questions_count"] = q_row["count"] if q_row else 0
        data["calculated_marks"] = q_row["marks"] or 0 if q_row else 0
        return data

    def list_topics(self, syllabus: str | None = None) -> list[dict[str, Any]]:
        """List topics registered in database along with counts of tagged questions and parts."""
        params: list[Any] = []
        where = ""
        if syllabus:
            where = "WHERE t.syllabus = ?"
            params.append(str(syllabus))

        sql = f"""
            SELECT
                t.topic_code,
                t.title,
                t.syllabus,
                COUNT(DISTINCT qt.question_id) as question_count,
                COUNT(DISTINCT qt.part_id) as part_count
            FROM topics t
            LEFT JOIN question_topics qt ON t.topic_code = qt.topic_code
            {where}
            GROUP BY t.topic_code, t.title, t.syllabus
            ORDER BY t.topic_code ASC;
        """
        cur = self._conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def _format_table(results: list[dict[str, Any]], is_parts: bool = False) -> str:
    """Format query results as a compact readable plain-text table."""
    if not results:
        return "No matching records found."

    lines: list[str] = []
    if is_parts:
        header = f"{'Paper ID':<18} {'Q#':<4} {'Part':<6} {'Marks':<6} {'Topics':<12} {'Part Image Path'}"
        sep = "-" * len(header)
        lines.append(header)
        lines.append(sep)
        for r in results:
            topics_str = ",".join(r.get("topics", [])) or "-"
            part_label = r.get("part_label") or r.get("label") or "-"
            lines.append(
                f"{r['paper_id']:<18} {r['question_number']:<4} {part_label:<6} {r['marks']:<6} {topics_str:<12} {r.get('part_image_path') or '-'}"
            )
    else:
        header = f"{'Paper ID':<18} {'Q#':<4} {'Marks':<6} {'Preamble':<10} {'Topics':<14} {'Composite Asset'}"
        sep = "-" * len(header)
        lines.append(header)
        lines.append(sep)
        for r in results:
            topics_str = ",".join(r.get("topics", [])) or "-"
            preamble_str = "Yes" if r.get("has_preamble") else "No"
            lines.append(
                f"{r['paper_id']:<18} {r['question_number']:<4} {r['total_marks']:<6} {preamble_str:<10} {topics_str:<14} {r.get('composite_image_path') or '-'}"
            )
    lines.append(f"\nTotal records: {len(results)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for repository queries."""
    parser = argparse.ArgumentParser(
        description="Query the PPQ Extractor SQLite question bank by topic, component, and exam attributes."
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommand to run")

    query_parser = subparsers.add_parser("query", help="Query questions or parts")
    query_parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        type=Path,
        help=f"Target SQLite database path (default: {DEFAULT_DB_PATH})",
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
        help="Paper variant number (e.g. 1, 2)",
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
        "--paper-id",
        help="Filter by specific paper ID",
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
    query_parser.add_argument(
        "--limit",
        type=int,
        help="Limit output rows",
    )

    # Topics list subcommand
    topics_parser = subparsers.add_parser(
        "topics", help="List registered syllabus topics and question counts"
    )
    topics_parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        type=Path,
        help=f"Target SQLite database path (default: {DEFAULT_DB_PATH})",
    )
    topics_parser.add_argument(
        "--syllabus",
        help="Filter by syllabus identifier (e.g. 9709)",
    )
    topics_parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="json",
        help="Output format (default: json)",
    )

    args = parser.parse_args(argv)

    if not args.subcommand or args.subcommand == "query":
        db_path = getattr(args, "db_path", DEFAULT_DB_PATH)
        if not Path(db_path).is_file():
            sys.stderr.write(f"Database not found: {db_path}\n")
            sys.exit(1)

        repo = QuestionRepository(db_path)
        try:
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
                    paper_id=getattr(args, "paper_id", None),
                    limit=getattr(args, "limit", None),
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
                    paper_id=getattr(args, "paper_id", None),
                    limit=getattr(args, "limit", None),
                )
                is_parts = False

            output_format = getattr(args, "format", "json")
            if output_format == "json":
                print(json.dumps(results, indent=2))
            else:
                print(_format_table(results, is_parts=is_parts))
        finally:
            repo.close()

    elif args.subcommand == "topics":
        db_path = getattr(args, "db_path", DEFAULT_DB_PATH)
        if not Path(db_path).is_file():
            sys.stderr.write(f"Database not found: {db_path}\n")
            sys.exit(1)

        repo = QuestionRepository(db_path)
        try:
            topics = repo.list_topics(syllabus=args.syllabus)
            if args.format == "json":
                print(json.dumps(topics, indent=2))
            else:
                print(f"{'Topic':<8} {'Title':<45} {'Questions':<10} {'Parts'}")
                print("-" * 75)
                for t in topics:
                    print(
                        f"{t['topic_code']:<8} {t['title']:<45} {t['question_count']:<10} {t['part_count']}"
                    )
        finally:
            repo.close()


if __name__ == "__main__":
    main()
