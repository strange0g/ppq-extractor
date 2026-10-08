"""Unit and integration tests for tools.crop_slices module."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

try:
    from tools.crop_slices import (
        crop_and_stitch,
        translate_coordinates,
        _format_part_naming,
    )
except ImportError:
    crop_and_stitch = None
    translate_coordinates = None
    _format_part_naming = None


class TestCropSlices(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.pages_dir = self.root / "pages"
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.crops_dir = self.root / "crops"
        self.crops_dir.mkdir(parents=True, exist_ok=True)

        # Page dimensions: W=1000, H=2000
        self.page_width = 1000
        self.page_height = 2000

        # Create two distinct synthetic test pages
        self._create_synthetic_page(page_num=1, bg_color=(240, 240, 240))
        self._create_synthetic_page(page_num=2, bg_color=(230, 230, 230))
        self._create_synthetic_page(page_num=3, bg_color=(220, 220, 220))

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_synthetic_page(self, page_num: int, bg_color: tuple[int, int, int]) -> Path:
        img = Image.new("RGB", (self.page_width, self.page_height), bg_color)
        draw = ImageDraw.Draw(img)
        # Add distinctive markers across the page vertically
        for y in range(0, self.page_height, 200):
            draw.line([(0, y), (self.page_width, y)], fill=(100, 100, 100), width=2)
            draw.text((50, y + 20), f"P{page_num} Y={y}", fill=(0, 0, 0))

        # Distinct colored bands for easy verification of content
        # Band 1: y=200 to 400 (normalized 100 to 200) -> Red
        draw.rectangle([(0, 200), (self.page_width, 400)], fill=(255, 200, 200))
        # Band 2: y=600 to 800 (normalized 300 to 400) -> Green
        draw.rectangle([(0, 600), (self.page_width, 800)], fill=(200, 255, 200))
        # Band 3: y=1000 to 1200 (normalized 500 to 600) -> Blue
        draw.rectangle([(0, 1000), (self.page_width, 1200)], fill=(200, 200, 255))

        page_path = self.pages_dir / f"page_{page_num:02d}.png"
        img.save(page_path)
        return page_path

    def test_coordinate_translation_and_clamping(self):
        """Test full-width coordinate translation and +10px vertical padding clamping."""
        if translate_coordinates is None:
            self.fail("tools.crop_slices or translate_coordinates not implemented")

        # Page size: 1000x2000
        # Normal range: ymin=200 (y=400px), ymax=400 (y=800px), pad=10
        # Expected: x1=0, x2=1000, y1=max(0, 400-10)=390, y2=min(2000, 800+10)=810
        x1, y1, x2, y2 = translate_coordinates(
            ymin=200, ymax=400, page_width=1000, page_height=2000, pad=10
        )
        self.assertEqual(x1, 0)
        self.assertEqual(x2, 1000)
        self.assertEqual(y1, 390)
        self.assertEqual(y2, 810)

        # Top boundary clamping: ymin=0
        # Expected: y1=max(0, 0-10)=0
        x1, y1, x2, y2 = translate_coordinates(
            ymin=0, ymax=100, page_width=1000, page_height=2000, pad=10
        )
        self.assertEqual(x1, 0)
        self.assertEqual(x2, 1000)
        self.assertEqual(y1, 0)
        self.assertEqual(y2, 210)

        # Bottom boundary clamping: ymax=1000
        # Expected: y2=min(2000, 2000+10)=2000
        x1, y1, x2, y2 = translate_coordinates(
            ymin=900, ymax=1000, page_width=1000, page_height=2000, pad=10
        )
        self.assertEqual(x1, 0)
        self.assertEqual(x2, 1000)
        self.assertEqual(y1, 1790)
        self.assertEqual(y2, 2000)

        # Force full width x1=0, x2=page_width
        x1, y1, x2, y2 = translate_coordinates(
            ymin=100, ymax=200, page_width=1654, page_height=2339, pad=10
        )
        self.assertEqual(x1, 0)
        self.assertEqual(x2, 1654)

    def test_standalone_part_generation_with_preamble(self):
        """Test question preamble is cropped once to preamble.png and part is cropped in isolation to part_a.png."""
        if crop_and_stitch is None:
            self.fail("tools.crop_slices or crop_and_stitch not implemented")

        # Manifest with Question 1 having preamble and subpart (a)
        # Preamble: ymin=100, ymax=200 -> on H=2000: y=200 to 400 (+-10 pad -> 190 to 410, H=220)
        # Part a:   ymin=300, ymax=400 -> on H=2000: y=600 to 800 (+-10 pad -> 590 to 810, H=220)
        manifest_data = {
            "id": "test_paper_01",
            "questions": [
                {
                    "number": 1,
                    "has_preamble": True,
                    "preamble_slice": {
                        "page": 1,
                        "ymin": 100,
                        "xmin": 0,
                        "ymax": 200,
                        "xmax": 1000,
                    },
                    "parts": [
                        {
                            "label": "a",
                            "marks": 3,
                            "slices": [
                                {
                                    "page": 1,
                                    "ymin": 300,
                                    "xmin": 0,
                                    "ymax": 400,
                                    "xmax": 1000,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        manifest_file = self.root / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        crop_and_stitch(manifest_file, self.pages_dir, self.crops_dir, pad=10, spacing=20)

        q1_dir = self.crops_dir / "questions" / "q01"
        self.assertTrue(q1_dir.is_dir(), f"Question package dir {q1_dir} does not exist")

        preamble_path = q1_dir / "preamble.png"
        self.assertTrue(preamble_path.is_file(), f"Expected preamble {preamble_path} not found")

        part_img_path = q1_dir / "part_a.png"
        self.assertTrue(part_img_path.is_file(), f"Expected isolated part {part_img_path} not found")

        with Image.open(preamble_path) as im_p:
            self.assertEqual(im_p.size, (1000, 220))
            self.assertEqual(im_p.getpixel((500, 100)), (255, 200, 200))  # Red band

        with Image.open(part_img_path) as im:
            # Standalone isolated part must NOT contain preamble -> H = 220
            self.assertEqual(im.size, (1000, 220))
            # Green band from page 1 part slice
            self.assertEqual(im.getpixel((500, 100)), (200, 255, 200))

    def test_composite_question_generation_omits_workspace(self):
        """Test full.png stitches preamble and all parts vertically with 20px divider."""
        if crop_and_stitch is None:
            self.fail("tools.crop_slices or crop_and_stitch not implemented")

        # Question 1 with preamble and two subparts (a and b)
        # Workspace lines exist between part a (ends at 400) and part b (starts at 500)
        # Part b is on page 2: ymin=100, ymax=200 -> H=220 (pad 10)
        manifest_data = {
            "id": "test_paper_02",
            "questions": [
                {
                    "number": 1,
                    "has_preamble": True,
                    "preamble_slice": {
                        "page": 1,
                        "ymin": 100,
                        "xmin": 0,
                        "ymax": 200,
                        "xmax": 1000,
                    },
                    "parts": [
                        {
                            "label": "a",
                            "marks": 3,
                            "slices": [
                                {
                                    "page": 1,
                                    "ymin": 300,
                                    "xmin": 0,
                                    "ymax": 400,
                                    "xmax": 1000,
                                }
                            ],
                        },
                        {
                            "label": "b",
                            "marks": 4,
                            "slices": [
                                {
                                    "page": 2,
                                    "ymin": 100,
                                    "xmin": 0,
                                    "ymax": 200,
                                    "xmax": 1000,
                                }
                            ],
                        },
                    ],
                }
            ],
        }
        manifest_file = self.root / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        crop_and_stitch(manifest_file, self.pages_dir, self.crops_dir, pad=10, spacing=20)

        composite_path = self.crops_dir / "questions" / "q01" / "full.png"
        self.assertTrue(composite_path.is_file(), f"Composite crop not found: {composite_path}")

        with Image.open(composite_path) as im:
            # 3 slices: preamble (220) + divider (20) + part a (220) + divider (20) + part b (220) = 700
            self.assertEqual(im.size, (1000, 700))

            # Dividers at [220..240] and [460..480] should be pure white
            for dy in range(220, 240):
                self.assertEqual(im.getpixel((500, dy)), (255, 255, 255))
            for dy in range(460, 480):
                self.assertEqual(im.getpixel((500, dy)), (255, 255, 255))

            # Preamble content (page 1 red band)
            self.assertEqual(im.getpixel((500, 100)), (255, 200, 200))
            # Part a content (page 1 green band)
            self.assertEqual(im.getpixel((500, 300)), (200, 255, 200))
            # Part b content (page 2 red band)
            self.assertEqual(im.getpixel((500, 550)), (255, 200, 200))

    def test_single_part_question_without_preamble(self):
        """Test single-part question without preamble (direct crop, no preamble.png)."""
        if crop_and_stitch is None:
            self.fail("tools.crop_slices or crop_and_stitch not implemented")

        # Question 2 without preamble, 1 part
        # ymin=500, ymax=600 -> on H=2000: y=1000 to 1200 (+-10 pad -> 990 to 1210, H=220)
        manifest_data = {
            "id": "test_paper_03",
            "questions": [
                {
                    "number": 2,
                    "has_preamble": False,
                    "parts": [
                        {
                            "label": "a",
                            "marks": 5,
                            "slices": [
                                {
                                    "page": 1,
                                    "ymin": 500,
                                    "xmin": 0,
                                    "ymax": 600,
                                    "xmax": 1000,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        manifest_file = self.root / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        crop_and_stitch(manifest_file, self.pages_dir, self.crops_dir, pad=10, spacing=20)

        q2_dir = self.crops_dir / "questions" / "q02"
        self.assertTrue(q2_dir.is_dir())
        self.assertFalse((q2_dir / "preamble.png").exists(), "preamble.png should not exist when has_preamble is False")

        part_img = q2_dir / "part_a.png"
        comp_img = q2_dir / "full.png"
        self.assertTrue(part_img.is_file())
        self.assertTrue(comp_img.is_file())

        with Image.open(part_img) as im:
            self.assertEqual(im.size, (1000, 220))
            # Blue band content
            self.assertEqual(im.getpixel((500, 100)), (200, 200, 255))

        with Image.open(comp_img) as im:
            self.assertEqual(im.size, (1000, 220))

    def test_manifest_updating_with_asset_paths_and_dimensions(self):
        """Test manifest.json and question.json metadata generation and indexing."""
        if crop_and_stitch is None:
            self.fail("tools.crop_slices or crop_and_stitch not implemented")

        manifest_data = {
            "id": "test_paper_04",
            "questions": [
                {
                    "number": 1,
                    "has_preamble": True,
                    "preamble_slice": {
                        "page": 1,
                        "ymin": 100,
                        "xmin": 0,
                        "ymax": 200,
                        "xmax": 1000,
                    },
                    "parts": [
                        {
                            "label": "a",
                            "marks": 3,
                            "slices": [
                                {
                                    "page": 1,
                                    "ymin": 300,
                                    "xmin": 0,
                                    "ymax": 400,
                                    "xmax": 1000,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        manifest_file = self.root / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        result = crop_and_stitch(manifest_file, self.pages_dir, self.crops_dir, pad=10, spacing=20)

        # Read back updated manifest from disk
        updated = json.loads(manifest_file.read_text())
        q1 = updated["questions"][0]
        part_a = q1["parts"][0]

        # Verify part asset_path and dimensions in manifest
        self.assertIn("part_a.png", part_a["asset_path"])
        self.assertEqual(part_a["width"], 1000)
        self.assertEqual(part_a["height"], 220)

        # Verify composite asset path and dimensions
        self.assertIn("full.png", q1["composite_asset_path"])
        self.assertEqual(q1["composite_width"], 1000)
        self.assertEqual(q1["composite_height"], 460)

        # Verify question_index in manifest
        self.assertIn("question_index", updated)
        self.assertEqual(len(updated["question_index"]), 1)
        idx_entry = updated["question_index"][0]
        self.assertEqual(idx_entry["question_number"], 1)
        self.assertEqual(idx_entry["package_path"], "questions/q01/question.json")
        self.assertEqual(idx_entry["total_marks"], 3)
        self.assertEqual(idx_entry["composite_asset"], "questions/q01/full.png")

        # Verify atomic question.json file
        q_json_path = self.crops_dir / "questions" / "q01" / "question.json"
        self.assertTrue(q_json_path.is_file(), f"question.json not found at {q_json_path}")
        q_data = json.loads(q_json_path.read_text())

        self.assertEqual(q_data["id"], "test_paper_04_q01")
        self.assertEqual(q_data["paper_id"], "test_paper_04")
        self.assertEqual(q_data["question_number"], 1)
        self.assertEqual(q_data["total_marks"], 3)

        self.assertTrue(q_data["preamble"]["present"])
        self.assertEqual(q_data["preamble"]["asset_path"], "preamble.png")
        self.assertEqual(q_data["preamble"]["dimensions"]["width"], 1000)
        self.assertEqual(q_data["preamble"]["dimensions"]["height"], 220)

        self.assertEqual(len(q_data["parts"]), 1)
        part_meta = q_data["parts"][0]
        self.assertEqual(part_meta["label"], "a")
        self.assertEqual(part_meta["marks"], 3)
        self.assertEqual(part_meta["isolated_asset_path"], "part_a.png")
        self.assertEqual(part_meta["context_dependencies"], ["preamble"])
        self.assertEqual(part_meta["dimensions"]["width"], 1000)
        self.assertEqual(part_meta["dimensions"]["height"], 220)

        self.assertEqual(q_data["composite"]["asset_path"], "full.png")
        self.assertEqual(q_data["composite"]["dimensions"]["width"], 1000)
        self.assertEqual(q_data["composite"]["dimensions"]["height"], 460)

    def test_cli_invocation(self):
        """Test CLI execution with standard flags."""
        manifest_data = {
            "id": "test_paper_cli",
            "questions": [
                {
                    "number": 1,
                    "has_preamble": False,
                    "parts": [
                        {
                            "label": "a",
                            "marks": 2,
                            "slices": [
                                {
                                    "page": 1,
                                    "ymin": 100,
                                    "xmin": 0,
                                    "ymax": 200,
                                    "xmax": 1000,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        manifest_file = self.root / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        cmd = [
            sys.executable,
            "-m",
            "tools.crop_slices",
            "--manifest",
            str(manifest_file),
            "--pages-dir",
            str(self.pages_dir),
            "--out-dir",
            str(self.crops_dir),
            "--pad",
            "10",
            "--spacing",
            "20",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"CLI exited with error: {proc.stderr}")

        output = json.loads(proc.stdout)
        self.assertIn("crops_count", output)
        self.assertTrue((self.crops_dir / "questions" / "q01" / "part_a.png").is_file())
        self.assertTrue((self.crops_dir / "questions" / "q01" / "full.png").is_file())
        self.assertTrue((self.crops_dir / "questions" / "q01" / "question.json").is_file())

    def test_invalid_coordinates_raise_error(self):
        """Test invalid coordinates raise ValueError."""
        if translate_coordinates is None:
            self.fail("tools.crop_slices or translate_coordinates not implemented")

        # ymin >= ymax
        with self.assertRaises(ValueError):
            translate_coordinates(ymin=500, ymax=400, page_width=1000, page_height=2000)

        # ymin < 0 or ymax > 1000
        with self.assertRaises(ValueError):
            translate_coordinates(ymin=-10, ymax=200, page_width=1000, page_height=2000)
        with self.assertRaises(ValueError):
            translate_coordinates(ymin=100, ymax=1001, page_width=1000, page_height=2000)

    def test_end_to_end_multi_part_and_composite(self):
        """End-to-end test validating multi-part questions, preamble attachment, and composite stitching."""
        # Multi-part question across 2 pages with preamble
        manifest_data = {
            "id": "9709_w24_qp_12",
            "syllabus": "9709",
            "year": 2024,
            "session": "w",
            "paper": 12,
            "questions": [
                {
                    "number": 1,
                    "has_preamble": True,
                    "preamble_slice": {
                        "page": 1,
                        "ymin": 100,
                        "xmin": 0,
                        "ymax": 200,
                        "xmax": 1000,
                    },
                    "parts": [
                        {
                            "label": "a",
                            "marks": 3,
                            "slices": [
                                {
                                    "page": 1,
                                    "ymin": 300,
                                    "xmin": 0,
                                    "ymax": 400,
                                    "xmax": 1000,
                                }
                            ],
                        },
                        {
                            "label": "b",
                            "marks": 4,
                            "slices": [
                                {
                                    "page": 2,
                                    "ymin": 150,
                                    "xmin": 0,
                                    "ymax": 250,
                                    "xmax": 1000,
                                }
                            ],
                        },
                    ],
                },
                {
                    "number": 2,
                    "has_preamble": False,
                    "parts": [
                        {
                            "label": "a",
                            "marks": 5,
                            "slices": [
                                {
                                    "page": 3,
                                    "ymin": 100,
                                    "xmin": 0,
                                    "ymax": 300,
                                    "xmax": 1000,
                                }
                            ],
                        }
                    ],
                },
            ],
        }
        manifest_file = self.root / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        result = crop_and_stitch(manifest_file, self.pages_dir, self.crops_dir, pad=10, spacing=20)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["questions_processed"], 2)
        # Q1 has preamble, part a, part b, composite (4). Q2 has part a, composite (2). Total = 6.
        self.assertEqual(result["crops_count"], 6)

        # Verify Q1 assets
        q1_dir = self.crops_dir / "questions" / "q01"
        self.assertTrue((q1_dir / "preamble.png").is_file())
        self.assertTrue((q1_dir / "part_a.png").is_file())
        self.assertTrue((q1_dir / "part_b.png").is_file())
        self.assertTrue((q1_dir / "full.png").is_file())
        self.assertTrue((q1_dir / "question.json").is_file())

        # Verify Q2 assets
        q2_dir = self.crops_dir / "questions" / "q02"
        self.assertFalse((q2_dir / "preamble.png").exists())
        self.assertTrue((q2_dir / "part_a.png").is_file())
        self.assertTrue((q2_dir / "full.png").is_file())
        self.assertTrue((q2_dir / "question.json").is_file())

        # Check updated manifest
        updated = json.loads(manifest_file.read_text())
        self.assertEqual(len(updated["question_index"]), 2)
        self.assertEqual(updated["question_index"][0]["package_path"], "questions/q01/question.json")
        self.assertEqual(updated["question_index"][1]["package_path"], "questions/q02/question.json")

    def test_multi_slice_preamble_and_standalone_whole_question(self):
        """Test handling of multi-slice preambles and standalone whole questions."""
        manifest_data = {
            "paper_id": "9709_w24_qp_12",
            "questions": [
                {
                    "number": 1,
                    "has_preamble": True,
                    "preamble_slices": [
                        {"page": 1, "box_1000": [100, 0, 200, 1000]},
                        {"page": 2, "box_1000": [100, 0, 150, 1000]},
                    ],
                    "parts": [
                        {
                            "label": "(a)",
                            "slices": [
                                {"page": 2, "box_1000": [200, 0, 300, 1000]}
                            ],
                        }
                    ],
                },
                {
                    "number": 2,
                    "kind": "whole",
                    "page": 2,
                    "box_1000": [400, 0, 600, 1000],
                    "marks": 6,
                },
            ],
        }
        manifest_file = self.root / "manifest_multi.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        result = crop_and_stitch(manifest_file, self.pages_dir, self.crops_dir, pad=10, spacing=20)
        self.assertEqual(result["status"], "success")

        # Q1 has preamble.png, part_a.png, full.png, question.json
        q1_dir = self.crops_dir / "questions" / "q01"
        self.assertTrue((q1_dir / "preamble.png").is_file())
        self.assertTrue((q1_dir / "part_a.png").is_file())
        self.assertTrue((q1_dir / "full.png").is_file())
        self.assertTrue((q1_dir / "question.json").is_file())

        # Q2 has whole question: part.png or part_whole.png and full.png
        q2_dir = self.crops_dir / "questions" / "q02"
        self.assertTrue((q2_dir / "full.png").is_file())
        self.assertTrue((q2_dir / "question.json").is_file())
        self.assertTrue((q2_dir / "part.png").is_file() or (q2_dir / "part_whole.png").is_file() or (q2_dir / "part_1.png").is_file())

    def test_format_part_naming_helper(self):
        """Test _format_part_naming helper cleans labels and formats ids."""
        # Labeled part
        part = {"label": "(a)", "part_label": "a"}
        filename, label, part_id = _format_part_naming(part, idx=1, total_parts=2, q_id="paper_q01")
        self.assertEqual(filename, "part_a.png")
        self.assertEqual(label, "a")
        self.assertEqual(part_id, "paper_q01_a")

        # Single part with empty label
        part_single = {"label": ""}
        filename, label, part_id = _format_part_naming(part_single, idx=1, total_parts=1, q_id="paper_q01")
        self.assertEqual(filename, "part.png")
        self.assertEqual(label, "")
        self.assertEqual(part_id, "paper_q01_p1")

        # Multiple parts with empty label
        part_num = {"label": None}
        filename, label, part_id = _format_part_naming(part_num, idx=2, total_parts=3, q_id="paper_q01")
        self.assertEqual(filename, "part_2.png")
        self.assertEqual(label, "2")
        self.assertEqual(part_id, "paper_q01_p2")

    def test_empty_composite_slices_guards_asset_path(self):
        """Test composite asset pointer is None when composite slices are empty."""
        manifest_data = {
            "paper_id": "test_empty_comp",
            "questions": [
                {
                    "number": 1,
                    "has_preamble": False,
                    "parts": [],
                }
            ],
        }
        manifest_file = self.root / "manifest_empty.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        crop_and_stitch(manifest_file, self.pages_dir, self.crops_dir)

        q1_json = self.crops_dir / "questions" / "q01" / "question.json"
        self.assertTrue(q1_json.is_file())
        q_data = json.loads(q1_json.read_text())
        self.assertIsNone(q_data["composite"]["asset_path"])
        self.assertIsNone(q_data["composite"]["dimensions"])

        updated_manifest = json.loads(manifest_file.read_text())
        self.assertIsNone(updated_manifest["question_index"][0]["composite_asset"])

    def test_manifest_verification_extracted_marks_and_balance_check(self):
        """Test verification block extracted_marks and balance_check update."""
        manifest_data = {
            "paper_id": "test_balance",
            "verification": {
                "expected_marks": 75,
                "status": "extracted",
            },
            "questions": [
                {
                    "number": 1,
                    "has_preamble": False,
                    "parts": [
                        {
                            "label": "a",
                            "marks": 5,
                            "slices": [{"page": 1, "ymin": 100, "xmin": 0, "ymax": 200, "xmax": 1000}],
                        }
                    ],
                }
            ],
        }
        manifest_file = self.root / "manifest_balance.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        crop_and_stitch(manifest_file, self.pages_dir, self.crops_dir)
        updated = json.loads(manifest_file.read_text())
        self.assertEqual(updated["verification"]["extracted_marks"], 5)
        self.assertFalse(updated["verification"]["balance_check"])

        # Now when expected_marks matches
        manifest_data["verification"]["expected_marks"] = 5
        manifest_file.write_text(json.dumps(manifest_data, indent=2))
        crop_and_stitch(manifest_file, self.pages_dir, self.crops_dir)
        updated = json.loads(manifest_file.read_text())
        self.assertEqual(updated["verification"]["extracted_marks"], 5)
        self.assertTrue(updated["verification"]["balance_check"])

    def test_autonomous_crop_repair_from_question_json(self):
        """Test autonomous crop repair loads edited coordinates from question.json."""
        manifest_data = {
            "paper_id": "test_repair",
            "questions": [
                {
                    "number": 1,
                    "has_preamble": False,
                    "parts": [
                        {
                            "label": "a",
                            "marks": 3,
                            "slices": [{"page": 1, "ymin": 300, "xmin": 0, "ymax": 400, "xmax": 1000}],
                        }
                    ],
                }
            ],
        }
        manifest_file = self.root / "manifest_repair.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        # Initial crop run
        crop_and_stitch(manifest_file, self.pages_dir, self.crops_dir)
        q1_json_file = self.crops_dir / "questions" / "q01" / "question.json"
        self.assertTrue(q1_json_file.is_file())

        with Image.open(self.crops_dir / "questions" / "q01" / "part_a.png") as part_img_initial:
            initial_height = part_img_initial.height

        # Simulate Verifier applying upward safety buffer directly in question.json
        q1_data = json.loads(q1_json_file.read_text())
        q1_data["parts"][0]["slices"][0]["ymin"] = 200  # Expand from 300 to 200
        q1_json_file.write_text(json.dumps(q1_data, indent=2))

        # Re-run cropping tool (autonomous repair)
        crop_and_stitch(manifest_file, self.pages_dir, self.crops_dir)

        # Verify new crop used coordinates from question.json
        with Image.open(self.crops_dir / "questions" / "q01" / "part_a.png") as part_img_repaired:
            self.assertGreater(part_img_repaired.height, initial_height)

        # Verify updated manifest in sync with question.json coordinates
        updated_manifest = json.loads(manifest_file.read_text())
        repaired_slice = updated_manifest["questions"][0]["parts"][0]["slices"][0]
        self.assertEqual(repaired_slice["ymin"], 200)


if __name__ == "__main__":
    unittest.main()

