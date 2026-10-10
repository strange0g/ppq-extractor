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
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from tools.pdf_utils import get_pdf_page_count

SCHEMA_URL = "https://json-schema.org/draft/2020-12/schema"
QUEUE_VERSION = "1.0"
VALID_STATUSES = {"unprocessed", "extracted", "verified", "needs_rework"}
QP_FILENAME_PATTERN = re.compile(
    r"^([a-zA-Z0-9]+)_([a-zA-Z]+)(\d{2})_qp_(\d+)\.pdf$"
)

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

    # Sort deterministically by (year, session, component, variant, id)
    discovered_papers.sort(
        key=lambda p: (
            p["year"],
            p["session"],
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
        raise ValueError(f"Invalid status: '{status}'. Valid statuses are: {VALID_STATUSES}")

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


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint for queue_manager."""
    parser = argparse.ArgumentParser(
        prog="python3 -m tools.queue_manager",
        description="Master Queue Ledger & Pipeline Manager",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

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

    # Subcommand: summary (or status)
    summary_parser = subparsers.add_parser(
        "summary", aliases=["status"], help="Print concise summary table of queue status"
    )
    summary_parser.add_argument(
        "--queue-file",
        default=".pipeline/queue.json",
        help="Queue ledger JSON path (default: .pipeline/queue.json)",
    )

    args = parser.parse_args(argv)

    if args.subcommand == "scan":
        queue_data = scan_queue(args.source_dir, args.queue_file)
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
        queue_file = Path(args.queue_file)
        if not queue_file.is_file():
            sys.stderr.write(f"Queue file '{args.queue_file}' does not exist.\n")
            return 1
        queue_data = load_queue(args.queue_file)
        paper = get_next_paper(queue_data, args.role)
        if paper is None:
            sys.stderr.write(f"No papers available for role '{args.role}'.\n")
            return 1
        print(json.dumps(paper, indent=2))
        return 0

    elif args.subcommand == "update":
        queue_file = Path(args.queue_file)
        if not queue_file.is_file():
            sys.stderr.write(f"Queue file '{args.queue_file}' does not exist.\n")
            return 1
        queue_data = load_queue(args.queue_file)
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

        save_queue(args.queue_file, queue_data)
        print(f"Paper '{args.paper_id}' successfully updated to '{args.status}'.")
        return 0

    elif args.subcommand == "show":
        queue_file = Path(args.queue_file)
        if not queue_file.is_file():
            sys.stderr.write(f"Queue file '{args.queue_file}' does not exist.\n")
            return 1
        queue_data = load_queue(args.queue_file)
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
        queue_file = Path(args.queue_file)
        if not queue_file.is_file():
            sys.stderr.write(f"Queue file '{args.queue_file}' does not exist.\n")
            return 1
        queue_data = load_queue(args.queue_file)
        summary = queue_data.get("summary", {})
        print("=== Processing Queue Status Summary ===")
        print(f"Total Papers  : {summary.get('total', 0)}")
        print(f"Unprocessed   : {summary.get('unprocessed', 0)}")
        print(f"Extracted     : {summary.get('extracted', 0)}")
        print(f"Verified      : {summary.get('verified', 0)}")
        print(f"Needs Rework  : {summary.get('needs_rework', 0)}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
