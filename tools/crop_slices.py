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

from PIL import Image, ImageDraw


def detect_page_margin_trim(page_img: Image.Image) -> Tuple[int, int]:
    """Detect and return horizontal content bounds (x1, x2) in pixels, trimming outer margin text.

    Cambridge write-in papers starting around 2024 include vertical margin warning text
    ('DO NOT WRITE IN THIS MARGIN') on the outer margins (right margin on even pages, left margin on odd pages).
    This function detects dark markings in the outer 4.5% horizontal strip and trims that strip automatically
    while preserving the full question content, diagrams, and mark brackets.
    """
    w, h = page_img.size
    left_strip_w = int(w * 0.045)
    right_strip_w = int(w * 0.045)
    sample_box_left = (0, int(h * 0.15), left_strip_w, int(h * 0.85))
    sample_box_right = (w - right_strip_w, int(h * 0.15), w, int(h * 0.85))

    gray = page_img.convert("L")
    left_crop = gray.crop(sample_box_left)
    right_crop = gray.crop(sample_box_right)

    has_left = (
        left_crop.getextrema()[0] < 180
        and sum(left_crop.histogram()[:180]) / (left_crop.width * left_crop.height)
        > 0.005
    )
    has_right = (
        right_crop.getextrema()[0] < 180
        and sum(right_crop.histogram()[:180]) / (right_crop.width * right_crop.height)
        > 0.005
    )

    x1 = left_strip_w if has_left else 0
    x2 = (w - right_strip_w) if has_right else w
    return x1, x2


def mask_margin_strip(
    crop_img: Image.Image,
    page_img: Image.Image,
    bg_color: Tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """Mask out vertical outer margin warnings with background color while preserving full image width."""
    mx1, mx2 = detect_page_margin_trim(page_img)
    w, h = crop_img.size
    has_left = mx1 > 0
    has_right = mx2 < page_img.width

    if not has_left and not has_right:
        return crop_img

    masked = crop_img.copy()
    draw = ImageDraw.Draw(masked)
    if has_left and mx1 <= w:
        draw.rectangle([(0, 0), (mx1, h)], fill=bg_color)
    if has_right and mx2 < page_img.width:
        right_start = max(0, w - (page_img.width - mx2))
        draw.rectangle([(right_start, 0), (w, h)], fill=bg_color)
    return masked


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
    trim_margins: bool = True,
) -> Image.Image:
    """Crop full-width slice from source page with automatic margin suppression."""
    page_num, ymin, ymax = _extract_slice_bounds(slice_info)
    page_img = _load_page_image(pages_dir, page_num, page_cache)
    x1, y1, x2, y2 = translate_coordinates(
        ymin=ymin,
        ymax=ymax,
        page_width=page_img.width,
        page_height=page_img.height,
        pad=pad,
    )
    cropped = page_img.crop((x1, y1, x2, y2))
    if trim_margins:
        cropped = mask_margin_strip(cropped, page_img)
    return cropped


