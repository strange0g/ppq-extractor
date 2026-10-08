"""PDF to high-resolution page images converter tool.

Uses Poppler's pdftoppm utility via subprocess to render Cambridge examination
PDFs into standardized 200 DPI PNG page images (page_01.png, page_02.png, etc.).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from PIL import Image


def get_pdf_page_count(pdf_path: Path) -> int:
    """Retrieve total page count of a PDF using pdfinfo."""
    pdfinfo_bin = shutil.which("pdfinfo") or "/usr/bin/pdfinfo"
    proc = subprocess.run(
        [pdfinfo_bin, str(pdf_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise ValueError(f"Could not determine page count from pdfinfo for {pdf_path}")


def render_pdf_to_images(
    pdf_path: str | Path,
    out_dir: str | Path,
    dpi: int = 200,
    force: bool = False,
) -> Dict[str, Any]:
    """Render a PDF file into high-resolution zero-padded PNG page images.

    Args:
        pdf_path: Path to the source PDF file.
        out_dir: Output directory where page images will be saved.
        dpi: Target resolution in dots per inch (default: 200).
        force: If True, re-renders even if valid page images exist.

    Returns:
        dict containing 'page_count', 'dpi', 'width', and 'height'.
    """
    pdf_file = Path(pdf_path).resolve()
    if not pdf_file.is_file():
        raise FileNotFoundError(f"Source PDF not found: {pdf_file}")

    output_path = Path(out_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    page_count = get_pdf_page_count(pdf_file)
    digits = max(2, len(str(page_count)))

    expected_files = [
        output_path / f"page_{i:0{digits}d}.png" for i in range(1, page_count + 1)
    ]

    # Check if all valid page images already exist and re-render is not forced
    if not force and all(f.is_file() and f.stat().st_size > 0 for f in expected_files):
        try:
            with Image.open(expected_files[0]) as first_page:
                width, height = first_page.size
            return {
                "page_count": page_count,
                "dpi": dpi,
                "width": width,
                "height": height,
            }
        except Exception:
            # Fall through to re-render if cached images cannot be read
            pass

    # Clear any existing page image files in out_dir to avoid stale pages
    for existing in output_path.glob("page*.png"):
        try:
            existing.unlink()
        except OSError:
            pass

    pdftoppm_bin = shutil.which("pdftoppm") or "/usr/bin/pdftoppm"
    prefix = output_path / "page"

    cmd = [
        pdftoppm_bin,
        "-png",
        "-r",
        str(dpi),
        "-sep",
        "_",
        str(pdf_file),
        str(prefix),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"pdftoppm failed with exit code {proc.returncode}: {proc.stderr.strip()}"
        )

    # Normalize zero-padded filenames (e.g., page_1.png -> page_01.png if needed)
    page_pattern = re.compile(r"^page[-_]?(\d+)\.png$")
    for file in sorted(output_path.glob("page*.png")):
        match = page_pattern.match(file.name)
        if match:
            page_num = int(match.group(1))
            normalized_name = f"page_{page_num:0{digits}d}.png"
            target_path = output_path / normalized_name
            if file != target_path:
                file.rename(target_path)

    # Validate output and extract dimensions
    first_page_path = output_path / f"page_{1:0{digits}d}.png"
    if not first_page_path.is_file():
        raise RuntimeError(f"Expected rendered page missing: {first_page_path}")

    with Image.open(first_page_path) as first_page:
        width, height = first_page.size

    return {
        "page_count": page_count,
        "dpi": dpi,
        "width": width,
        "height": height,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Convert Cambridge Question Paper PDF to high-resolution PNG page images."
    )
    parser.add_argument(
        "--pdf",
        required=True,
        type=Path,
        help="Path to source PDF file",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        help="Directory to save rendered page images",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="Resolution in DPI (default: 200)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-rendering even if valid page images already exist",
    )

    args = parser.parse_args(argv)

    try:
        summary = render_pdf_to_images(
            pdf_path=args.pdf,
            out_dir=args.out_dir,
            dpi=args.dpi,
            force=args.force,
        )
        print(json.dumps(summary, indent=2))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
