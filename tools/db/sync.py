"""Manifest-to-Database synchronization seam for PPQ Extractor.

Ingests paper manifest.json structures into the unified relational SQLite schema:
  - papers (metadata, total marks, verifier notes)
  - questions (question items, composite/preamble assets, marks)
  - question_parts (Question Parts, labels, marks, isolated part assets)
  - slices (preamble and part bounding boxes: ymin, ymax, xmin, xmax, page)
  - topics & question_topics (Syllabus Topic Codes e.g. '1.1', '1.8')

Executes all ingestions inside atomic BEGIN IMMEDIATE; write transactions with
idempotent replace semantics to support verifier repair loops without duplicates.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from tools.db.connection import atomic_transaction, get_connection
from tools.db.migrations import seed_syllabus_topics
from tools.queue_manager import (
    determine_expected_marks,
    determine_mode,
    get_session_slug,
)

QP_ID_PATTERN = re.compile(r"^([a-zA-Z0-9]+)_([a-zA-Z]+)(\d{2})_qp_(\d+)(?:\.pdf)?$")


def _extract_preamble_slices(q: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract preamble slices from question dictionary."""
    slices: list[dict[str, Any]] = []
    has_preamble = q.get("has_preamble", None)

    if has_preamble is not False:
        if "preamble_slices" in q and q["preamble_slices"]:
            raw = q["preamble_slices"]
            if isinstance(raw, list):
                slices.extend(raw)
            elif isinstance(raw, dict):
                slices.append(raw)
        elif "preamble_slice" in q and q["preamble_slice"]:
            raw = q["preamble_slice"]
            if isinstance(raw, list):
                slices.extend(raw)
            elif isinstance(raw, dict):
                slices.append(raw)
        elif "preamble" in q and isinstance(q["preamble"], dict):
            preamble_data = q["preamble"]
            if "slices" in preamble_data and preamble_data["slices"]:
                raw = preamble_data["slices"]
                if isinstance(raw, list):
                    slices.extend(raw)
                elif isinstance(raw, dict):
                    slices.append(raw)

    return slices


