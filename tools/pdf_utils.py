"""Shared PDF utility functions for Cambridge examination papers."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


def get_pdf_page_count(pdf_path: str | Path) -> int:
    """Retrieve total page count of a PDF using pdfinfo with binary fallback.

    Args:
        pdf_path: Path to the target PDF file.

    Returns:
        Total integer page count (>= 1).

    Raises:
        FileNotFoundError: If the source PDF file does not exist.
        ValueError: If page count cannot be determined by either method.
    """
    path = Path(pdf_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Source PDF not found: {path}")

    # Method 1: Try pdfinfo CLI utility
    pdfinfo_bin = shutil.which("pdfinfo") or "/usr/bin/pdfinfo"
    try:
        proc = subprocess.run(
            [pdfinfo_bin, str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in proc.stdout.splitlines():
            if line.startswith("Pages:"):
                count = int(line.split(":", 1)[1].strip())
                if count > 0:
                    return count
    except Exception:
        pass

    # Method 2: Fallback to binary inspection of /Count in PDF structure
    try:
        with open(path, "rb") as f:
            content = f.read()
        matches = re.findall(rb"/Type\s*/Pages.*?/Count\s+(\d+)", content, re.DOTALL)
        if matches:
            count = int(matches[-1])
            if count > 0:
                return count
        matches = re.findall(rb"/Count\s+(\d+)", content)
        if matches:
            count = max(int(m) for m in matches)
            if count > 0:
                return count
    except Exception:
        pass

    raise ValueError(f"Could not determine page count from pdfinfo or binary inspection for {path}")
