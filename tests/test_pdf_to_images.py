import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from PIL import Image

try:
    from tools.pdf_to_images import render_pdf_to_images
except ImportError:
    render_pdf_to_images = None


def find_sample_pdf() -> Path:
    candidates = [
        Path("/home/raied/Programming/ppq-extractor/9709/2024/2024 Nov/9709_w24_qp_12.pdf"),
        Path(__file__).resolve().parents[2] / "9709/2024/2024 Nov/9709_w24_qp_12.pdf",
        Path(__file__).resolve().parents[3] / "9709/2024/2024 Nov/9709_w24_qp_12.pdf",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError("Sample Cambridge PDF 9709_w24_qp_12.pdf not found in candidate paths.")


MINIMAL_1PAGE_PDF = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >> endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer << /Size 4 /Root 1 0 R >>
startxref
190
%%EOF"""


class TestPdfToImages(unittest.TestCase):
    def setUp(self):
        if render_pdf_to_images is None:
            self.fail("tools.pdf_to_images module or render_pdf_to_images function not implemented")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.out_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_render_pdf_to_images_end_to_end_sample_paper(self):
        pdf_path = find_sample_pdf()
        result = render_pdf_to_images(pdf_path, self.out_dir, dpi=200)

        self.assertEqual(result["page_count"], 20)
        self.assertEqual(result["dpi"], 200)
        self.assertEqual(result["width"], 1654)
        self.assertEqual(result["height"], 2339)

        # Verify all 20 pages exist and are named page_01.png .. page_20.png
        for i in range(1, 21):
            expected_file = self.out_dir / f"page_{i:02d}.png"
            self.assertTrue(expected_file.exists(), f"Missing expected page file: {expected_file.name}")
            with Image.open(expected_file) as im:
                self.assertEqual(im.size, (1654, 2339))

    def test_cli_invocation(self):
        pdf_path = find_sample_pdf()
        cmd = [
            sys.executable,
            "-m",
            "tools.pdf_to_images",
            "--pdf",
            str(pdf_path),
            "--out-dir",
            str(self.out_dir),
            "--dpi",
            "200",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"CLI failed with stderr: {proc.stderr}")

        summary = json.loads(proc.stdout)
        self.assertEqual(summary["page_count"], 20)
        self.assertEqual(summary["dpi"], 200)
        self.assertEqual(summary["width"], 1654)
        self.assertEqual(summary["height"], 2339)

        # Check files on disk
        self.assertTrue((self.out_dir / "page_01.png").exists())
        self.assertTrue((self.out_dir / "page_20.png").exists())

    def test_skip_re_rendering_when_pages_exist(self):
        pdf_path = find_sample_pdf()
        # Initial render
        render_pdf_to_images(pdf_path, self.out_dir, dpi=200)
        page1 = self.out_dir / "page_01.png"
        self.assertTrue(page1.exists())
        initial_mtime = page1.stat().st_mtime_ns

        # Small sleep to ensure timestamp differences if modified
        time.sleep(0.05)

        # Second render with force=False should skip
        render_pdf_to_images(pdf_path, self.out_dir, dpi=200, force=False)
        self.assertEqual(page1.stat().st_mtime_ns, initial_mtime)

        # Third render with force=True should re-render
        render_pdf_to_images(pdf_path, self.out_dir, dpi=200, force=True)
        self.assertNotEqual(page1.stat().st_mtime_ns, initial_mtime)

    def test_zero_padded_single_page_pdf(self):
        single_pdf = self.out_dir / "single.pdf"
        single_pdf.write_bytes(MINIMAL_1PAGE_PDF)
        render_dir = self.out_dir / "pages"

        result = render_pdf_to_images(single_pdf, render_dir, dpi=200)
        self.assertEqual(result["page_count"], 1)

        # Ensure page_01.png exists (zero-padded to 2 digits)
        self.assertTrue((render_dir / "page_01.png").exists())
        self.assertFalse((render_dir / "page_1.png").exists())

    def test_error_nonexistent_pdf(self):
        with self.assertRaises(FileNotFoundError):
            render_pdf_to_images(self.out_dir / "nonexistent.pdf", self.out_dir)

        # CLI should exit non-zero
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.pdf_to_images",
                "--pdf",
                str(self.out_dir / "nonexistent.pdf"),
                "--out-dir",
                str(self.out_dir),
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
