#!/usr/bin/env python3
"""Tests for code review fixes.

Validates:
1. Domain vocabulary: no 'subpart' in tools/db/migrations.py, tools/db/sync.py, tests/test_db_sync.py.
2. Pydantic v2 domain models in tools/db/models.py and re-exported in tools/db.
3. QuestionRepository returns typed models with dictionary compatibility and .to_dict().
4. SQLite LIMIT/OFFSET pagination fix when offset is specified without limit.
5. Alias --skip-question-json in tools/crop_slices.py.
6. Shared CLI query options and WHERE clause builder.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path


class TestReviewFixes(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent

    def test_domain_vocabulary_no_subpart_in_target_files(self):
        """Ensure 'subpart' does not occur in target files."""
        target_files = [
            self.repo_root / "tools" / "db" / "migrations.py",
            self.repo_root / "tools" / "db" / "sync.py",
            self.repo_root / "tests" / "test_db_sync.py",
        ]
        subpart_pattern = re.compile(r"\bsubpart(s)?\b", re.IGNORECASE)

        for file_path in target_files:
            self.assertTrue(file_path.is_file(), f"File {file_path} does not exist")
            content = file_path.read_text(encoding="utf-8")
            matches = list(subpart_pattern.finditer(content))
            self.assertEqual(
                len(matches),
                0,
                f"Found {len(matches)} occurrences of prohibited term 'subpart' in {file_path.name}",
            )

    def test_pydantic_models_exported_and_valid(self):
        """Pydantic models are defined in tools/db/models.py and exported via tools.db."""
        from tools.db import (
            PaperModel,
            QuestionModel,
            QuestionPartModel,
            QuestionQueryFilter,
            SliceModel,
            TopicModel,
        )

        part = QuestionPartModel(
            id="q1_a",
            question_id="q1",
            label="a",
            part_label="a",
            marks=3,
            topics=["1.1"],
        )
        self.assertEqual(part.label, "a")
        self.assertEqual(part["label"], "a")
        self.assertEqual(part.to_dict()["marks"], 3)

        q = QuestionModel(
            id="q1",
            paper_id="paper_1",
            question_number=1,
            total_marks=5,
            parts=[part],
            topics=["1.1"],
        )
        self.assertEqual(q.question_number, 1)
        self.assertEqual(q["question_number"], 1)
        self.assertEqual(len(q.parts), 1)
        self.assertEqual(q.to_dict()["id"], "q1")

        paper = PaperModel(
            id="9709_w24_qp_12",
            syllabus="9709",
            year=2024,
            session="w",
            session_slug="oct_nov",
            component=1,
            variant=2,
            source_pdf="test.pdf",
            status="extracted",
            total_pages=12,
            mode="write_in",
            expected_marks=75,
            output_dir="data/extracted/9709/2024/oct_nov/paper_12",
        )
        self.assertEqual(paper.year, 2024)
        self.assertEqual(paper["syllabus"], "9709")
        self.assertEqual(paper.to_dict()["status"], "extracted")

        topic = TopicModel(
            topic_code="1.1",
            title="Quadratics",
            syllabus="9709",
        )
        self.assertEqual(topic.topic_code, "1.1")
        self.assertEqual(topic["title"], "Quadratics")

        slice_model = SliceModel(
            question_id="q1",
            kind="part",
            page=2,
            ymin=100.0,
            ymax=400.0,
        )
        self.assertEqual(slice_model.page, 2)
        self.assertEqual(slice_model["ymin"], 100.0)

        q_filter = QuestionQueryFilter(
            topic_code="1.1",
            syllabus="9709",
            year=2024,
        )
        self.assertEqual(q_filter.topic_code, "1.1")

    def test_repository_returns_typed_models_and_offset_without_limit(self):
        """QuestionRepository returns typed models and supports offset without limit."""
        from tools.db import QuestionModel, QuestionPartModel, QuestionRepository
        from tools.db.migrations import run_migrations, seed_syllabus_topics
        from tools.db.sync import sync_manifest_to_db

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        run_migrations(conn)
        seed_syllabus_topics(conn)

        manifest_data = {
            "schema_version": "2.0",
            "paper_id": "9709_w24_qp_12",
            "mode": "write_in",
            "page_count": 12,
            "questions": [
                {
                    "question_number": 1,
                    "total_marks": 4,
                    "taxonomy": {"topics": [{"code": "1.1", "title": "Quadratics"}]},
                    "parts": [
                        {
                            "label": "a",
                            "marks": 4,
                            "taxonomy": {"topics": [{"code": "1.1"}]},
                            "slices": [{"page": 2, "ymin": 100, "ymax": 300}],
                        }
                    ],
                },
                {
                    "question_number": 2,
                    "total_marks": 6,
                    "taxonomy": {"topics": [{"code": "1.2", "title": "Functions"}]},
                    "parts": [
                        {
                            "label": "a",
                            "marks": 6,
                            "taxonomy": {"topics": [{"code": "1.2"}]},
                            "slices": [{"page": 3, "ymin": 100, "ymax": 400}],
                        }
                    ],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            m_path = Path(tmpdir) / "manifest.json"
            m_path.write_text(json.dumps(manifest_data, indent=2))
            sync_manifest_to_db(m_path, conn=conn)

            repo = QuestionRepository(conn=conn)

            # Query questions returns QuestionModel instances
            all_questions = repo.query_questions()
            self.assertEqual(len(all_questions), 2)
            self.assertIsInstance(all_questions[0], QuestionModel)
            self.assertEqual(all_questions[0].question_number, 1)
            # Dict compatibility
            self.assertEqual(all_questions[0]["question_number"], 1)
            self.assertEqual(all_questions[0].to_dict()["question_number"], 1)

            # Pagination: offset without limit
            offset_questions = repo.query_questions(offset=1)
            self.assertEqual(len(offset_questions), 1)
            self.assertEqual(offset_questions[0].question_number, 2)

            # Query parts returns QuestionPartModel instances
            all_parts = repo.query_parts()
            self.assertEqual(len(all_parts), 2)
            self.assertIsInstance(all_parts[0], QuestionPartModel)
            self.assertEqual(all_parts[0]["marks"], 4)

            # Part pagination: offset without limit
            offset_parts = repo.query_parts(offset=1)
            self.assertEqual(len(offset_parts), 1)
            self.assertEqual(offset_parts[0].question_number, 2)

    def test_crop_slices_cli_accepts_skip_question_json(self):
        """tools/crop_slices.py parser accepts --skip-question-json."""
        import subprocess

        result = subprocess.run(
            ["uv", "run", "python", "-m", "tools.crop_slices", "--help"],
            capture_output=True,
            text=True,
            cwd=str(self.repo_root),
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--skip-question-json", result.stdout)
        self.assertIn("--emit-question-json", result.stdout)

    def test_shared_query_cli_arguments_helper(self):
        """Shared add_query_arguments helper populates query parser consistently."""
        from tools.db.repository import add_query_arguments

        parser = argparse.ArgumentParser()
        add_query_arguments(parser)
        args = parser.parse_args(["--topic", "1.1", "--year", "2024", "--parts"])
        self.assertEqual(args.topic_code, "1.1")
        self.assertEqual(args.year, 2024)
        self.assertTrue(args.parts)


if __name__ == "__main__":
    unittest.main()