def sync_manifest_to_db(
    manifest_path: str | Path,
    db_path: str | Path | sqlite3.Connection | None = None,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Synchronize a paper's manifest.json into the unified SQLite database.

    Args:
        manifest_path: Path to the paper's manifest.json.
        db_path: SQLite database path, or existing connection. Defaults to `.pipeline/queue.db`.
        conn: Optional explicit SQLite connection to reuse.

    Returns:
        Summary dictionary of ingested entities.
    """
    manifest_file = Path(manifest_path).resolve()
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_file}")

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))

    paper_id = str(
        manifest_data.get("id") or manifest_data.get("paper_id") or ""
    ).strip()
    if not paper_id:
        raise ValueError(f"Manifest at {manifest_file} is missing 'id' or 'paper_id'")

    should_close = False
    if isinstance(db_path, sqlite3.Connection):
        target_conn = db_path
    elif conn is not None:
        target_conn = conn
    else:
        target_conn = get_connection(db_path)
        should_close = True

    try:
        with atomic_transaction(target_conn):
            # 1. Parse / derive paper metadata
            match = QP_ID_PATTERN.match(paper_id)
            if match:
                reg_syllabus = match.group(1)
                reg_session = match.group(2)
                reg_yy = int(match.group(3))
                reg_year = 2000 + reg_yy if reg_yy < 80 else 1900 + reg_yy
                reg_code = match.group(4)
                if len(reg_code) > 1:
                    reg_comp = int(reg_code[0])
                    reg_var: int | None = int(reg_code[1:])
                else:
                    reg_comp = int(reg_code[0])
                    reg_var = None
            else:
                reg_syllabus = "9709"
                reg_session = "w"
                reg_year = 2024
                reg_comp = 1
                reg_var = None

            syllabus = str(manifest_data.get("syllabus") or reg_syllabus)
            year = int(manifest_data.get("year") or reg_year)
            session = str(manifest_data.get("session") or reg_session)
            session_slug = str(
                manifest_data.get("session_slug") or get_session_slug(session)
            )

            if "component" in manifest_data and manifest_data["component"] is not None:
                component = int(manifest_data["component"])
            elif "paper" in manifest_data and manifest_data["paper"] is not None:
                p_val = int(manifest_data["paper"])
                component = p_val // 10 if p_val >= 10 else p_val
            else:
                component = reg_comp

            if "variant" in manifest_data and manifest_data["variant"] is not None:
                variant: int | None = int(manifest_data["variant"])
            elif "paper" in manifest_data and manifest_data["paper"] is not None:
                p_val = int(manifest_data["paper"])
                variant = p_val % 10 if p_val >= 10 else None
            else:
                variant = reg_var

            # Check for existing paper in database to preserve un-overridden metadata
            existing_row = target_conn.execute(
                "SELECT * FROM papers WHERE id = ?;", (paper_id,)
            ).fetchone()

            source_pdf = (
                str(manifest_data["source_pdf"])
                if "source_pdf" in manifest_data
                else (
                    str(existing_row["source_pdf"])
                    if existing_row
                    else f"data/source/{paper_id}.pdf"
                )
            )

            # Status handling
            verification_block = manifest_data.get("verification")
            raw_status = manifest_data.get("status")
            if (
                isinstance(verification_block, dict)
                and verification_block.get("status") == "approved"
            ):
                status = "verified"
            elif raw_status in ("unprocessed", "extracted", "verified", "needs_rework"):
                status = raw_status
            elif existing_row:
                status = existing_row["status"]
            else:
                status = "extracted"

            pages_processed = manifest_data.get("pages_processed")
            if (
                "total_pages" in manifest_data
                and manifest_data["total_pages"] is not None
            ):
                total_pages = int(manifest_data["total_pages"])
            elif isinstance(pages_processed, list) and pages_processed:
                total_pages = max(int(p) for p in pages_processed)
            elif existing_row:
                total_pages = int(existing_row["total_pages"])
            else:
                total_pages = 1

            if "mode" in manifest_data:
                mode = str(manifest_data["mode"])
            elif existing_row:
                mode = str(existing_row["mode"])
            else:
                mode = determine_mode(total_pages, year)

            if (
                "expected_marks" in manifest_data
                and manifest_data["expected_marks"] is not None
            ):
                expected_marks = int(manifest_data["expected_marks"])
            elif (
                "total_marks" in manifest_data
                and manifest_data["total_marks"] is not None
            ):
                expected_marks = int(manifest_data["total_marks"])
            elif existing_row:
                expected_marks = int(existing_row["expected_marks"])
            else:
                expected_marks = determine_expected_marks(syllabus, component)

            if "output_dir" in manifest_data:
                output_dir = str(manifest_data["output_dir"])
            elif existing_row:
                output_dir = str(existing_row["output_dir"])
            else:
                output_dir = str(manifest_file.parent)

            verified_at = None
            verifier_notes = None
            if isinstance(verification_block, dict):
                verified_at = verification_block.get("timestamp") or manifest_data.get(
                    "verified_at"
                )
                audit_notes = verification_block.get("audit_notes")
                if isinstance(audit_notes, list):
                    verifier_notes = "\n".join(str(note) for note in audit_notes)
                elif audit_notes:
                    verifier_notes = str(audit_notes)
                else:
                    verifier_notes = manifest_data.get("verifier_notes")
            else:
                verified_at = manifest_data.get("verified_at")
                verifier_notes = manifest_data.get("verifier_notes")

            extracted_at = manifest_data.get("extracted_at")

            # Questions parsing
            raw_questions = manifest_data.get("questions", [])

            # Compute extracted marks total
            if (
                "extracted_marks" in manifest_data
                and manifest_data["extracted_marks"] is not None
            ):
                extracted_marks = int(manifest_data["extracted_marks"])
            elif (
                "extracted_marks_total" in manifest_data
                and manifest_data["extracted_marks_total"] is not None
            ):
                extracted_marks = int(manifest_data["extracted_marks_total"])
            elif (
                isinstance(verification_block, dict)
                and verification_block.get("extracted_marks") is not None
            ):
                extracted_marks = int(verification_block["extracted_marks"])
            else:
                # Sum question marks
                extracted_marks = sum(
                    int(
                        q.get("marks")
                        or q.get("total_question_marks")
                        or q.get("total_marks")
                        or 0
                    )
                    for q in raw_questions
                )

            # Ensure syllabus topics seed is applied
            seed_syllabus_topics(target_conn)

            # 2. Upsert paper row
            target_conn.execute(
                """
                INSERT INTO papers (
                    id, syllabus, year, session, session_slug, component, variant,
                    source_pdf, status, total_pages, mode, expected_marks, extracted_marks,
                    output_dir, extracted_at, verified_at, verifier_notes
                ) VALUES (
                    :id, :syllabus, :year, :session, :session_slug, :component, :variant,
                    :source_pdf, :status, :total_pages, :mode, :expected_marks, :extracted_marks,
                    :output_dir, :extracted_at, :verified_at, :verifier_notes
                )
                ON CONFLICT(id) DO UPDATE SET
                    syllabus = excluded.syllabus,
                    year = excluded.year,
                    session = excluded.session,
                    session_slug = excluded.session_slug,
                    component = excluded.component,
                    variant = excluded.variant,
                    source_pdf = CASE WHEN excluded.source_pdf != '' THEN excluded.source_pdf ELSE papers.source_pdf END,
                    status = excluded.status,
                    total_pages = CASE WHEN excluded.total_pages > 0 THEN excluded.total_pages ELSE papers.total_pages END,
                    mode = excluded.mode,
                    expected_marks = CASE WHEN excluded.expected_marks > 0 THEN excluded.expected_marks ELSE papers.expected_marks END,
                    extracted_marks = COALESCE(excluded.extracted_marks, papers.extracted_marks),
                    output_dir = CASE WHEN excluded.output_dir != '' THEN excluded.output_dir ELSE papers.output_dir END,
                    extracted_at = COALESCE(excluded.extracted_at, papers.extracted_at),
                    verified_at = COALESCE(excluded.verified_at, papers.verified_at),
                    verifier_notes = COALESCE(excluded.verifier_notes, papers.verifier_notes);
                """,
                {
                    "id": paper_id,
                    "syllabus": syllabus,
                    "year": year,
                    "session": session,
                    "session_slug": session_slug,
                    "component": component,
                    "variant": variant,
                    "source_pdf": source_pdf,
                    "status": status,
                    "total_pages": total_pages,
                    "mode": mode,
                    "expected_marks": expected_marks,
                    "extracted_marks": extracted_marks,
                    "output_dir": output_dir,
                    "extracted_at": extracted_at,
                    "verified_at": verified_at,
                    "verifier_notes": verifier_notes,
                },
            )

            # 3. Purge existing question records for this paper (idempotent replace)
            target_conn.execute(
                "DELETE FROM slices WHERE question_id IN (SELECT id FROM questions WHERE paper_id = ?);",
                (paper_id,),
            )
            target_conn.execute(
                "DELETE FROM question_topics WHERE question_id IN (SELECT id FROM questions WHERE paper_id = ?);",
                (paper_id,),
            )
            target_conn.execute(
                "DELETE FROM question_parts WHERE question_id IN (SELECT id FROM questions WHERE paper_id = ?);",
                (paper_id,),
            )
            target_conn.execute(
                "DELETE FROM questions WHERE paper_id = ?;",
                (paper_id,),
            )

            # Build index lookup for question_index if present
            question_index_map: dict[int, dict[str, Any]] = {}
            for item in manifest_data.get("question_index", []):
                if isinstance(item, dict) and "question_number" in item:
                    question_index_map[int(item["question_number"])] = item

            # 4. Ingest questions, parts, slices, and topics
            total_parts_count = 0
            total_slices_count = 0
            total_topics_count = 0

            for idx, q in enumerate(raw_questions, start=1):
                q_num = int(q.get("number", idx))
                q_id = str(q.get("id") or f"{paper_id}_q{q_num:02d}")

                preamble_slices = _extract_preamble_slices(q)
                has_preamble = int(bool(q.get("has_preamble") or preamble_slices))

                # Resolve composite asset path
                composite_asset = (
                    q.get("composite_asset_path")
                    or q.get("composite_image_path")
                    or (question_index_map.get(q_num, {}).get("composite_asset"))
                    or f"questions/q{q_num:02d}/full.png"
                )

                # Resolve preamble asset path
                if has_preamble:
                    preamble_asset = (
                        q.get("preamble_asset_path")
                        or q.get("preamble_image_path")
                        or f"questions/q{q_num:02d}/preamble.png"
                    )
                else:
                    preamble_asset = None

                # Parts resolution
                parts = q.get("parts", [])
                if not parts:
                    if "slices" in q:
                        parts = [{"label": "", "slices": q["slices"]}]
                    elif "box_1000" in q or ("ymin" in q and "ymax" in q):
                        parts = [{"label": "", "slices": [q]}]

                # Calculate total marks for question
                if "marks" in q and q["marks"] is not None:
                    q_marks = int(q["marks"])
                elif (
                    "total_question_marks" in q
                    and q["total_question_marks"] is not None
                ):
                    q_marks = int(q["total_question_marks"])
                elif "total_marks" in q and q["total_marks"] is not None:
                    q_marks = int(q["total_marks"])
                else:
                    q_marks = sum(int(p.get("marks", 0) or 0) for p in parts)

                # Insert question
                target_conn.execute(
                    """
                    INSERT INTO questions (
                        id, paper_id, question_number, total_marks, has_preamble,
                        composite_image_path, preamble_image_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        q_id,
                        paper_id,
                        q_num,
                        q_marks,
                        has_preamble,
                        composite_asset,
                        preamble_asset,
                    ),
                )

                # Insert preamble slices
                for seq, p_sl in enumerate(preamble_slices):
                    target_conn.execute(
                        """
                        INSERT INTO slices (
                            question_id, part_id, kind, page, ymin, ymax, xmin, xmax, sequence
                        ) VALUES (?, NULL, 'preamble', ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            q_id,
                            int(p_sl["page"]),
                            float(p_sl["ymin"]),
                            float(p_sl["ymax"]),
                            float(p_sl.get("xmin", 0.0)),
                            float(p_sl.get("xmax", 1000.0)),
                            seq,
                        ),
                    )
                    total_slices_count += 1

                # Ingest question parts
                for p_idx, part in enumerate(parts, start=1):
                    raw_label = (
                        str(part.get("label") or part.get("part_label") or "")
                        .strip()
                        .strip("()")
                    )
                    clean_label = re.sub(r"[^a-zA-Z0-9_-]", "", raw_label)

                    if clean_label:
                        filename = f"part_{clean_label}.png"
                        label_val = clean_label
                        default_part_id = f"{q_id}_{clean_label}"
                    elif len(parts) == 1:
                        filename = "full.png" if not has_preamble else "part.png"
                        label_val = ""
                        default_part_id = f"{q_id}_p{p_idx}"
                    else:
                        filename = f"part_{p_idx}.png"
                        label_val = str(p_idx)
                        default_part_id = f"{q_id}_p{p_idx}"

                    part_id = str(
                        part.get("id") or part.get("part_id") or default_part_id
                    )
                    if part.get("marks") is not None:
                        part_marks = int(part["marks"])
                    elif len(parts) == 1:
                        part_marks = q_marks
                    else:
                        part_marks = 0
                    part_image_path = (
                        part.get("part_image_path")
                        or part.get("asset_path")
                        or f"questions/q{q_num:02d}/{filename}"
                    )
                    asset_path = part.get("asset_path") or part_image_path
                    has_preamble_context = (
                        1
                        if (
                            has_preamble
                            or "preamble" in part.get("context_dependencies", [])
                        )
                        else 0
                    )
                    part_label_display = part.get("part_label") or (
                        f"({label_val})" if label_val else None
                    )

                    target_conn.execute(
                        """
                        INSERT INTO question_parts (
                            id, question_id, label, part_label, marks,
                            part_image_path, asset_path, has_preamble_context
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            part_id,
                            q_id,
                            label_val,
                            part_label_display,
                            part_marks,
                            part_image_path,
                            asset_path,
                            has_preamble_context,
                        ),
                    )
                    total_parts_count += 1

                    # Ingest part slices
                    part_slices = part.get("slices", [])
                    if not part_slices and "slice" in part:
                        part_slices = [part["slice"]]

                    for s_seq, s in enumerate(part_slices):
                        target_conn.execute(
                            """
                            INSERT INTO slices (
                                question_id, part_id, kind, page, ymin, ymax, xmin, xmax, sequence
                            ) VALUES (?, ?, 'part', ?, ?, ?, ?, ?, ?);
                            """,
                            (
                                q_id,
                                part_id,
                                int(s["page"]),
                                float(s["ymin"]),
                                float(s["ymax"]),
                                float(s.get("xmin", 0.0)),
                                float(s.get("xmax", 1000.0)),
                                s_seq,
                            ),
                        )
                        total_slices_count += 1

                    # Part topics
                    part_topics = part.get("topics", [])
                    if not part_topics and len(parts) == 1:
                        part_topics = q.get("topics", []) or (
                            q.get("taxonomy", {}).get("topics", [])
                            if isinstance(q.get("taxonomy"), dict)
                            else []
                        )
                    for t in part_topics:
                        t_code = (
                            (t.get("code") or t.get("topic_code"))
                            if isinstance(t, dict)
                            else str(t).strip()
                        )
                        if not t_code:
                            continue
                        t_title = t.get("title") if isinstance(t, dict) else None
                        target_conn.execute(
                            """
                            INSERT OR IGNORE INTO topics (topic_code, title, syllabus)
                            VALUES (?, ?, ?);
                            """,
                            (t_code, t_title or f"Topic {t_code}", syllabus),
                        )
                        target_conn.execute(
                            """
                            INSERT OR IGNORE INTO question_topics (question_id, topic_code, part_id)
                            VALUES (?, ?, ?);
                            """,
                            (q_id, t_code, part_id),
                        )
                        total_topics_count += 1

                # Question-level topics
                q_topics = q.get("topics", []) or (
                    q.get("taxonomy", {}).get("topics", [])
                    if isinstance(q.get("taxonomy"), dict)
                    else []
                )
                for t in q_topics:
                    t_code = (
                        (t.get("code") or t.get("topic_code"))
                        if isinstance(t, dict)
                        else str(t).strip()
                    )
                    if not t_code:
                        continue
                    t_title = t.get("title") if isinstance(t, dict) else None
                    target_conn.execute(
                        """
                        INSERT OR IGNORE INTO topics (topic_code, title, syllabus)
                        VALUES (?, ?, ?);
                        """,
                        (t_code, t_title or f"Topic {t_code}", syllabus),
                    )
                    target_conn.execute(
                        """
                        INSERT OR IGNORE INTO question_topics (question_id, topic_code, part_id)
                        VALUES (?, ?, NULL);
                        """,
                        (q_id, t_code),
                    )
                    total_topics_count += 1

        return {
            "status": "success",
            "paper_id": paper_id,
            "questions_synced": len(raw_questions),
            "parts_synced": total_parts_count,
            "slices_synced": total_slices_count,
            "topics_synced": total_topics_count,
        }
    finally:
        if should_close:
            target_conn.close()
