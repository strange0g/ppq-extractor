"""Tests for tools.db.repository (QuestionRepository) and topic querying interface.

Verifies:
1. QuestionRepository queries questions by Syllabus Topic Code (e.g. '1.1').
2. QuestionRepository queries questions by component, year, year range, session, mark allocation.
3. QuestionRepository queries question parts with isolated assets, marks, and topic tags.
4. QuestionRepository retrieves question and paper entities with nested structures.
5. QuestionRepository CLI topic query subcommand supports JSON and tabular output.
6. Startup / query latency remains fast (< 10ms).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tools.db.connection import get_connection
from tools.db.repository import QuestionRepository
from tools.db.sync import sync_manifest_to_db


class TestQuestionRepository(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.db_path = self.root / "questions.db"
        self.conn = get_connection(self.db_path)

        # Ingest two distinct papers with diverse questions and topics
        paper1 = {
            "id": "9709_w24_qp_12",
            "syllabus": "9709",
            "year": 2024,
            "session": "w",
            "component": 1,
            "variant": 2,
            "source_pdf": "data/source/9709_w24_qp_12.pdf",
            "status": "verified",
            "mode": "write_in",
            "total_marks": 75,
            "questions": [
                {
                    "number": 1,
                    "has_preamble": False,
                    "marks": 5,
                    "topics": ["1.1"],
                    "slices": [
                        {"page": 2, "ymin": 100, "ymax": 300, "xmin": 0, "xmax": 1000}
                    ],
                    "composite_asset_path": "questions/q01/full.png",
                },
                {
                    "number": 2,
                    "has_preamble": True,
                    "preamble_slice": {
                        "page": 2,
                        "ymin": 350,
                        "ymax": 450,
                        "xmin": 0,
                        "xmax": 1000,
                    },
                    "composite_asset_path": "questions/q02/full.png",
                    "preamble_asset_path": "questions/q02/preamble.png",
                    "parts": [
                        {
                            "label": "a",
                            "marks": 3,
                            "topics": ["1.2"],
                            "slices": [
                                {
                                    "page": 2,
                                    "ymin": 460,
                                    "ymax": 550,
                                    "xmin": 0,
                                    "xmax": 1000,
                                }
                            ],
                            "asset_path": "questions/q02/part_a.png",
                        },
                        {
                            "label": "b",
                            "marks": 4,
                            "topics": ["1.1", "1.2"],
                            "slices": [
                                {
                                    "page": 3,
                                    "ymin": 100,
                                    "ymax": 250,
                                    "xmin": 0,
                                    "xmax": 1000,
                                }
                            ],
                            "asset_path": "questions/q02/part_b.png",
                        },
                    ],
                },
            ],
        }

        paper2 = {
            "id": "9709_s23_qp_31",
            "syllabus": "9709",
            "year": 2023,
            "session": "s",
            "component": 3,
            "variant": 1,
            "source_pdf": "data/source/9709_s23_qp_31.pdf",
            "status": "extracted",
            "mode": "write_in",
            "total_marks": 75,
            "questions": [
                {
                    "number": 1,
                    "has_preamble": False,
                    "marks": 8,
                    "topics": ["3.1"],
                    "slices": [
                        {"page": 2, "ymin": 100, "ymax": 400, "xmin": 0, "xmax": 1000}
                    ],
                    "composite_asset_path": "questions/q01/full.png",
                }
            ],
        }

        p1_path = self.root / "p1_manifest.json"
        p1_path.write_text(json.dumps(paper1, indent=2))
        sync_manifest_to_db(p1_path, conn=self.conn)

        p2_path = self.root / "p2_manifest.json"
        p2_path.write_text(json.dumps(paper2, indent=2))
        sync_manifest_to_db(p2_path, conn=self.conn)

        self.repo = QuestionRepository(conn=self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def test_query_questions_by_topic_code(self):
        """Querying by topic code retrieves matching questions and their parts."""
        # Topic 1.1 matches Question 1 and Question 2 in paper 9709_w24_qp_12
        q_results = self.repo.query_questions(topic_code="1.1")
        self.assertEqual(len(q_results), 2)
        q_numbers = {q["question_number"] for q in q_results}
        self.assertEqual(q_numbers, {1, 2})

        # Topic 3.1 matches only Question 1 in paper 9709_s23_qp_31
        q_results_3 = self.repo.query_questions(topic_code="3.1")
        self.assertEqual(len(q_results_3), 1)
        self.assertEqual(q_results_3[0]["paper_id"], "9709_s23_qp_31")
        self.assertEqual(q_results_3[0]["question_number"], 1)

    def test_query_questions_by_component_and_year(self):
        """Querying by component, year range, and session."""
        res_comp1 = self.repo.query_questions(component=1)
        self.assertEqual(len(res_comp1), 2)

        res_comp3 = self.repo.query_questions(component=3)
        self.assertEqual(len(res_comp3), 1)

        res_2024 = self.repo.query_questions(year=2024)
        self.assertEqual(len(res_2024), 2)

        res_range = self.repo.query_questions(year_min=2020, year_max=2023)
        self.assertEqual(len(res_range), 1)
        self.assertEqual(res_range[0]["year"], 2023)

        res_session = self.repo.query_questions(session="s")
        self.assertEqual(len(res_session), 1)
        self.assertEqual(res_session[0]["session"], "s")

    def test_query_questions_by_marks(self):
        """Querying questions by mark range."""
        res_marks = self.repo.query_questions(min_marks=6, max_marks=10)
        self.assertEqual(len(res_marks), 2)
        q_marks = {q["total_marks"] for q in res_marks}
        self.assertEqual(q_marks, {7, 8})

    def test_query_parts_by_topic(self):
        """Querying parts by topic code returns isolated part assets and metadata."""
        parts_1_2 = self.repo.query_parts(topic_code="1.2")
        self.assertEqual(len(parts_1_2), 2)
        labels = {p["label"] for p in parts_1_2}
        self.assertEqual(labels, {"a", "b"})

        part_a = next(p for p in parts_1_2 if p["label"] == "a")
        self.assertEqual(part_a["marks"], 3)
        self.assertEqual(part_a["part_image_path"], "questions/q02/part_a.png")
        self.assertEqual(part_a["paper_id"], "9709_w24_qp_12")
        self.assertEqual(part_a["component"], 1)

    def test_query_by_topic_shortcut(self):
        """query_by_topic convenience method retrieves questions for curriculum researchers."""
        res = self.repo.query_by_topic("1.1", component=1)
        self.assertEqual(len(res), 2)

    def test_get_question_by_id(self):
        """get_question returns question details, parts, topics, and paper metadata."""
        q = self.repo.get_question("9709_w24_qp_12_q02")
        self.assertIsNotNone(q)
        self.assertEqual(q["question_number"], 2)
        self.assertEqual(q["total_marks"], 7)
        self.assertTrue(q["has_preamble"])
        self.assertEqual(len(q["parts"]), 2)
        self.assertIn("1.1", q["topics"])
        self.assertIn("1.2", q["topics"])

    def test_list_topics(self):
        """list_topics lists all topics with question/part counts."""
        topics = self.repo.list_topics()
        self.assertGreaterEqual(len(topics), 2)
        code_map = {t["topic_code"]: t for t in topics}
        self.assertIn("1.1", code_map)
        self.assertGreaterEqual(code_map["1.1"]["question_count"], 2)

    def test_query_latency_performance(self):
        """Sub-10ms query execution latency."""
        t0 = time.perf_counter()
        for _ in range(20):
            self.repo.query_questions(topic_code="1.1", component=1)
        elapsed = (time.perf_counter() - t0) / 20
        self.assertLess(
            elapsed,
            0.010,
            f"Average query took {elapsed * 1000:.2f}ms, expected < 10ms",
        )

    def test_cli_topic_query(self):
        """uv run python -m tools.db.repository query CLI test."""
        cmd = [
            sys.executable,
            "-m",
            "tools.db.repository",
            "query",
            "--db-path",
            str(self.db_path),
            "--topic",
            "1.1",
            "--component",
            "1",
            "--format",
            "json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"CLI error: {proc.stderr}")
        data = json.loads(proc.stdout)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["component"], 1)

    def test_cli_queue_manager_query(self):
        """ppq-queue query CLI test."""
        cmd = [
            sys.executable,
            "-m",
            "tools.queue_manager",
            "query",
            "--db-path",
            str(self.db_path),
            "--topic",
            "1.1",
            "--component",
            "1",
            "--format",
            "table",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"CLI error: {proc.stderr}")
        self.assertIn("9709_w24_qp_12", proc.stdout)
        self.assertIn("Total records: 2", proc.stdout)


if __name__ == "__main__":
    unittest.main()
