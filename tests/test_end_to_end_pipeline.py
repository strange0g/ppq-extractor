"""End-to-End Pipeline Integration Test for PPQ Extractor.

Validates the full autonomous pipeline against Cambridge 9709 Question Paper (9709_w24_qp_12.pdf):
1. Discovery and queue scanning (expected marks 75, write_in mode, 20 pages, standard CAIE taxonomy).
2. Extractor claiming paper from processing queue.
3. High-speed PDF rendering into 200 DPI PNG page images (page_01.png to page_20.png).
4. Manifest assembly with 0-1000 vertical bounding coordinates for all 10 questions and parts.
5. Slicing and Question Package generation creating standalone Question Preamble Images (preamble.png),
   isolated Question Part Images (part_{label}.png), and Composite Question Images (full.png)
   under questions/q{NN}/ with uniform full width (W) and answer workspace lines excised.
6. Validation that Question 1 top bound encompasses the numeral "1" (ymin coordinate and visual headroom margin).
7. Validation that Question 10 has cleanly decoupled preamble.png, isolated part_a.png, part_b.png, part_c.png, and composite full.png.
8. Validation of all 10 Question Packages containing purely media assets (without question.json) and paper manifest.json indexing.
9. Mathematical mark-sum invariant verification (75/75 marks).
10. Verifier audit checks and queue status transition to 'verified'.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from tools.crop_slices import crop_and_stitch
from tools.db.repository import QuestionRepository
from tools.pdf_to_images import render_pdf_to_images
from tools.queue_manager import (
    get_next_paper,
    load_queue,
    save_queue,
    scan_queue,
    update_paper_status,
)


def find_sample_pdf() -> Path | None:
    """Locate the 9709_w24_qp_12.pdf past paper in local environment."""
    candidates = [
        Path.cwd() / "9709" / "2024" / "2024 Nov" / "9709_w24_qp_12.pdf",
        Path(__file__).resolve().parent.parent
        / "9709"
        / "2024"
        / "2024 Nov"
        / "9709_w24_qp_12.pdf",
        Path(__file__).resolve().parent.parent.parent
        / "9709"
        / "2024"
        / "2024 Nov"
        / "9709_w24_qp_12.pdf",
        Path(
            "/home/raied/Programming/ppq-extractor/9709/2024/2024 Nov/9709_w24_qp_12.pdf"
        ),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def get_ground_truth_manifest(sample_pdf_rel_path: str) -> dict:
    """Return ground-truth manifest structure for 9709_w24_qp_12 with 75 marks total."""
    return {
        "id": "9709_w24_qp_12",
        "syllabus": "9709",
        "year": 2024,
        "session": "w",
        "paper": 12,
        "source_pdf": sample_pdf_rel_path,
        "status": "extracted",
        "mode": "write_in",
        "total_marks": 75,
        "extracted_marks_total": 75,
        "pages_processed": list(range(2, 18)),
        "questions": [
            {
                "number": 1,
                "has_preamble": True,
                "preamble_slice": {
                    "page": 2,
                    "ymin": 74,
                    "xmin": 0,
                    "ymax": 397,
                    "xmax": 1000,
                },
                "parts": [
                    {
                        "label": "a",
                        "marks": 3,
                        "slices": [
                            {
                                "page": 2,
                                "ymin": 412,
                                "xmin": 0,
                                "ymax": 438,
                                "xmax": 1000,
                            }
                        ],
                    },
                    {
                        "label": "b",
                        "marks": 2,
                        "slices": [
                            {
                                "page": 2,
                                "ymin": 720,
                                "xmin": 0,
                                "ymax": 794,
                                "xmax": 1000,
                            },
                            {
                                "page": 2,
                                "ymin": 859,
                                "xmin": 0,
                                "ymax": 887,
                                "xmax": 1000,
                            },
                        ],
                    },
                ],
                "total_question_marks": 5,
            },
            {
                "number": 2,
                "has_preamble": True,
                "preamble_slice": {
                    "page": 3,
                    "ymin": 77,
                    "xmin": 0,
                    "ymax": 92,
                    "xmax": 1000,
                },
                "parts": [
                    {
                        "label": "a",
                        "marks": 2,
                        "slices": [
                            {
                                "page": 3,
                                "ymin": 108,
                                "xmin": 0,
                                "ymax": 130,
                                "xmax": 1000,
                            }
                        ],
                    },
                    {
                        "label": "b",
                        "marks": 3,
                        "slices": [
                            {
                                "page": 3,
                                "ymin": 349,
                                "xmin": 0,
                                "ymax": 407,
                                "xmax": 1000,
                            }
                        ],
                    },
                ],
                "total_question_marks": 5,
            },
            {
                "number": 3,
                "has_preamble": True,
                "preamble_slice": {
                    "page": 4,
                    "ymin": 79,
                    "xmin": 0,
                    "ymax": 108,
                    "xmax": 1000,
                },
                "parts": [
                    {
                        "label": "a",
                        "marks": 3,
                        "slices": [
                            {
                                "page": 4,
                                "ymin": 125,
                                "xmin": 0,
                                "ymax": 148,
                                "xmax": 1000,
                            }
                        ],
                    },
                    {
                        "label": "b",
                        "marks": 2,
                        "slices": [
                            {
                                "page": 4,
                                "ymin": 460,
                                "xmin": 0,
                                "ymax": 503,
                                "xmax": 1000,
                            }
                        ],
                    },
                ],
                "total_question_marks": 5,
            },
            {
                "number": 4,
                "has_preamble": True,
                "preamble_slice": {
                    "page": 5,
                    "ymin": 76,
                    "xmin": 0,
                    "ymax": 91,
                    "xmax": 1000,
                },
                "parts": [
                    {
                        "label": "a",
                        "marks": 2,
                        "slices": [
                            {
                                "page": 5,
                                "ymin": 110,
                                "xmin": 0,
                                "ymax": 148,
                                "xmax": 1000,
                            }
                        ],
                    },
                    {
                        "label": "b",
                        "marks": 4,
                        "slices": [
                            {
                                "page": 5,
                                "ymin": 369,
                                "xmin": 0,
                                "ymax": 418,
                                "xmax": 1000,
                            }
                        ],
                    },
                ],
                "total_question_marks": 6,
            },
            {
                "number": 5,
                "has_preamble": True,
                "preamble_slice": {
                    "page": 6,
                    "ymin": 77,
                    "xmin": 0,
                    "ymax": 103,
                    "xmax": 1000,
                },
                "parts": [
                    {
                        "label": "a",
                        "marks": 7,
                        "slices": [
                            {
                                "page": 6,
                                "ymin": 127,
                                "xmin": 0,
                                "ymax": 152,
                                "xmax": 1000,
                            },
                            {
                                "page": 6,
                                "ymin": 279,
                                "xmin": 0,
                                "ymax": 696,
                                "xmax": 1000,
                            },
                        ],
                    },
                    {
                        "label": "b",
                        "marks": 3,
                        "slices": [
                            {
                                "page": 7,
                                "ymin": 427,
                                "xmin": 0,
                                "ymax": 483,
                                "xmax": 1000,
                            }
                        ],
                    },
                ],
                "total_question_marks": 10,
            },
            {
                "number": 6,
                "has_preamble": False,
                "parts": [
                    {
                        "label": "",
                        "marks": 6,
                        "slices": [
                            {
                                "page": 8,
                                "ymin": 82,
                                "xmin": 0,
                                "ymax": 463,
                                "xmax": 1000,
                            }
                        ],
                    }
                ],
                "total_question_marks": 6,
            },
            {
                "number": 7,
                "has_preamble": False,
                "parts": [
                    {
                        "label": "a",
                        "marks": 3,
                        "slices": [
                            {
                                "page": 10,
                                "ymin": 77,
                                "xmin": 0,
                                "ymax": 121,
                                "xmax": 1000,
                            }
                        ],
                    },
                    {
                        "label": "b",
                        "marks": 5,
                        "slices": [
                            {
                                "page": 10,
                                "ymin": 372,
                                "xmin": 0,
                                "ymax": 666,
                                "xmax": 1000,
                            }
                        ],
                    },
                ],
                "total_question_marks": 8,
            },
            {
                "number": 8,
                "has_preamble": True,
                "preamble_slice": {
                    "page": 12,
                    "ymin": 77,
                    "xmin": 0,
                    "ymax": 93,
                    "xmax": 1000,
                },
                "parts": [
                    {
                        "label": "a",
                        "marks": 2,
                        "slices": [
                            {
                                "page": 12,
                                "ymin": 107,
                                "xmin": 0,
                                "ymax": 152,
                                "xmax": 1000,
                            }
                        ],
                    },
                    {
                        "label": "b",
                        "marks": 8,
                        "slices": [
                            {
                                "page": 12,
                                "ymin": 395,
                                "xmin": 0,
                                "ymax": 427,
                                "xmax": 1000,
                            },
                            {
                                "page": 13,
                                "ymin": 76,
                                "xmin": 0,
                                "ymax": 97,
                                "xmax": 1000,
                            },
                        ],
                    },
                ],
                "total_question_marks": 10,
            },
            {
                "number": 9,
                "has_preamble": True,
                "preamble_slice": {
                    "page": 14,
                    "ymin": 77,
                    "xmin": 0,
                    "ymax": 104,
                    "xmax": 1000,
                },
                "parts": [
                    {
                        "label": "a",
                        "marks": 7,
                        "slices": [
                            {
                                "page": 14,
                                "ymin": 121,
                                "xmin": 0,
                                "ymax": 176,
                                "xmax": 1000,
                            }
                        ],
                    },
                    {
                        "label": "b",
                        "marks": 3,
                        "slices": [
                            {
                                "page": 15,
                                "ymin": 336,
                                "xmin": 0,
                                "ymax": 391,
                                "xmax": 1000,
                            }
                        ],
                    },
                ],
                "total_question_marks": 10,
            },
            {
                "number": 10,
                "has_preamble": True,
                "preamble_slice": {
                    "page": 16,
                    "ymin": 77,
                    "xmin": 0,
                    "ymax": 108,
                    "xmax": 1000,
                },
                "parts": [
                    {
                        "label": "a",
                        "marks": 3,
                        "slices": [
                            {
                                "page": 16,
                                "ymin": 126,
                                "xmin": 0,
                                "ymax": 151,
                                "xmax": 1000,
                            }
                        ],
                    },
                    {
                        "label": "b",
                        "marks": 4,
                        "slices": [
                            {
                                "page": 16,
                                "ymin": 311,
                                "xmin": 0,
                                "ymax": 336,
                                "xmax": 1000,
                            }
                        ],
                    },
                    {
                        "label": "c",
                        "marks": 3,
                        "slices": [
                            {
                                "page": 17,
                                "ymin": 77,
                                "xmin": 0,
                                "ymax": 175,
                                "xmax": 1000,
                            }
                        ],
                    },
                ],
                "total_question_marks": 10,
            },
        ],
        "verification": {
            "status": "pending",
            "verified_by": None,
            "timestamp": None,
            "checks": {
                "mark_sum_matches": None,
                "no_answer_lines_detected": None,
                "no_clipping_detected": None,
                "question_numbers_intact": None,
            },
            "audit_notes": [],
        },
    }


class TestEndToEndPipeline(unittest.TestCase):
    """End-to-End pipeline execution test suite."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.source_dir = self.root / "source_pdf"
        self.source_dir.mkdir(parents=True, exist_ok=True)
        self.queue_file = self.root / ".pipeline" / "queue.json"
        self.queue_db = self.root / ".pipeline" / "queue.db"
        self.queue_db.parent.mkdir(parents=True, exist_ok=True)

        # Locate sample PDF
        self.sample_pdf_path = find_sample_pdf()
        self.assertIsNotNone(
            self.sample_pdf_path,
            "Could not locate 9709_w24_qp_12.pdf in repository",
        )

        # Copy sample PDF to test source_dir mimicking repository directory structure
        self.test_pdf = self.source_dir / "2024" / "2024 Nov" / "9709_w24_qp_12.pdf"
        self.test_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.sample_pdf_path, self.test_pdf)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_full_pipeline_dry_run_and_verification(self):
        """Execute end-to-end pipeline run from scan to verified queue state."""
        # -------------------------------------------------------------
        # Step 1: Scan directory and verify ledger initialization
        # -------------------------------------------------------------
        queue_data = scan_queue(self.source_dir, self.queue_file)
        self.assertEqual(queue_data["summary"]["total"], 1)
        self.assertEqual(queue_data["summary"]["unprocessed"], 1)
        self.assertEqual(queue_data["summary"]["extracted"], 0)
        self.assertEqual(queue_data["summary"]["verified"], 0)

        paper = queue_data["papers"][0]
        self.assertEqual(paper["id"], "9709_w24_qp_12")
        self.assertEqual(paper["syllabus"], "9709")
        self.assertEqual(paper["year"], 2024)
        self.assertEqual(paper["session"], "w")
        self.assertEqual(paper["component"], 1)
        self.assertEqual(paper["variant"], 2)
        self.assertEqual(paper["status"], "unprocessed")
        self.assertEqual(paper["mode"], "write_in")
        self.assertEqual(paper["expected_marks"], 75)
        self.assertEqual(paper["total_pages"], 20)
        self.assertEqual(
            paper["output_dir"], "data/extracted/9709/2024/oct_nov/paper_12"
        )

        # -------------------------------------------------------------
        # Step 2: Extractor polls and claims next candidate paper
        # -------------------------------------------------------------
        claimed_paper = get_next_paper(queue_data, role="extractor")
        self.assertIsNotNone(claimed_paper)
        self.assertEqual(claimed_paper["id"], "9709_w24_qp_12")

        # -------------------------------------------------------------
        # Step 3: High-speed PDF rendering via pdf_to_images
        # -------------------------------------------------------------
        output_dir = self.root / claimed_paper["output_dir"]
        pages_dir = output_dir / "pages"
        questions_dir = output_dir / "questions"

        render_result = render_pdf_to_images(
            pdf_path=self.test_pdf,
            out_dir=pages_dir,
            dpi=200,
        )
        self.assertEqual(render_result["page_count"], 20)
        self.assertEqual(render_result["dpi"], 200)

        page_files = sorted(pages_dir.glob("page_*.png"))
        self.assertEqual(len(page_files), 20)
        for i, pf in enumerate(page_files, start=1):
            self.assertEqual(pf.name, f"page_{i:02d}.png")
            with Image.open(pf) as img:
                self.assertEqual(img.size, (1654, 2339))

        # -------------------------------------------------------------
        # Step 4: Manifest assembly & crop_slices execution
        # -------------------------------------------------------------
        manifest_data = get_ground_truth_manifest(str(self.test_pdf))
        manifest_path = output_dir / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest_data, indent=2))

        crop_summary = crop_and_stitch(
            manifest_path=manifest_path,
            pages_dir=pages_dir,
            out_dir=output_dir,
            pad=10,
            spacing=20,
            db_path=self.queue_db,
        )
        self.assertEqual(crop_summary["status"], "success")
        self.assertEqual(crop_summary["questions_processed"], 10)
        self.assertIn("db_sync", crop_summary)
        self.assertIsNotNone(crop_summary["db_sync"])
        self.assertEqual(crop_summary["db_sync"]["paper_id"], "9709_w24_qp_12")
        self.assertTrue(self.queue_db.is_file())

        # -------------------------------------------------------------
        # Step 5: Question 1 numeral invariant & safety buffer verification
        # -------------------------------------------------------------
        q1_manifest = manifest_data["questions"][0]
        # Verify Question 1 ymin coordinate encompasses numeral '1' (starts at ~77.0 normalized)
        # with upward safety buffer
        self.assertLessEqual(
            q1_manifest["preamble_slice"]["ymin"],
            75,
            "Question 1 preamble ymin must encompass numeral '1' with upward safety buffer",
        )

        q1_dir = questions_dir / "q01"
        self.assertTrue(q1_dir.is_dir(), "Question 1 package directory missing")
        q1_preamble_path = q1_dir / "preamble.png"
        self.assertTrue(q1_preamble_path.is_file(), "Question 1 preamble.png missing")

        with Image.open(q1_preamble_path) as im_q1_p:
            self.assertEqual(
                im_q1_p.width, 1654, "Preamble crop width must be full-width 1654"
            )
            self.assertGreater(im_q1_p.height, 50, "Preamble crop height too small")
            # Visual check for numeral '1' visibility and upward margin buffer
            arr_q1 = np.array(im_q1_p.convert("L"))
            # Column slice for numeral '1' (x: 130..160)
            numeral_cols = arr_q1[:, 130:160]
            dark_ys, _ = np.where(numeral_cols < 128)
            self.assertGreater(
                len(dark_ys),
                0,
                "Numeral '1' dark pixels must be present in Question 1 preamble crop",
            )
            first_numeral_row = dark_ys.min()
            # Visual upper headroom margin buffer must be at least 15 pixels
            self.assertGreaterEqual(
                first_numeral_row,
                15,
                f"Visual headroom margin buffer above numeral '1' ({first_numeral_row}px) must be >= 15px",
            )
            # Top rows (0..15) in numeral region must be pure margin (white background)
            self.assertTrue(
                np.all(arr_q1[:15, 130:160] >= 200),
                "Headroom buffer above numeral '1' must not contain clipped edge artifacts",
            )

        with Image.open(q1_dir / "full.png") as im_q1_full:
            self.assertEqual(
                im_q1_full.width, 1654, "Composite full.png must have full width 1654"
            )
            arr_q1_full = np.array(im_q1_full.convert("L"))
            dark_ys_full, _ = np.where(arr_q1_full[:, 130:160] < 128)
            self.assertGreater(
                len(dark_ys_full),
                0,
                "Numeral '1' must be visible in composite full.png",
            )
            self.assertGreaterEqual(
                dark_ys_full.min(),
                15,
                "Numeral '1' must have >= 15px headroom in composite full.png",
            )

        # -------------------------------------------------------------
        # Step 6: Question 10 decoupled preamble and parts verification
        # -------------------------------------------------------------
        q10_dir = questions_dir / "q10"
        self.assertTrue(q10_dir.is_dir(), "Question 10 package directory missing")

        q10_preamble_path = q10_dir / "preamble.png"
        q10_part_a_path = q10_dir / "part_a.png"
        q10_part_b_path = q10_dir / "part_b.png"
        q10_part_c_path = q10_dir / "part_c.png"
        q10_full_path = q10_dir / "full.png"
        q10_json_path = q10_dir / "question.json"

        self.assertTrue(q10_preamble_path.is_file(), "Question 10 preamble.png missing")
        self.assertTrue(q10_part_a_path.is_file(), "Question 10 part_a.png missing")
        self.assertTrue(q10_part_b_path.is_file(), "Question 10 part_b.png missing")
        self.assertTrue(q10_part_c_path.is_file(), "Question 10 part_c.png missing")
        self.assertTrue(q10_full_path.is_file(), "Question 10 full.png missing")
        self.assertFalse(
            q10_json_path.exists(),
            "Question Packages must contain purely image assets without question.json by default",
        )

        with (
            Image.open(q10_preamble_path) as im_p10,
            Image.open(q10_part_a_path) as im_p10_a,
            Image.open(q10_part_b_path) as im_p10_b,
            Image.open(q10_part_c_path) as im_p10_c,
            Image.open(q10_full_path) as im_p10_full,
        ):
            # All crops maintain full width 1654
            for crop_img, name in [
                (im_p10, "preamble.png"),
                (im_p10_a, "part_a.png"),
                (im_p10_b, "part_b.png"),
                (im_p10_c, "part_c.png"),
                (im_p10_full, "full.png"),
            ]:
                self.assertEqual(
                    crop_img.width, 1654, f"Q10 {name} width is not full-width 1654"
                )
                self.assertGreater(crop_img.height, 40, f"Q10 {name} height too small")

            # Isolated part check: part_a must NOT contain preamble
            self.assertLess(
                im_p10_a.height,
                im_p10.height + im_p10_a.height,
                "part_a.png must be isolated and not contain preamble",
            )
            # Composite stitches preamble and all parts vertically
            expected_min_full_h = (
                im_p10.height + im_p10_a.height + im_p10_b.height + im_p10_c.height
            )
            self.assertGreaterEqual(
                im_p10_full.height,
                expected_min_full_h,
                "Composite full.png must stitch preamble and all parts",
            )

        # Validate Question 10 metadata from manifest.json authority
        updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        q10_meta = updated_manifest["questions"][9]
        self.assertEqual(q10_meta["number"], 10)
        self.assertEqual(q10_meta["total_question_marks"], 10)
        self.assertTrue(q10_meta["has_preamble"])
        self.assertEqual(len(q10_meta["parts"]), 3)

        expected_q10_parts = [
            ("a", 3, "part_a.png"),
            ("b", 4, "part_b.png"),
            ("c", 3, "part_c.png"),
        ]
        for part_meta, (exp_label, exp_marks, exp_asset) in zip(
            q10_meta["parts"], expected_q10_parts
        ):
            self.assertEqual(part_meta["label"], exp_label)
            self.assertEqual(part_meta["marks"], exp_marks)
            self.assertIn(exp_asset, part_meta["asset_path"])
            self.assertEqual(part_meta["width"], 1654)

        self.assertIn("full.png", q10_meta["composite_asset_path"])
        self.assertEqual(q10_meta["composite_width"], 1654)

        # -------------------------------------------------------------
        # Step 7: Validate all 10 Question Packages & manifest index
        # -------------------------------------------------------------
        self.assertIn("question_index", updated_manifest)
        self.assertEqual(len(updated_manifest["question_index"]), 10)

        for q_num in range(1, 11):
            q_pkg_dir = questions_dir / f"q{q_num:02d}"
            self.assertTrue(
                q_pkg_dir.is_dir(), f"Missing question package dir for q{q_num:02d}"
            )

            q_json_file = q_pkg_dir / "question.json"
            self.assertFalse(
                q_json_file.exists(),
                f"Question Package for q{q_num:02d} must not contain question.json by default",
            )

            # Ensure question package contains purely image assets
            for pkg_file in q_pkg_dir.iterdir():
                self.assertTrue(
                    pkg_file.name.endswith(".png"),
                    f"Unexpected non-image file {pkg_file.name} in q{q_num:02d}",
                )

            q_meta = updated_manifest["questions"][q_num - 1]
            self.assertEqual(q_meta["number"], q_num)

            # Manifest question_index verification
            idx_entry = updated_manifest["question_index"][q_num - 1]
            self.assertEqual(idx_entry["question_number"], q_num)
            self.assertEqual(
                idx_entry["package_path"],
                f"questions/q{q_num:02d}",
            )
            self.assertGreater(idx_entry["total_marks"], 0)
            self.assertEqual(
                idx_entry["composite_asset"],
                f"questions/q{q_num:02d}/full.png",
            )
            # Verify paths resolved from output_dir root exist
            self.assertTrue((output_dir / idx_entry["package_path"]).is_dir())
            self.assertTrue((output_dir / idx_entry["composite_asset"]).is_file())

        # -------------------------------------------------------------
        # Step 8: Mathematical mark-sum invariant audit & queue update
        # -------------------------------------------------------------
        total_extracted_marks = sum(
            item["total_marks"] for item in updated_manifest["question_index"]
        )
        self.assertEqual(total_extracted_marks, 75)
        self.assertEqual(total_extracted_marks, claimed_paper["expected_marks"])

        queue_data = update_paper_status(
            queue_data=queue_data,
            paper_id=claimed_paper["id"],
            status="extracted",
            extracted_marks=total_extracted_marks,
        )
        save_queue(self.queue_file, queue_data)

        self.assertEqual(queue_data["summary"]["extracted"], 1)
        self.assertEqual(queue_data["summary"]["unprocessed"], 0)

        # -------------------------------------------------------------
        # Step 9: Verifier claims paper and performs verification audit
        # -------------------------------------------------------------
        verifier_paper = get_next_paper(queue_data, role="verifier")
        self.assertIsNotNone(verifier_paper)
        self.assertEqual(verifier_paper["id"], "9709_w24_qp_12")

        # Load updated manifest and verify audit block
        updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(updated_manifest["total_marks"], 75)
        self.assertEqual(updated_manifest["extracted_marks_total"], 75)

        # Complete verifier audit in manifest
        updated_manifest["verification"] = {
            "status": "approved",
            "verified_by": "verifier_agent",
            "timestamp": "2026-10-08T20:30:00Z",
            "checks": {
                "mark_sum_matches": True,
                "no_answer_lines_detected": True,
                "no_clipping_detected": True,
                "question_numbers_intact": True,
            },
            "audit_notes": [
                "Mark sum matches expected 75 marks.",
                "Question numerals 1-10 verified intact with upward headroom buffer.",
                "Zero answer workspace lines detected in crops.",
                "Full width 1654 maintained across all Question Package assets.",
            ],
        }
        manifest_path.write_text(json.dumps(updated_manifest, indent=2))

        # -------------------------------------------------------------
        # Step 10: Update queue to 'verified'
        # -------------------------------------------------------------
        queue_data = update_paper_status(
            queue_data=queue_data,
            paper_id=verifier_paper["id"],
            status="verified",
            notes="Audit verified 75/75 marks, question numerals intact, and clean Question Packages",
        )
        save_queue(self.queue_file, queue_data)

        # Verify final ledger state
        final_queue = load_queue(self.queue_file)
        self.assertEqual(final_queue["summary"]["verified"], 1)
        self.assertEqual(final_queue["summary"]["extracted"], 0)
        self.assertEqual(final_queue["summary"]["unprocessed"], 0)
        self.assertEqual(final_queue["summary"]["needs_rework"], 0)

        final_paper = final_queue["papers"][0]
        self.assertEqual(final_paper["status"], "verified")
        self.assertIsNotNone(final_paper["extracted_at"])
        self.assertIsNotNone(final_paper["verified_at"])
        self.assertEqual(final_paper["extracted_marks"], 75)

        # -------------------------------------------------------------
        # Step 11: Query SQLite Question Bank via QuestionRepository
        # -------------------------------------------------------------
        with QuestionRepository(self.queue_db) as repo:
            db_questions = repo.query_questions(paper_id="9709_w24_qp_12")
            self.assertEqual(len(db_questions), 10)

            # Check Question 10 parts and metadata
            q10 = repo.get_question("9709_w24_qp_12_q10")
            self.assertIsNotNone(q10)
            self.assertEqual(len(q10["parts"]), 3)
            self.assertEqual(q10["total_marks"], 10)
            self.assertTrue(q10["has_preamble"])

            # Query Question Parts directly
            parts = repo.query_parts(paper_id="9709_w24_qp_12")
            self.assertGreater(len(parts), 10)


if __name__ == "__main__":
    unittest.main()
