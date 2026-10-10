"""Tests for Ticket #21: End-to-End Pipeline Integration & CLI Topic Querying.

Verifies:
1. crop_and_stitch automatically syncs manifest records into SQLite when db is present.
2. Cropping errors abort before opening a database write transaction.
3. Explicit db_path=None or empty string skips syncing.
4. CLI ppq-crop --db-path syncs into specified SQLite database.
5. CLI ppq-crop --no-db or --db-path "" skips syncing.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tools.crop_slices import crop_and_stitch
from tools.db.connection import get_connection


class TestPipelineCropDBSync(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.pages_dir = self.root / "pages"
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.out_dir = self.root / "output"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "test_queue.db"

        # Generate synthetic pages
        self._create_synthetic_page(1)
        self._create_synthetic_page(2)

        # Create valid manifest
        self.manifest_data = {
            "id": "9709_w24_qp_12",
            "syllabus": "9709",
            "year": 2024,
            "session": "w",
            "paper": 12,
            "source_pdf": "data/source/9709_w24_qp_12.pdf",
            "status": "extracted",
            "mode": "write_in",
            "total_pages": 2,
            "total_marks": 10,
            "questions": [
                {
                    "number": 1,
                    "has_preamble": True,
                    "preamble_slice": {
                        "page": 1,
                        "ymin": 100,
                        "ymax": 200,
                        "xmin": 0,
                        "xmax": 1000,
                    },
                    "parts": [
                        {
                            "label": "a",
                            "marks": 4,
                            "topics": ["1.1"],
                            "slices": [
                                {
                                    "page": 1,
                                    "ymin": 250,
                                    "ymax": 350,
                                    "xmin": 0,
                                    "xmax": 1000,
                                }
                            ],
                        },
                        {
                            "label": "b",
                            "marks": 6,
                            "topics": ["1.2"],
                            "slices": [
                                {
                                    "page": 2,
                                    "ymin": 100,
                                    "ymax": 300,
                                    "xmin": 0,
                                    "xmax": 1000,
                                }
                            ],
                        },
                    ],
                }
            ],
        }
        self.manifest_path = self.out_dir / "manifest.json"
        self.manifest_path.write_text(json.dumps(self.manifest_data, indent=2))

    def tearDown(self):
        self.tmpdir.cleanup()

    def _create_synthetic_page(self, page_num: int) -> Path:
        img = Image.new("RGB", (1000, 2000), (245, 245, 245))
        p = self.pages_dir / f"page_{page_num:02d}.png"
        img.save(p)
        return p

    def test_crop_and_stitch_syncs_to_db_on_success(self):
        """crop_and_stitch automatically syncs manifest into SQLite when db_path is provided."""
        res = crop_and_stitch(
            manifest_path=self.manifest_path,
            pages_dir=self.pages_dir,
            out_dir=self.out_dir,
            db_path=self.db_path,
        )

        self.assertEqual(res["status"], "success")
        self.assertIn("db_sync", res)
        self.assertIsNotNone(res["db_sync"])
        self.assertEqual(res["db_sync"]["status"], "success")
        self.assertEqual(res["db_sync"]["paper_id"], "9709_w24_qp_12")

        # Verify database contents
        conn = get_connection(self.db_path)
        try:
            paper = conn.execute(
                "SELECT * FROM papers WHERE id = '9709_w24_qp_12';"
            ).fetchone()
            self.assertIsNotNone(paper)
            self.assertEqual(paper["total_pages"], 2)

            questions = conn.execute(
                "SELECT * FROM questions WHERE paper_id = '9709_w24_qp_12';"
            ).fetchall()
            self.assertEqual(len(questions), 1)
            self.assertEqual(questions[0]["total_marks"], 10)
            self.assertEqual(questions[0]["has_preamble"], 1)

            parts = conn.execute(
                "SELECT * FROM question_parts WHERE question_id = ?;",
                (questions[0]["id"],),
            ).fetchall()
            self.assertEqual(len(parts), 2)

            q_topics = conn.execute(
                "SELECT topic_code FROM question_topics WHERE question_id = ?;",
                (questions[0]["id"],),
            ).fetchall()
            topics_set = {r["topic_code"] for r in q_topics}
            self.assertEqual(topics_set, {"1.1", "1.2"})
        finally:
            conn.close()

    def test_crop_and_stitch_skips_db_when_explicitly_none_or_empty(self):
        """crop_and_stitch skips SQLite sync when db_path=None or empty."""
        res_none = crop_and_stitch(
            manifest_path=self.manifest_path,
            pages_dir=self.pages_dir,
            out_dir=self.out_dir,
            db_path=None,
        )
        self.assertEqual(res_none["status"], "success")
        self.assertIsNone(res_none.get("db_sync"))
        self.assertFalse(self.db_path.exists())

        res_empty = crop_and_stitch(
            manifest_path=self.manifest_path,
            pages_dir=self.pages_dir,
            out_dir=self.out_dir,
            db_path="",
        )
        self.assertEqual(res_empty["status"], "success")
        self.assertIsNone(res_empty.get("db_sync"))

    def test_cropping_error_aborts_before_database_transaction(self):
        """Cropping failure aborts before opening DB write transaction, preventing partial ingestion."""
        # Corrupt manifest coordinates with invalid ymin >= ymax
        bad_manifest = dict(self.manifest_data)
        bad_manifest["questions"] = [
            {
                "number": 1,
                "has_preamble": False,
                "parts": [
                    {
                        "label": "a",
                        "marks": 5,
                        "slices": [
                            {
                                "page": 1,
                                "ymin": 500,
                                "ymax": 400,  # Invalid: ymin >= ymax
                                "xmin": 0,
                                "xmax": 1000,
                            }
                        ],
                    }
                ],
            }
        ]
        bad_manifest_path = self.out_dir / "bad_manifest.json"
        bad_manifest_path.write_text(json.dumps(bad_manifest, indent=2))

        # Ensure DB does not have any records
        with self.assertRaises(ValueError):
            crop_and_stitch(
                manifest_path=bad_manifest_path,
                pages_dir=self.pages_dir,
                out_dir=self.out_dir,
                db_path=self.db_path,
            )

        if self.db_path.exists():
            conn = get_connection(self.db_path)
            try:
                row = conn.execute(
                    "SELECT * FROM papers WHERE id = '9709_w24_qp_12';"
                ).fetchone()
                self.assertIsNone(
                    row, "No row should be written to DB when cropping fails"
                )
            finally:
                conn.close()

    def test_ppq_crop_cli_with_db_path(self):
        """ppq-crop CLI writes to SQLite when --db-path is passed."""
        cmd = [
            sys.executable,
            "-m",
            "tools.crop_slices",
            "--manifest",
            str(self.manifest_path),
            "--pages-dir",
            str(self.pages_dir),
            "--out-dir",
            str(self.out_dir),
            "--db-path",
            str(self.db_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"CLI error: {proc.stderr}")
        data = json.loads(proc.stdout)
        self.assertEqual(data["status"], "success")
        self.assertIn("db_sync", data)
        self.assertEqual(data["db_sync"]["paper_id"], "9709_w24_qp_12")
        self.assertTrue(self.db_path.exists())

    def test_ppq_crop_cli_with_no_db(self):
        """ppq-crop CLI skips SQLite sync when --no-db is passed."""
        custom_db = self.root / "should_not_exist.db"
        cmd = [
            sys.executable,
            "-m",
            "tools.crop_slices",
            "--manifest",
            str(self.manifest_path),
            "--pages-dir",
            str(self.pages_dir),
            "--out-dir",
            str(self.out_dir),
            "--no-db",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"CLI error: {proc.stderr}")
        data = json.loads(proc.stdout)
        self.assertEqual(data["status"], "success")
        self.assertIsNone(data.get("db_sync"))
        self.assertFalse(custom_db.exists())


if __name__ == "__main__":
    unittest.main()
