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
    from tools.crop_slices import crop_and_stitch, translate_coordinates
except ImportError:
    crop_and_stitch = None
    translate_coordinates = None


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
        """Test standalone part image prepends preamble slice with 20px white divider."""
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
                            "asset_path": "crops/q01_a.png",
                        }
                    ],
                    "composite_asset_path": "crops/q01_full.png",
                }
            ],
        }
        manifest_file = self.root / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        crop_and_stitch(manifest_file, self.pages_dir, self.crops_dir, pad=10, spacing=20)

        part_img_path = self.crops_dir / "q01_a.png"
        self.assertTrue(part_img_path.is_file(), f"Expected crop {part_img_path} not found")

        with Image.open(part_img_path) as im:
            # Expected dimensions: W=1000, H = 220 (preamble) + 20 (spacing) + 220 (part a) = 460
            self.assertEqual(im.size, (1000, 460))

            # Verify white divider of 20px height between y=220 and y=240
            for dy in range(220, 240):
                pixel = im.getpixel((500, dy))
                self.assertEqual(pixel, (255, 255, 255), f"Divider pixel at y={dy} is not white")

            # Verify preamble content is in top portion
            top_pixel = im.getpixel((500, 100))
            self.assertEqual(top_pixel, (255, 200, 200))  # Red band from page 1

            # Verify part a content is in bottom portion
            bottom_pixel = im.getpixel((500, 240 + 100))
            self.assertEqual(bottom_pixel, (200, 255, 200))  # Green band from page 1

    def test_composite_question_generation_omits_workspace(self):
        """Test qXX_full.png stitches preamble and all parts vertically with 20px divider."""
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
                            "asset_path": "crops/q01_a.png",
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
                            "asset_path": "crops/q01_b.png",
                        },
                    ],
                    "composite_asset_path": "crops/q01_full.png",
                }
            ],
        }
        manifest_file = self.root / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        crop_and_stitch(manifest_file, self.pages_dir, self.crops_dir, pad=10, spacing=20)

        composite_path = self.crops_dir / "q01_full.png"
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
        """Test single-part question without preamble (direct crop)."""
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
                            "asset_path": "crops/q02_a.png",
                        }
                    ],
                    "composite_asset_path": "crops/q02_full.png",
                }
            ],
        }
        manifest_file = self.root / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        crop_and_stitch(manifest_file, self.pages_dir, self.crops_dir, pad=10, spacing=20)

        part_img = self.crops_dir / "q02_a.png"
        comp_img = self.crops_dir / "q02_full.png"
        self.assertTrue(part_img.is_file())
        self.assertTrue(comp_img.is_file())

        with Image.open(part_img) as im:
            # Standalone crop has no preamble prepended -> H=220
            self.assertEqual(im.size, (1000, 220))
            # Blue band content
            self.assertEqual(im.getpixel((500, 100)), (200, 200, 255))

        with Image.open(comp_img) as im:
            # Composite for single part question is also H=220
            self.assertEqual(im.size, (1000, 220))

    def test_manifest_updating_with_asset_paths_and_dimensions(self):
        """Test manifest.json is updated with asset file paths and pixel dimensions."""
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

        # Verify part asset_path and dimensions
        self.assertEqual(part_a["asset_path"], "crops/q01_a.png")
        self.assertEqual(part_a["width"], 1000)
        self.assertEqual(part_a["height"], 460)

        # Verify composite asset path and dimensions
        self.assertEqual(q1["composite_asset_path"], "crops/q01_full.png")
        self.assertEqual(q1["composite_width"], 1000)
        self.assertEqual(q1["composite_height"], 460)

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
        self.assertTrue((self.crops_dir / "q01_a.png").is_file())
        self.assertTrue((self.crops_dir / "q01_full.png").is_file())

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
        # Q1 has part a, part b, and composite (3). Q2 has part a and composite (2). Total = 5.
        self.assertEqual(result["crops_count"], 5)

        # Verify Q1 assets
        self.assertTrue((self.crops_dir / "q01_a.png").is_file())
        self.assertTrue((self.crops_dir / "q01_b.png").is_file())
        self.assertTrue((self.crops_dir / "q01_full.png").is_file())

        # Verify Q2 assets
        self.assertTrue((self.crops_dir / "q02_a.png").is_file())
        self.assertTrue((self.crops_dir / "q02_full.png").is_file())

        # Check updated manifest
        updated = json.loads(manifest_file.read_text())
        self.assertEqual(updated["questions"][0]["parts"][0]["asset_path"], "crops/q01_a.png")
        self.assertEqual(updated["questions"][0]["parts"][1]["asset_path"], "crops/q01_b.png")
        self.assertEqual(updated["questions"][0]["composite_asset_path"], "crops/q01_full.png")
        self.assertEqual(updated["questions"][1]["parts"][0]["asset_path"], "crops/q02_a.png")
        self.assertEqual(updated["questions"][1]["composite_asset_path"], "crops/q02_full.png")

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

        # Q1 has standalone part a and composite
        self.assertTrue((self.crops_dir / "q01_a.png").is_file())
        self.assertTrue((self.crops_dir / "q01_full.png").is_file())

        # Q2 has standalone whole question q02.png and composite q02_full.png
        self.assertTrue((self.crops_dir / "q02.png").is_file())
        self.assertTrue((self.crops_dir / "q02_full.png").is_file())


if __name__ == "__main__":
    unittest.main()

