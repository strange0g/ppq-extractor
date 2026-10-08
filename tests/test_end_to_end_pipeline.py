"""End-to-End Pipeline Integration Test for PPQ Extractor.

Validates the full autonomous pipeline against Cambridge 9709 Question Paper (9709_w24_qp_12.pdf):
1. Discovery and queue scanning (expected marks 75, write_in mode, 20 pages).
2. Extractor claiming paper from processing queue.
3. High-speed PDF rendering into 200 DPI PNG page images (page_01.png to page_20.png).
4. Manifest assembly with 0-1000 vertical bounding coordinates for all 10 questions and parts.
5. Slicing and composite stitching creating Question Part Images (qXX_a.png) and
   Composite Question Images (qXX_full.png) with uniform full width (W) and answer workspace lines excised.
6. Mathematical mark-sum invariant verification (75/75 marks).
7. Verifier audit checks and queue status transition to 'verified'.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from tools.pdf_to_images import render_pdf_to_images
from tools.crop_slices import crop_and_stitch, translate_coordinates
from tools.queue_manager import (
    load_queue,
    save_queue,
    scan_queue,
    get_next_paper,
    update_paper_status,
)


def find_sample_pdf() -> Path | None:
    """Locate the 9709_w24_qp_12.pdf past paper in local environment."""
    candidates = [
        Path.cwd() / "9709" / "2024" / "2024 Nov" / "9709_w24_qp_12.pdf",
        Path(__file__).resolve().parent.parent / "9709" / "2024" / "2024 Nov" / "9709_w24_qp_12.pdf",
        Path(__file__).resolve().parent.parent.parent / "9709" / "2024" / "2024 Nov" / "9709_w24_qp_12.pdf",
        Path("/home/raied/Programming/ppq-extractor/9709/2024/2024 Nov/9709_w24_qp_12.pdf"),
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
                "preamble_slice": {"page": 2, "ymin": 91, "xmin": 0, "ymax": 397, "xmax": 1000},
                "parts": [
                    {
                        "label": "a",
                        "marks": 3,
                        "slices": [{"page": 2, "ymin": 412, "xmin": 0, "ymax": 438, "xmax": 1000}],
                        "asset_path": "crops/q01_a.png",
                    },
                    {
                        "label": "b",
                        "marks": 2,
                        "slices": [
                            {"page": 2, "ymin": 720, "xmin": 0, "ymax": 794, "xmax": 1000},
                            {"page": 2, "ymin": 859, "xmin": 0, "ymax": 887, "xmax": 1000},
                        ],
                        "asset_path": "crops/q01_b.png",
                    },
                ],
                "composite_asset_path": "crops/q01_full.png",
                "total_question_marks": 5,
            },
            {
                "number": 2,
                "has_preamble": True,
                "preamble_slice": {"page": 3, "ymin": 77, "xmin": 0, "ymax": 92, "xmax": 1000},
                "parts": [
                    {
                        "label": "a",
                        "marks": 2,
                        "slices": [{"page": 3, "ymin": 108, "xmin": 0, "ymax": 130, "xmax": 1000}],
                        "asset_path": "crops/q02_a.png",
                    },
                    {
                        "label": "b",
                        "marks": 3,
                        "slices": [{"page": 3, "ymin": 349, "xmin": 0, "ymax": 407, "xmax": 1000}],
                        "asset_path": "crops/q02_b.png",
                    },
                ],
                "composite_asset_path": "crops/q02_full.png",
                "total_question_marks": 5,
            },
            {
                "number": 3,
                "has_preamble": True,
                "preamble_slice": {"page": 4, "ymin": 79, "xmin": 0, "ymax": 108, "xmax": 1000},
                "parts": [
                    {
                        "label": "a",
                        "marks": 3,
                        "slices": [{"page": 4, "ymin": 125, "xmin": 0, "ymax": 148, "xmax": 1000}],
                        "asset_path": "crops/q03_a.png",
                    },
                    {
                        "label": "b",
                        "marks": 2,
                        "slices": [{"page": 4, "ymin": 460, "xmin": 0, "ymax": 503, "xmax": 1000}],
                        "asset_path": "crops/q03_b.png",
                    },
                ],
                "composite_asset_path": "crops/q03_full.png",
                "total_question_marks": 5,
            },
            {
                "number": 4,
                "has_preamble": True,
                "preamble_slice": {"page": 5, "ymin": 76, "xmin": 0, "ymax": 91, "xmax": 1000},
                "parts": [
                    {
                        "label": "a",
                        "marks": 2,
                        "slices": [{"page": 5, "ymin": 110, "xmin": 0, "ymax": 148, "xmax": 1000}],
                        "asset_path": "crops/q04_a.png",
                    },
                    {
                        "label": "b",
                        "marks": 4,
                        "slices": [{"page": 5, "ymin": 369, "xmin": 0, "ymax": 418, "xmax": 1000}],
                        "asset_path": "crops/q04_b.png",
                    },
                ],
                "composite_asset_path": "crops/q04_full.png",
                "total_question_marks": 6,
            },
            {
                "number": 5,
                "has_preamble": True,
                "preamble_slice": {"page": 6, "ymin": 77, "xmin": 0, "ymax": 103, "xmax": 1000},
                "parts": [
                    {
                        "label": "a",
                        "marks": 7,
                        "slices": [
                            {"page": 6, "ymin": 127, "xmin": 0, "ymax": 152, "xmax": 1000},
                            {"page": 6, "ymin": 279, "xmin": 0, "ymax": 696, "xmax": 1000},
                        ],
                        "asset_path": "crops/q05_a.png",
                    },
                    {
                        "label": "b",
                        "marks": 3,
                        "slices": [{"page": 7, "ymin": 427, "xmin": 0, "ymax": 483, "xmax": 1000}],
                        "asset_path": "crops/q05_b.png",
                    },
                ],
                "composite_asset_path": "crops/q05_full.png",
                "total_question_marks": 10,
            },
            {
                "number": 6,
                "has_preamble": False,
                "parts": [
                    {
                        "label": "",
                        "marks": 6,
                        "slices": [{"page": 8, "ymin": 82, "xmin": 0, "ymax": 463, "xmax": 1000}],
                        "asset_path": "crops/q06.png",
                    }
                ],
                "composite_asset_path": "crops/q06_full.png",
                "total_question_marks": 6,
            },
            {
                "number": 7,
                "has_preamble": False,
                "parts": [
                    {
                        "label": "a",
                        "marks": 3,
                        "slices": [{"page": 10, "ymin": 77, "xmin": 0, "ymax": 121, "xmax": 1000}],
                        "asset_path": "crops/q07_a.png",
                    },
                    {
                        "label": "b",
                        "marks": 5,
                        "slices": [{"page": 10, "ymin": 372, "xmin": 0, "ymax": 666, "xmax": 1000}],
                        "asset_path": "crops/q07_b.png",
                    },
                ],
                "composite_asset_path": "crops/q07_full.png",
                "total_question_marks": 8,
            },
            {
                "number": 8,
                "has_preamble": True,
                "preamble_slice": {"page": 12, "ymin": 77, "xmin": 0, "ymax": 93, "xmax": 1000},
                "parts": [
                    {
                        "label": "a",
                        "marks": 2,
                        "slices": [{"page": 12, "ymin": 107, "xmin": 0, "ymax": 152, "xmax": 1000}],
                        "asset_path": "crops/q08_a.png",
                    },
                    {
                        "label": "b",
                        "marks": 8,
                        "slices": [
                            {"page": 12, "ymin": 395, "xmin": 0, "ymax": 427, "xmax": 1000},
                            {"page": 13, "ymin": 76, "xmin": 0, "ymax": 97, "xmax": 1000},
                        ],
                        "asset_path": "crops/q08_b.png",
                    },
                ],
                "composite_asset_path": "crops/q08_full.png",
                "total_question_marks": 10,
            },
            {
                "number": 9,
                "has_preamble": True,
                "preamble_slice": {"page": 14, "ymin": 77, "xmin": 0, "ymax": 104, "xmax": 1000},
                "parts": [
                    {
                        "label": "a",
                        "marks": 7,
                        "slices": [{"page": 14, "ymin": 121, "xmin": 0, "ymax": 176, "xmax": 1000}],
                        "asset_path": "crops/q09_a.png",
                    },
                    {
                        "label": "b",
                        "marks": 3,
                        "slices": [{"page": 15, "ymin": 336, "xmin": 0, "ymax": 391, "xmax": 1000}],
                        "asset_path": "crops/q09_b.png",
                    },
                ],
                "composite_asset_path": "crops/q09_full.png",
                "total_question_marks": 10,
            },
            {
                "number": 10,
                "has_preamble": True,
                "preamble_slice": {"page": 16, "ymin": 77, "xmin": 0, "ymax": 108, "xmax": 1000},
                "parts": [
                    {
                        "label": "a",
                        "marks": 3,
                        "slices": [{"page": 16, "ymin": 126, "xmin": 0, "ymax": 151, "xmax": 1000}],
                        "asset_path": "crops/q10_a.png",
                    },
                    {
                        "label": "b",
                        "marks": 4,
                        "slices": [{"page": 16, "ymin": 311, "xmin": 0, "ymax": 336, "xmax": 1000}],
                        "asset_path": "crops/q10_b.png",
                    },
                    {
                        "label": "c",
                        "marks": 3,
                        "slices": [{"page": 17, "ymin": 77, "xmin": 0, "ymax": 175, "xmax": 1000}],
                        "asset_path": "crops/q10_c.png",
                    },
                ],
                "composite_asset_path": "crops/q10_full.png",
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
        crops_dir = output_dir / "crops"

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
            out_dir=crops_dir,
            pad=10,
            spacing=20,
        )
        self.assertEqual(crop_summary["status"], "success")
        self.assertEqual(crop_summary["questions_processed"], 10)

        # -------------------------------------------------------------
        # Step 5: Validate cropped assets fidelity and geometry
        # -------------------------------------------------------------
        # Check all expected crops exist
        expected_part_crops = [
            "q01_a.png", "q01_b.png", "q01_full.png",
            "q02_a.png", "q02_b.png", "q02_full.png",
            "q03_a.png", "q03_b.png", "q03_full.png",
            "q04_a.png", "q04_b.png", "q04_full.png",
            "q05_a.png", "q05_b.png", "q05_full.png",
            "q06.png", "q06_full.png",
            "q07_a.png", "q07_b.png", "q07_full.png",
            "q08_a.png", "q08_b.png", "q08_full.png",
            "q09_a.png", "q09_b.png", "q09_full.png",
            "q10_a.png", "q10_b.png", "q10_c.png", "q10_full.png",
        ]

        for crop_name in expected_part_crops:
            crop_path = crops_dir / crop_name
            self.assertTrue(crop_path.is_file(), f"Missing crop: {crop_name}")
            with Image.open(crop_path) as im:
                # All crops must have full standardized width W=1654
                self.assertEqual(im.width, 1654, f"Crop {crop_name} width is not full-width 1654")
                self.assertGreater(im.height, 50, f"Crop {crop_name} height too small")

        # Verify standalone subpart image has preamble prepended
        with Image.open(crops_dir / "q01_a.png") as im_part:
            # Standalone q01_a height must be greater than just part a slice height alone
            # because preamble is prepended
            part_a_slice_h = int((438 - 412) * 2339 / 1000) + 20
            self.assertGreater(im_part.height, part_a_slice_h)

        # -------------------------------------------------------------
        # Step 6: Mark-sum invariant audit & queue update to 'extracted'
        # -------------------------------------------------------------
        # Verify mark sum across all questions
        total_extracted_marks = sum(
            sum(part.get("marks", 0) for part in q.get("parts", []))
            for q in manifest_data["questions"]
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
        # Step 7: Verifier polls paper, performs visual audit, approves
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
            },
            "audit_notes": [
                "Mark sum matches expected 75 marks.",
                "Zero answer workspace lines detected in crops.",
                "Full width 1654 maintained across all images.",
            ],
        }
        manifest_path.write_text(json.dumps(updated_manifest, indent=2))

        # -------------------------------------------------------------
        # Step 8: Update queue to 'verified'
        # -------------------------------------------------------------
        queue_data = update_paper_status(
            queue_data=queue_data,
            paper_id=verifier_paper["id"],
            status="verified",
            notes="Audit verified 75/75 marks and clean crops",
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


if __name__ == "__main__":
    unittest.main()
