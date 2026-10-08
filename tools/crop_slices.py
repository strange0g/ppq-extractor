"""Full-width slicing and composite stitching tool for Cambridge Question Papers.

Reads a paper's manifest.json and rendered page images, performs full-width
horizontal crops from normalized 0–1000 vertical bounding coordinates [ymin, 0, ymax, 1000],
prepends stem preambles to standalone Question Part Images (e.g. q01_a.png), excises candidate
answer workspace lines, and stitches composite question images (e.g. q01_full.png).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image


def translate_coordinates(
    ymin: float,
    ymax: float,
    page_width: int,
    page_height: int,
    pad: int = 10,
) -> Tuple[int, int, int, int]:
    """Translate normalized 0-1000 coordinates to pixel coordinates.

    Forces full-width crop (x1=0, x2=page_width) and applies vertical padding
    with boundary clamping:
        y1 = max(0, int(ymin * H / 1000) - pad)
        y2 = min(H, int(ymax * H / 1000) + pad)

    Args:
        ymin: Normalized top bound in [0, 1000].
        ymax: Normalized bottom bound in [0, 1000].
        page_width: Width of source page in pixels.
        page_height: Height of source page in pixels.
        pad: Vertical safety padding in pixels (default: 10).

    Returns:
        Tuple of (x1, y1, x2, y2) pixel bounding box.
    """
    if ymin < 0 or ymax > 1000:
        raise ValueError(
            f"Normalized coordinates must be within [0, 1000], got ymin={ymin}, ymax={ymax}"
        )
    if ymin >= ymax:
        raise ValueError(f"ymin ({ymin}) must be strictly less than ymax ({ymax})")

    y1 = max(0, int(ymin * page_height / 1000) - pad)
    y2 = min(page_height, int(ymax * page_height / 1000) + pad)
    x1 = 0
    x2 = page_width

    return x1, y1, x2, y2


def _find_page_file(pages_dir: Path, page_num: int) -> Path:
    """Locate page image file for a given page number in pages_dir."""
    # Common conventions: page_01.png, page_1.png, page_001.png
    candidates = [
        pages_dir / f"page_{page_num:02d}.png",
        pages_dir / f"page_{page_num}.png",
        pages_dir / f"page_{page_num:03d}.png",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    # Fallback to regex search in pages_dir
    pattern = re.compile(rf"^page[-_]?0*{page_num}\.(png|PNG|jpg|jpeg)$")
    for file in pages_dir.iterdir():
        if pattern.match(file.name):
            return file

    fallback_num = pages_dir / f"{page_num}.png"
    if fallback_num.is_file():
        return fallback_num

    raise FileNotFoundError(
        f"Page image for page {page_num} not found in directory: {pages_dir}"
    )


def _load_page_image(
    pages_dir: Path, page_num: int, cache: Dict[int, Image.Image]
) -> Image.Image:
    """Load and cache a page image as RGB."""
    if page_num in cache:
        return cache[page_num]

    page_file = _find_page_file(pages_dir, page_num)
    with Image.open(page_file) as img:
        rgb_img = img.convert("RGB")
    cache[page_num] = rgb_img
    return rgb_img


def _extract_slice_bounds(slice_info: Dict[str, Any]) -> Tuple[int, float, float]:
    """Extract page number and normalized vertical bounds from slice definition."""
    if "page" not in slice_info:
        raise ValueError("Slice definition missing required 'page' key")

    page = int(slice_info["page"])
    if "box_1000" in slice_info:
        box = slice_info["box_1000"]
        ymin, ymax = float(box[0]), float(box[2])
    elif "ymin" in slice_info and "ymax" in slice_info:
        ymin, ymax = float(slice_info["ymin"]), float(slice_info["ymax"])
    else:
        raise ValueError(
            "Slice definition must contain either 'box_1000' or 'ymin'/'ymax' keys"
        )

    return page, ymin, ymax


def _crop_slice(
    pages_dir: Path,
    slice_info: Dict[str, Any],
    pad: int,
    page_cache: Dict[int, Image.Image],
) -> Image.Image:
    """Crop full-width slice from source page."""
    page_num, ymin, ymax = _extract_slice_bounds(slice_info)
    page_img = _load_page_image(pages_dir, page_num, page_cache)
    x1, y1, x2, y2 = translate_coordinates(
        ymin=ymin,
        ymax=ymax,
        page_width=page_img.width,
        page_height=page_img.height,
        pad=pad,
    )
    return page_img.crop((x1, y1, x2, y2))


def concatenate_vertical(
    slices: List[Image.Image],
    spacing: int = 20,
    bg_color: Tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """Concatenate a sequence of images vertically with spacing separator.

    Args:
        slices: List of Image objects with equal width.
        spacing: Height in pixels of divider between adjacent images.
        bg_color: Background color for divider (default white).

    Returns:
        Stitched Image object.
    """
    if not slices:
        raise ValueError("Cannot concatenate an empty list of slices")

    if len(slices) == 1:
        return slices[0].copy()

    width = slices[0].width
    total_height = sum(s.height for s in slices) + (len(slices) - 1) * spacing
    canvas = Image.new("RGB", (width, total_height), bg_color)

    y_offset = 0
    for i, s in enumerate(slices):
        canvas.paste(s, (0, y_offset))
        y_offset += s.height + spacing

    return canvas


def _get_relative_asset_path(
    out_file: Path, manifest_path: Path, out_dir: Path
) -> str:
    """Determine normalized relative asset path for manifest."""
    manifest_dir = manifest_path.resolve().parent
    try:
        return str(out_file.resolve().relative_to(manifest_dir))
    except ValueError:
        if out_dir.name == "crops":
            return f"crops/{out_file.name}"
        return out_file.name


def crop_and_stitch(
    manifest_path: str | Path,
    pages_dir: str | Path,
    out_dir: str | Path,
    pad: int = 10,
    spacing: int = 20,
) -> Dict[str, Any]:
    """Process question slices from manifest.json and write cropped assets.

    Args:
        manifest_path: Path to paper manifest.json.
        pages_dir: Directory containing rendered page PNGs.
        out_dir: Directory where cropped assets will be written.
        pad: Vertical padding in pixels added to each slice (default: 10).
        spacing: White separator divider between stitched parts (default: 20).

    Returns:
        Summary dict containing crops metadata and updated manifest.
    """
    manifest_file = Path(manifest_path).resolve()
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_file}")

    pages_path = Path(pages_dir).resolve()
    if not pages_path.is_dir():
        raise FileNotFoundError(f"Pages directory not found: {pages_path}")

    crops_path = Path(out_dir).resolve()
    crops_path.mkdir(parents=True, exist_ok=True)

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    questions = manifest_data.get("questions", [])

    page_cache: Dict[int, Image.Image] = {}
    generated_crops: List[str] = []

    for q in questions:
        q_num = int(q.get("number", 1))
        has_preamble = q.get("has_preamble", None)

        preamble_slice_list: List[Dict[str, Any]] = []
        if has_preamble is not False:
            if "preamble_slices" in q and q["preamble_slices"]:
                raw_preambles = q["preamble_slices"]
                if isinstance(raw_preambles, list):
                    preamble_slice_list.extend(raw_preambles)
                elif isinstance(raw_preambles, dict):
                    preamble_slice_list.append(raw_preambles)
            elif "preamble_slice" in q and q["preamble_slice"]:
                raw_preambles = q["preamble_slice"]
                if isinstance(raw_preambles, list):
                    preamble_slice_list.extend(raw_preambles)
                elif isinstance(raw_preambles, dict):
                    preamble_slice_list.append(raw_preambles)

        preamble_imgs: List[Image.Image] = []
        for p_slice in preamble_slice_list:
            preamble_imgs.append(_crop_slice(pages_path, p_slice, pad, page_cache))

        preamble_img: Image.Image | None = None
        if preamble_imgs:
            preamble_img = concatenate_vertical(preamble_imgs, spacing=spacing)

        composite_slices: List[Image.Image] = []
        if preamble_imgs:
            composite_slices.extend(preamble_imgs)

        parts = q.get("parts", [])
        # If parts list is empty, support root question slices or whole question box
        if not parts:
            if "slices" in q:
                parts = [{"label": "", "slices": q["slices"]}]
            elif "box_1000" in q or ("ymin" in q and "ymax" in q):
                parts = [{"label": "", "slices": [q]}]

        for idx, part in enumerate(parts, start=1):
            slices_info = part.get("slices", [])
            if not slices_info and "slice" in part:
                slices_info = [part["slice"]]

            if not slices_info:
                continue

            part_slice_imgs = [
                _crop_slice(pages_path, s, pad, page_cache) for s in slices_info
            ]
            part_main_img = concatenate_vertical(part_slice_imgs, spacing=spacing)

            composite_slices.extend(part_slice_imgs)

            # Standalone Question Part Image: prepend preamble if present
            if preamble_img is not None:
                standalone_img = concatenate_vertical(
                    [preamble_img, part_main_img], spacing=spacing
                )
            else:
                standalone_img = part_main_img

            # Determine output filename for Question Part Image
            if part.get("asset_path"):
                filename = Path(part["asset_path"]).name
            else:
                raw_label = str(part.get("label") or part.get("part_label") or "").strip().strip("()")
                clean_label = re.sub(r"[^a-zA-Z0-9_-]", "", raw_label)
                if clean_label:
                    filename = f"q{q_num:02d}_{clean_label}.png"
                elif len(parts) == 1:
                    filename = f"q{q_num:02d}.png"
                else:
                    filename = f"q{q_num:02d}_part{idx}.png"

            out_file = crops_path / filename
            standalone_img.save(out_file, format="PNG")
            generated_crops.append(str(out_file))

            # Update part metadata in manifest
            rel_asset_path = _get_relative_asset_path(out_file, manifest_file, crops_path)
            part["asset_path"] = rel_asset_path
            part["width"] = standalone_img.width
            part["height"] = standalone_img.height

        # Generate composite question image
        if composite_slices:
            composite_img = concatenate_vertical(composite_slices, spacing=spacing)

            if q.get("composite_asset_path"):
                comp_filename = Path(q["composite_asset_path"]).name
            else:
                comp_filename = f"q{q_num:02d}_full.png"

            comp_file = crops_path / comp_filename
            composite_img.save(comp_file, format="PNG")
            generated_crops.append(str(comp_file))

            rel_comp_path = _get_relative_asset_path(comp_file, manifest_file, crops_path)
            q["composite_asset_path"] = rel_comp_path
            q["composite_width"] = composite_img.width
            q["composite_height"] = composite_img.height

    # Save updated manifest back to disk
    manifest_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    return {
        "status": "success",
        "manifest_path": str(manifest_file),
        "crops_count": len(generated_crops),
        "crops": generated_crops,
        "questions_processed": len(questions),
        "manifest": manifest_data,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Full-width slicing and composite stitching tool for Cambridge Question Papers."
    )
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="Path to manifest.json",
    )
    parser.add_argument(
        "--pages-dir",
        required=True,
        type=Path,
        help="Path to rendered page images directory",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        help="Output directory for generated crops",
    )
    parser.add_argument(
        "--pad",
        type=int,
        default=10,
        help="Vertical padding in pixels (default: 10)",
    )
    parser.add_argument(
        "--spacing",
        type=int,
        default=20,
        help="Vertical divider spacing in pixels (default: 20)",
    )

    args = parser.parse_args(argv)

    try:
        summary = crop_and_stitch(
            manifest_path=args.manifest,
            pages_dir=args.pages_dir,
            out_dir=args.out_dir,
            pad=args.pad,
            spacing=args.spacing,
        )
        print(json.dumps(summary, indent=2))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
