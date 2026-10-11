import json
import tempfile
import unittest
from pathlib import Path

from tools.db.connection import get_connection
from tools.db.sync import sync_manifest_to_db


class TestManifestSyncToDatabase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.tmpdir.name)
        self.db_path = self.test_dir / "test_queue.db"
        self.paper_dir = self.test_dir / "papers" / "9709_w24_qp_12"
        self.paper_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.paper_dir / "manifest.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_sync_single_part_question(self):
        """Single-part question (no Question Parts or preamble) ingests cleanly with valid foreign keys."""
        manifest_data = {
            "id": "9709_w24_qp_12",
            "syllabus": "9709",
            "year": 2024,
            "session": "w",
            "paper": 12,
            "source_pdf": "data/source/9709_w24_qp_12.pdf",
            "status": "extracted",
            "mode": "write_in",
            "total_marks": 6,
            "extracted_marks_total": 6,
            "questions": [
                {
                    "number": 1,
                    "has_preamble": False,
                    "marks": 6,
                    "topics": ["1.1"],
                    "slices": [
                        {
                            "page": 2,
                            "ymin": 100.0,
                            "ymax": 350.0,
                            "xmin": 0.0,
                            "xmax": 1000.0,
                        }
                    ],
                }
            ],
        }
        self.manifest_path.write_text(json.dumps(manifest_data, indent=2))

        result = sync_manifest_to_db(self.manifest_path, self.db_path)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["paper_id"], "9709_w24_qp_12")

        conn = get_connection(self.db_path)
        try:
            # Check paper row
            paper = conn.execute(
                "SELECT * FROM papers WHERE id = '9709_w24_qp_12';"
            ).fetchone()
            self.assertIsNotNone(paper)
            self.assertEqual(paper["syllabus"], "9709")
            self.assertEqual(paper["year"], 2024)
            self.assertEqual(paper["extracted_marks"], 6)

            # Check question row
            questions = conn.execute(
                "SELECT * FROM questions WHERE paper_id = '9709_w24_qp_12';"
            ).fetchall()
            self.assertEqual(len(questions), 1)
            q = questions[0]
            self.assertEqual(q["question_number"], 1)
            self.assertEqual(q["total_marks"], 6)
            self.assertEqual(q["has_preamble"], 0)

            # Check question_parts row
            parts = conn.execute(
                "SELECT * FROM question_parts WHERE question_id = ?;", (q["id"],)
            ).fetchall()
            self.assertEqual(len(parts), 1)
            p = parts[0]
            self.assertEqual(p["marks"], 6)

            # Check slices row
            slices = conn.execute(
                "SELECT * FROM slices WHERE question_id = ?;", (q["id"],)
            ).fetchall()
            self.assertEqual(len(slices), 1)
            s = slices[0]
            self.assertEqual(s["part_id"], p["id"])
            self.assertEqual(s["kind"], "part")
            self.assertEqual(s["page"], 2)
            self.assertEqual(s["ymin"], 100.0)
            self.assertEqual(s["ymax"], 350.0)

            # Check topics & question_topics
            q_topics = conn.execute(
                "SELECT * FROM question_topics WHERE question_id = ?;", (q["id"],)
            ).fetchall()
            self.assertGreaterEqual(len(q_topics), 1)
            topic_codes = {row["topic_code"] for row in q_topics}
            self.assertIn("1.1", topic_codes)

            # Topics registry populated
            topic_row = conn.execute(
                "SELECT * FROM topics WHERE topic_code = '1.1';"
            ).fetchone()
            self.assertIsNotNone(topic_row)
            self.assertEqual(topic_row["syllabus"], "9709")
        finally:
            conn.close()

    def test_sync_multipart_question_with_preamble(self):
        """Multipart question with preamble slice and Question Parts ingests with appropriate foreign keys."""
        manifest_data = {
            "id": "9709_w24_qp_12",
            "syllabus": "9709",
            "year": 2024,
            "session": "w",
            "component": 1,
            "variant": 2,
            "source_pdf": "data/source/9709_w24_qp_12.pdf",
            "status": "extracted",
            "mode": "write_in",
            "total_marks": 75,
            "extracted_marks_total": 7,
            "questions": [
                {
                    "number": 2,
                    "has_preamble": True,
                    "preamble_slice": {
                        "page": 3,
                        "ymin": 77.0,
                        "ymax": 120.0,
                        "xmin": 0.0,
                        "xmax": 1000.0,
                    },
                    "parts": [
                        {
                            "label": "a",
                            "marks": 3,
                            "topics": ["1.1"],
                            "slices": [
                                {
                                    "page": 3,
                                    "ymin": 130.0,
                                    "ymax": 200.0,
                                    "xmin": 0.0,
                                    "xmax": 1000.0,
                                }
                            ],
                        },
                        {
                            "label": "b",
                            "marks": 4,
                            "topics": ["1.8"],
                            "slices": [
                                {
                                    "page": 3,
                                    "ymin": 300.0,
                                    "ymax": 450.0,
                                    "xmin": 0.0,
                                    "xmax": 1000.0,
                                }
                            ],
                        },
                    ],
                }
            ],
        }
        self.manifest_path.write_text(json.dumps(manifest_data, indent=2))

        result = sync_manifest_to_db(self.manifest_path, self.db_path)
        self.assertEqual(result["status"], "success")

        conn = get_connection(self.db_path)
        try:
            q = conn.execute(
                "SELECT * FROM questions WHERE paper_id = '9709_w24_qp_12' AND question_number = 2;"
            ).fetchone()
            self.assertIsNotNone(q)
            self.assertEqual(q["has_preamble"], 1)
            self.assertEqual(q["total_marks"], 7)

            # Preamble slice has part_id IS NULL and kind='preamble'
            preamble_slice = conn.execute(
                "SELECT * FROM slices WHERE question_id = ? AND kind = 'preamble';",
                (q["id"],),
            ).fetchone()
            self.assertIsNotNone(preamble_slice)
            self.assertIsNone(preamble_slice["part_id"])
            self.assertEqual(preamble_slice["page"], 3)
            self.assertEqual(preamble_slice["ymin"], 77.0)

            # Two question parts
            parts = conn.execute(
                "SELECT * FROM question_parts WHERE question_id = ? ORDER BY label;",
                (q["id"],),
            ).fetchall()
            self.assertEqual(len(parts), 2)
            self.assertEqual(parts[0]["label"], "a")
            self.assertEqual(parts[0]["marks"], 3)
            self.assertEqual(parts[0]["has_preamble_context"], 1)
            self.assertEqual(parts[1]["label"], "b")
            self.assertEqual(parts[1]["marks"], 4)

            # Part slices linked to part_id
            part_a_slice = conn.execute(
                "SELECT * FROM slices WHERE part_id = ?;", (parts[0]["id"],)
            ).fetchone()
            self.assertIsNotNone(part_a_slice)
            self.assertEqual(part_a_slice["kind"], "part")
            self.assertEqual(part_a_slice["ymin"], 130.0)

            # Topic links
            topic_a = conn.execute(
                "SELECT * FROM question_topics WHERE part_id = ?;", (parts[0]["id"],)
            ).fetchone()
            self.assertIsNotNone(topic_a)
            self.assertEqual(topic_a["topic_code"], "1.1")

            topic_b = conn.execute(
                "SELECT * FROM question_topics WHERE part_id = ?;", (parts[1]["id"],)
            ).fetchone()
            self.assertIsNotNone(topic_b)
            self.assertEqual(topic_b["topic_code"], "1.8")
        finally:
            conn.close()

    def test_idempotent_replace_verifier_repair(self):
        """Re-ingesting a repaired manifest executes clean replace without duplicate rows or orphaned parts."""
        # Initial manifest with 2 questions
        manifest_v1 = {
            "id": "9709_w24_qp_12",
            "syllabus": "9709",
            "year": 2024,
            "session": "w",
            "paper": 12,
            "status": "extracted",
            "total_marks": 75,
            "questions": [
                {
                    "number": 1,
                    "marks": 5,
                    "topics": ["1.1"],
                    "slices": [{"page": 2, "ymin": 100, "ymax": 200}],
                },
                {
                    "number": 2,
                    "marks": 4,
                    "topics": ["1.2"],
                    "slices": [{"page": 2, "ymin": 250, "ymax": 350}],
                },
            ],
        }
        self.manifest_path.write_text(json.dumps(manifest_v1, indent=2))
        sync_manifest_to_db(self.manifest_path, self.db_path)

        conn = get_connection(self.db_path)
        try:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM questions;").fetchone()[0], 2
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM question_parts;").fetchone()[0], 2
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM slices;").fetchone()[0], 2
            )
        finally:
            conn.close()

        # Verifier repairs: Q1 coordinate adjusted, Q2 removed, Q3 added with 2 Question Parts
        manifest_v2 = {
            "id": "9709_w24_qp_12",
            "syllabus": "9709",
            "year": 2024,
            "session": "w",
            "paper": 12,
            "status": "verified",
            "total_marks": 75,
            "extracted_marks_total": 12,
            "verification": {
                "status": "approved",
                "timestamp": "2026-10-10T12:00:00Z",
                "audit_notes": ["All questions verified clean"],
            },
            "questions": [
                {
                    "number": 1,
                    "marks": 5,
                    "topics": ["1.1"],
                    "slices": [{"page": 2, "ymin": 90, "ymax": 200}],  # ymin adjusted
                },
                {
                    "number": 3,
                    "parts": [
                        {
                            "label": "a",
                            "marks": 3,
                            "topics": ["1.3"],
                            "slices": [{"page": 3, "ymin": 100, "ymax": 200}],
                        },
                        {
                            "label": "b",
                            "marks": 4,
                            "topics": ["1.4"],
                            "slices": [{"page": 3, "ymin": 210, "ymax": 300}],
                        },
                    ],
                },
            ],
        }
        self.manifest_path.write_text(json.dumps(manifest_v2, indent=2))
        sync_manifest_to_db(self.manifest_path, self.db_path)

        conn = get_connection(self.db_path)
        try:
            # Paper status updated to verified
            paper = conn.execute(
                "SELECT * FROM papers WHERE id = '9709_w24_qp_12';"
            ).fetchone()
            self.assertEqual(paper["status"], "verified")
            self.assertEqual(paper["verified_at"], "2026-10-10T12:00:00Z")
            self.assertEqual(paper["extracted_marks"], 12)

            # Exactly 2 questions: Q1 and Q3 (Q2 cleanly excised)
            q_numbers = [
                r[0]
                for r in conn.execute(
                    "SELECT question_number FROM questions WHERE paper_id = '9709_w24_qp_12' ORDER BY question_number;"
                ).fetchall()
            ]
            self.assertEqual(q_numbers, [1, 3])

            # Q1 coordinate updated
            q1_slice = conn.execute(
                "SELECT ymin FROM slices s JOIN questions q ON s.question_id = q.id WHERE q.question_number = 1;"
            ).fetchone()
            self.assertEqual(q1_slice[0], 90.0)

            # Exactly 3 parts total (1 for Q1, 2 for Q3)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM question_parts;").fetchone()[0], 3
            )

            # Exactly 3 slices total
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM slices;").fetchone()[0], 3
            )

            # Old Q2 topics cleanly purged
            q2_topics = conn.execute(
                "SELECT * FROM question_topics WHERE topic_code = '1.2';"
            ).fetchall()
            self.assertEqual(len(q2_topics), 0)
        finally:
            conn.close()

    def test_atomic_rollback_on_error(self):
        """If synchronization encounters an unhandled exception, the transaction rolls back cleanly."""
        # Initial valid ingestion
        manifest_v1 = {
            "id": "9709_w24_qp_12",
            "syllabus": "9709",
            "year": 2024,
            "session": "w",
            "paper": 12,
            "total_marks": 75,
            "questions": [
                {
                    "number": 1,
                    "marks": 5,
                    "slices": [{"page": 2, "ymin": 100, "ymax": 200}],
                }
            ],
        }
        self.manifest_path.write_text(json.dumps(manifest_v1, indent=2))
        sync_manifest_to_db(self.manifest_path, self.db_path)

        # Corrupt manifest that causes error during question insertion (e.g. invalid slice page string)
        corrupted_manifest = {
            "id": "9709_w24_qp_12",
            "syllabus": "9709",
            "year": 2024,
            "session": "w",
            "paper": 12,
            "questions": [
                {
                    "number": 1,
                    "marks": 5,
                    "slices": [{"page": "NOT_AN_INTEGER", "ymin": 100, "ymax": 200}],
                }
            ],
        }
        self.manifest_path.write_text(json.dumps(corrupted_manifest, indent=2))

        with self.assertRaises(ValueError):
            sync_manifest_to_db(self.manifest_path, self.db_path)

        # Confirm database rolled back to state prior to the failed transaction
        conn = get_connection(self.db_path)
        try:
            questions = conn.execute("SELECT * FROM questions;").fetchall()
            self.assertEqual(len(questions), 1)
            # Slice page is still valid int 2 from v1
            sl = conn.execute("SELECT page FROM slices;").fetchone()
            self.assertEqual(sl[0], 2)
        finally:
            conn.close()

    def test_missing_manifest_file_raises_filenotfound(self):
        """Missing manifest file raises FileNotFoundError."""
        bogus_path = self.test_dir / "does_not_exist" / "manifest.json"
        with self.assertRaises(FileNotFoundError):
            sync_manifest_to_db(bogus_path, self.db_path)

    def test_export_from_tools_db_package(self):
        """sync_manifest_to_db is exported from top-level tools.db package."""
        import tools.db

        self.assertTrue(hasattr(tools.db, "sync_manifest_to_db"))
        self.assertIs(tools.db.sync_manifest_to_db, sync_manifest_to_db)

    def test_manifest_missing_id_raises_valueerror(self):
        """Manifest without id or paper_id raises ValueError."""
        manifest_data = {"syllabus": "9709", "questions": []}
        self.manifest_path.write_text(json.dumps(manifest_data, indent=2))
        with self.assertRaises(ValueError):
            sync_manifest_to_db(self.manifest_path, self.db_path)

    def test_paper_upsert_preserves_existing_metadata(self):
        """Pre-existing paper row in queue (e.g. unprocessed) is upserted cleanly."""
        from tools.db.connection import atomic_transaction

        conn = get_connection(self.db_path)
        try:
            with atomic_transaction(conn):
                conn.execute(
                    """
                    INSERT INTO papers (
                        id, syllabus, year, session, session_slug, component, variant,
                        source_pdf, status, total_pages, mode, expected_marks, output_dir
                    ) VALUES (
                        '9709_w24_qp_12', '9709', 2024, 'w', 'oct_nov', 1, 2,
                        'original/path.pdf', 'unprocessed', 16, 'write_in', 75, 'data/output/paper'
                    );
                    """
                )
        finally:
            conn.close()

        manifest_data = {
            "id": "9709_w24_qp_12",
            "syllabus": "9709",
            "year": 2024,
            "session": "w",
            "paper": 12,
            "status": "extracted",
            "extracted_marks_total": 75,
            "questions": [
                {
                    "number": 1,
                    "marks": 5,
                    "slices": [{"page": 2, "ymin": 100, "ymax": 200}],
                }
            ],
        }
        self.manifest_path.write_text(json.dumps(manifest_data, indent=2))
        sync_manifest_to_db(self.manifest_path, self.db_path)

        conn = get_connection(self.db_path)
        try:
            paper = conn.execute(
                "SELECT * FROM papers WHERE id = '9709_w24_qp_12';"
            ).fetchone()
            self.assertEqual(paper["status"], "extracted")
            self.assertEqual(paper["extracted_marks"], 75)
            self.assertEqual(paper["total_pages"], 16)
            self.assertEqual(paper["source_pdf"], "original/path.pdf")
        finally:
            conn.close()

    def test_multi_slice_preamble_and_part_mark_summing(self):
        """Preamble with multiple slices and question without root marks correctly aggregates."""
        manifest_data = {
            "id": "9709_w24_qp_12",
            "syllabus": "9709",
            "year": 2024,
            "session": "w",
            "paper": 12,
            "questions": [
                {
                    "number": 5,
                    "has_preamble": True,
                    "preamble_slices": [
                        {"page": 4, "ymin": 50, "ymax": 100, "xmin": 0, "xmax": 1000},
                        {"page": 4, "ymin": 120, "ymax": 180, "xmin": 0, "xmax": 1000},
                    ],
                    "parts": [
                        {
                            "label": "a",
                            "marks": 2,
                            "slices": [{"page": 4, "ymin": 200, "ymax": 250}],
                        },
                        {
                            "label": "b",
                            "marks": 5,
                            "slices": [{"page": 4, "ymin": 260, "ymax": 350}],
                        },
                    ],
                }
            ],
        }
        self.manifest_path.write_text(json.dumps(manifest_data, indent=2))

        # Test passing connection directly
        conn = get_connection(self.db_path)
        try:
            result = sync_manifest_to_db(self.manifest_path, conn=conn)
            self.assertEqual(result["slices_synced"], 4)  # 2 preamble + 2 part slices

            q = conn.execute(
                "SELECT * FROM questions WHERE paper_id = '9709_w24_qp_12' AND question_number = 5;"
            ).fetchone()
            self.assertEqual(q["total_marks"], 7)  # 2 + 5

            p_slices = conn.execute(
                "SELECT sequence, ymin FROM slices WHERE question_id = ? AND kind = 'preamble' ORDER BY sequence;",
                (q["id"],),
            ).fetchall()
            self.assertEqual(len(p_slices), 2)
            self.assertEqual(p_slices[0]["sequence"], 0)
            self.assertEqual(p_slices[0]["ymin"], 50.0)
            self.assertEqual(p_slices[1]["sequence"], 1)
            self.assertEqual(p_slices[1]["ymin"], 120.0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