def concatenate_vertical(
    slices: List[Image.Image],
    spacing: int = 20,
    bg_color: Tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """Concatenate a sequence of images vertically with spacing separator.

    Args:
        slices: List of Image objects.
        spacing: Height in pixels of divider between adjacent images.
        bg_color: Background color for divider (default white).

    Returns:
        Stitched Image object.
    """
    if not slices:
        raise ValueError("Cannot concatenate an empty list of slices")

    if len(slices) == 1:
        return slices[0].copy()

    max_width = max(s.width for s in slices)
    total_height = sum(s.height for s in slices) + (len(slices) - 1) * spacing
    canvas = Image.new("RGB", (max_width, total_height), bg_color)

    y_offset = 0
    for s in slices:
        canvas.paste(s, (0, y_offset))
        y_offset += s.height + spacing

    return canvas


def _get_relative_asset_path(out_file: Path, manifest_path: Path, out_dir: Path) -> str:
    """Determine normalized relative asset path for manifest."""
    manifest_dir = manifest_path.resolve().parent
    try:
        return str(out_file.resolve().relative_to(manifest_dir))
    except ValueError:
        try:
            return str(out_file.resolve().relative_to(out_dir.resolve()))
        except ValueError:
            return out_file.name


def _format_part_naming(
    part: Dict[str, Any],
    idx: int,
    total_parts: int,
    q_id: str,
) -> Tuple[str, str, str]:
    """Format filename, label, and identifier for a question part.

    Returns:
        Tuple of (filename, label, part_id).
    """
    raw_label = (
        str(part.get("label") or part.get("part_label") or "").strip().strip("()")
    )
    clean_label = re.sub(r"[^a-zA-Z0-9_-]", "", raw_label)
    if clean_label:
        filename = f"part_{clean_label}.png"
        label_val = clean_label
        part_id = f"{q_id}_{clean_label}"
    elif total_parts == 1:
        filename = "part.png"
        label_val = ""
        part_id = f"{q_id}_p{idx}"
    else:
        filename = f"part_{idx}.png"
        label_val = str(idx)
        part_id = f"{q_id}_p{idx}"

    return filename, label_val, part_id


def _extract_preamble_slices_from_manifest(q: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract preamble slice definitions from question dict in manifest."""
    has_preamble = q.get("has_preamble", None)
    slice_list: List[Dict[str, Any]] = []
    if has_preamble is not False:
        if "preamble_slices" in q and q["preamble_slices"]:
            raw_preambles = q["preamble_slices"]
            if isinstance(raw_preambles, list):
                slice_list.extend(raw_preambles)
            elif isinstance(raw_preambles, dict):
                slice_list.append(raw_preambles)
        elif "preamble_slice" in q and q["preamble_slice"]:
            raw_preambles = q["preamble_slice"]
            if isinstance(raw_preambles, list):
                slice_list.extend(raw_preambles)
            elif isinstance(raw_preambles, dict):
                slice_list.append(raw_preambles)
    return slice_list


def _should_load_from_question_json(
    q_json_file: Path,
    manifest_file: Path,
    manifest_q: Dict[str, Any],
    existing_q_data: Dict[str, Any],
) -> bool:
    """Determine whether to load coordinates from question.json instead of manifest."""
    has_pkg_slices = bool(
        (
            existing_q_data.get("preamble")
            and existing_q_data.get("preamble", {}).get("slices")
        )
        or (
            existing_q_data.get("parts")
            and any(p.get("slices") for p in existing_q_data.get("parts", []))
        )
    )
    if not has_pkg_slices:
        return False

    has_manifest_slices = bool(
        manifest_q.get("preamble_slices")
        or manifest_q.get("preamble_slice")
        or manifest_q.get("slices")
        or (
            manifest_q.get("parts")
            and any(p.get("slices") for p in manifest_q.get("parts", []))
        )
    )
    if not has_manifest_slices:
        return True

    try:
        q_mtime = q_json_file.stat().st_mtime
        m_mtime = manifest_file.stat().st_mtime
        if q_mtime > m_mtime:
            return True
    except OSError:
        pass

    q_slices = (existing_q_data.get("preamble", {}).get("slices") or []) + [
        s for p in existing_q_data.get("parts", []) for s in p.get("slices", [])
    ]
    m_slices = (
        (
            manifest_q.get("preamble_slices")
            or (
                [manifest_q["preamble_slice"]]
                if manifest_q.get("preamble_slice")
                else []
            )
        )
        + (manifest_q.get("slices") or [])
        + [s for p in manifest_q.get("parts", []) for s in p.get("slices", [])]
    )
    if q_slices != m_slices:
        try:
            if q_json_file.stat().st_mtime >= manifest_file.stat().st_mtime - 0.05:
                return True
        except OSError:
            return True

    return False


def _resolve_relative_path(target_path: Path, paper_dir: Path, base_dir: Path) -> str:
    """Resolve target path relative to paper directory or base directory cleanly without string slicing."""
    target = target_path.resolve()
    for root in (paper_dir.resolve(), base_dir.resolve()):
        try:
            rel = target.relative_to(root)
            parts = rel.parts
            if "questions" in parts:
                q_idx = parts.index("questions")
                return str(Path(*parts[q_idx:]))
            return str(rel)
        except ValueError:
            continue
    return str(target_path.name)


def crop_and_stitch(
    manifest_path: str | Path,
    pages_dir: str | Path,
    out_dir: str | Path,
    pad: int = 10,
    spacing: int = 20,
    trim_margins: bool = True,
) -> Dict[str, Any]:
    """Process question slices from manifest.json and write cropped Question Packages.

    Outputs question packages under out_dir/questions/q{NN}/:
      - preamble.png (if question has preamble slices)
      - part_{label}.png (isolated Question Part Images without preamble)
      - full.png (composite question image stitching preamble + all parts with 20px padding)
      - question.json (atomic item-level metadata descriptor)

    Updates manifest.json with question_index and package metadata.

    Args:
        manifest_path: Path to paper manifest.json.
        pages_dir: Directory containing rendered page PNGs.
        out_dir: Directory where Question Packages or paper assets will be written.
        pad: Vertical padding in pixels added to each slice (default: 10).
        spacing: White separator divider between stitched parts (default: 20).
        trim_margins: Automatically trim outer margin warning text (default: True).

    Returns:
        Summary dict containing crops metadata and updated manifest.
    """
    manifest_file = Path(manifest_path).resolve()
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_file}")

    pages_path = Path(pages_dir).resolve()
    if not pages_path.is_dir():
        raise FileNotFoundError(f"Pages directory not found: {pages_path}")

    base_out_path = Path(out_dir).resolve()
    base_out_path.mkdir(parents=True, exist_ok=True)

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    paper_dir = manifest_file.parent
    paper_id = str(manifest_data.get("id") or manifest_data.get("paper_id") or "")
    questions = manifest_data.get("questions", [])

    page_cache: Dict[int, Image.Image] = {}
    generated_crops: List[str] = []
    question_index: List[Dict[str, Any]] = []

    for q in questions:
        q_num = int(q.get("number", 1))
        q_dir_name = f"q{q_num:02d}"
        q_pkg_dir = base_out_path / "questions" / q_dir_name
        q_pkg_dir.mkdir(parents=True, exist_ok=True)
        q_json_file = q_pkg_dir / "question.json"

        # Check if individual question.json already exists and has slices edited (e.g. by Verifier)
        existing_q_data: Dict[str, Any] | None = None
        if q_json_file.is_file():
            try:
                existing_q_data = json.loads(q_json_file.read_text(encoding="utf-8"))
            except Exception:
                existing_q_data = None

        load_from_q_json = False
        if existing_q_data and isinstance(existing_q_data, dict):
            load_from_q_json = _should_load_from_question_json(
                q_json_file=q_json_file,
                manifest_file=manifest_file,
                manifest_q=q,
                existing_q_data=existing_q_data,
            )

        preamble_slice_list: List[Dict[str, Any]] = []
        if load_from_q_json and isinstance(existing_q_data.get("preamble"), dict):
            ext_preamble = existing_q_data["preamble"]
            if ext_preamble.get("slices"):
                preamble_slice_list = list(ext_preamble["slices"])
            elif ext_preamble.get("present") is False:
                preamble_slice_list = []
            else:
                preamble_slice_list = _extract_preamble_slices_from_manifest(q)
        else:
            preamble_slice_list = _extract_preamble_slices_from_manifest(q)

        # Sync repaired preamble slices back to manifest if loaded from question.json
        if load_from_q_json:
            if preamble_slice_list:
                q["preamble_slices"] = preamble_slice_list
                q["has_preamble"] = True
            elif (
                existing_q_data
                and existing_q_data.get("preamble", {}).get("present") is False
            ):
                q["has_preamble"] = False
                q.pop("preamble_slices", None)
                q.pop("preamble_slice", None)

        preamble_imgs: List[Image.Image] = []
        for p_slice in preamble_slice_list:
            preamble_imgs.append(
                _crop_slice(
                    pages_path, p_slice, pad, page_cache, trim_margins=trim_margins
                )
            )

        preamble_img: Image.Image | None = None
        preamble_meta: Dict[str, Any] = {
            "present": False,
            "asset_path": None,
            "dimensions": None,
            "slices": preamble_slice_list,
        }

        if preamble_imgs:
            preamble_img = concatenate_vertical(preamble_imgs, spacing=spacing)
            preamble_file = q_pkg_dir / "preamble.png"
            preamble_img.save(preamble_file, format="PNG")
            generated_crops.append(str(preamble_file))

            preamble_meta = {
                "present": True,
                "asset_path": "preamble.png",
                "dimensions": {
                    "width": preamble_img.width,
                    "height": preamble_img.height,
                },
                "slices": preamble_slice_list,
            }

        composite_slices: List[Image.Image] = []
        if preamble_imgs:
            composite_slices.extend(preamble_imgs)

        parts: List[Dict[str, Any]] = []
        if (
            load_from_q_json
            and isinstance(existing_q_data.get("parts"), list)
            and existing_q_data["parts"]
        ):
            parts = [dict(p) for p in existing_q_data["parts"]]
            q["parts"] = parts
        else:
            parts = q.get("parts", [])
            # If parts list is empty, support root question slices or whole question box
            if not parts:
                if "slices" in q:
                    parts = [{"label": "", "slices": q["slices"]}]
                elif "box_1000" in q or ("ymin" in q and "ymax" in q):
                    parts = [{"label": "", "slices": [q]}]

        q_id = f"{paper_id}_q{q_num:02d}" if paper_id else f"q{q_num:02d}"
        question_parts_meta: List[Dict[str, Any]] = []

        for idx, part in enumerate(parts, start=1):
            slices_info = part.get("slices", [])
            if not slices_info and "slice" in part:
                slices_info = [part["slice"]]

            if not slices_info:
                continue

            part_slice_imgs = [
                _crop_slice(pages_path, s, pad, page_cache, trim_margins=trim_margins)
                for s in slices_info
            ]
            part_main_img = concatenate_vertical(part_slice_imgs, spacing=spacing)

            composite_slices.extend(part_slice_imgs)

            # Determine whether this is a standalone question without subparts
            is_standalone_question = (
                len(parts) == 1
                and not preamble_meta["present"]
                and not (part.get("label") or part.get("part_label"))
            )

            filename, label_val, part_identifier = _format_part_naming(
                part=part,
                idx=idx,
                total_parts=len(parts),
                q_id=q_id,
            )

            if is_standalone_question:
                # Standalone Question: The composite full.png serves as the primary asset; avoid saving duplicate part.png
                filename = "full.png"
                part_file = q_pkg_dir / "full.png"
                # Clean up any stale redundant part.png or preamble.png on disk
                for stale_name in (
                    "part.png",
                    "part_1.png",
                    "part_whole.png",
                    "preamble.png",
                ):
                    stale_file = q_pkg_dir / stale_name
                    if stale_file.is_file():
                        stale_file.unlink()
            else:
                # Multipart Question: Save isolated Question Part Image
                part_file = q_pkg_dir / filename
                part_main_img.save(part_file, format="PNG")
                generated_crops.append(str(part_file))

            # Update part metadata in manifest
            rel_part_manifest_path = _get_relative_asset_path(
                part_file, manifest_file, base_out_path
            )
            part["asset_path"] = rel_part_manifest_path
            part["width"] = part_main_img.width
            part["height"] = part_main_img.height

            # Part metadata for question.json
            part_marks = part.get("marks")
            part_context_deps = ["preamble"] if preamble_meta["present"] else []
            # For standalone questions without subdivided parts, inherit question-level topics directly
            part_topics = (
                part.get("topics") or (q.get("topics") if len(parts) == 1 else []) or []
            )

            question_parts_meta.append(
                {
                    "part_id": part_identifier,
                    "label": label_val,
                    "marks": part_marks,
                    "isolated_asset_path": filename,
                    "dimensions": {
                        "width": part_main_img.width,
                        "height": part_main_img.height,
                    },
                    "slices": slices_info,
                    "topics": part_topics,
                    "context_dependencies": part_context_deps,
                }
            )

        # Generate composite question image (preamble + all Question Parts)
        composite_meta: Dict[str, Any] = {
            "asset_path": None,
            "dimensions": None,
        }
        rel_composite_asset: str | None = None
        if composite_slices:
            composite_img = concatenate_vertical(composite_slices, spacing=spacing)
            comp_file = q_pkg_dir / "full.png"
            composite_img.save(comp_file, format="PNG")
            generated_crops.append(str(comp_file))

            rel_comp_path = _get_relative_asset_path(
                comp_file, manifest_file, base_out_path
            )
            q["composite_asset_path"] = rel_comp_path
            q["composite_width"] = composite_img.width
            q["composite_height"] = composite_img.height

            composite_meta = {
                "asset_path": "full.png",
                "dimensions": {
                    "width": composite_img.width,
                    "height": composite_img.height,
                },
            }
            rel_composite_asset = _resolve_relative_path(
                comp_file, paper_dir, base_out_path
            )

        # Calculate question total marks
        if "marks" in q and q["marks"] is not None:
            q_total_marks = int(q["marks"])
        elif "total_question_marks" in q and q["total_question_marks"] is not None:
            q_total_marks = int(q["total_question_marks"])
        else:
            q_total_marks = sum(
                int(p["marks"])
                for p in question_parts_meta
                if p.get("marks") is not None
            )

        # Aggregate topics across question parts and question root
        q_topics = list(
            dict.fromkeys(
                (q.get("topics") or [])
                + [t for p in question_parts_meta for t in (p.get("topics") or [])]
            )
        )

        # Atomic question.json
        q_json_file = q_pkg_dir / "question.json"
        q_json_content = {
            "id": q_id,
            "paper_id": paper_id,
            "question_number": q_num,
            "total_marks": q_total_marks,
            "preamble": preamble_meta,
            "parts": question_parts_meta,
            "composite": composite_meta,
            "taxonomy": {
                "topics": q_topics,
                "has_diagram": bool(
                    preamble_meta["present"] or q.get("has_diagram", False)
                ),
            },
        }
        q_json_file.write_text(json.dumps(q_json_content, indent=2), encoding="utf-8")

        # Manifest index item: spec dictates package_path: "questions/q{NN}/question.json"
        # and composite_asset: "questions/q{NN}/full.png" relative to paper root
        rel_pkg_path = _resolve_relative_path(q_json_file, paper_dir, base_out_path)

        question_index.append(
            {
                "question_number": q_num,
                "package_path": rel_pkg_path,
                "total_marks": q_total_marks,
                "composite_asset": rel_composite_asset,
            }
        )

    # Update verification block if present
    if "verification" in manifest_data and isinstance(
        manifest_data["verification"], dict
    ):
        total_extracted_marks = sum(item["total_marks"] for item in question_index)
        manifest_data["verification"]["extracted_marks"] = total_extracted_marks
        manifest_data["verification"]["balance_check"] = manifest_data["verification"][
            "extracted_marks"
        ] == manifest_data["verification"].get("expected_marks")

    # Update paper-level manifest
    manifest_data["question_index"] = question_index
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
    parser.add_argument(
        "--no-trim-margins",
        action="store_true",
        help="Disable automatic outer margin warning trimming",
    )

    args = parser.parse_args(argv)

    try:
        summary = crop_and_stitch(
            manifest_path=args.manifest,
            pages_dir=args.pages_dir,
            out_dir=args.out_dir,
            pad=args.pad,
            spacing=args.spacing,
            trim_margins=not args.no_trim_margins,
        )
        print(json.dumps(summary, indent=2))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
