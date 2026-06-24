"""Shared path utilities used across the LiteGS pipeline scripts."""

import logging
import shutil
from pathlib import Path


# ── repo-root paths (this file lives at <repo>/utils/common.py) ────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "data"
LITEGS_ROOT = REPO_ROOT / "LiteGS"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


# ── auto-detect helpers ─────────────────────────────────────────────────────

def auto_detect_frame_id(source_path: Path) -> str:
    """Extract frame_id (HHmmss) from the last directory segment.

    Two naming conventions are supported:

    *No prefix* — parts[0] is a 4-digit year, HHmmss at index 3::

        2026-06-13-234829          -> "234829"
        2026-06-23-175925-114      -> "175925"

    *With prefix* — parts[0] is a non-year token (e.g. image count),
    HHmmss shifts to index 4::

        114-2026-06-24-113513      -> "113513"
    """
    name = source_path.name
    parts = name.split("-")

    if len(parts) < 4:
        raise ValueError(
            f"Cannot auto-detect --frame_id from source path '{source_path}'. "
            f"Expected the last directory to match YYYY-MM-DD-HHmmss[*]. "
            f"Please specify --frame_id manually."
        )

    # Heuristic: if parts[0] looks like a year (4 digits, starts with 20xx),
    # the timestamp is at index 3.  Otherwise there is a leading prefix
    # (image count, label, ...) and the timestamp is at index 4.
    if _looks_like_year(parts[0]):
        ts_idx = 3
    else:
        ts_idx = 4

    if ts_idx >= len(parts):
        raise ValueError(
            f"Cannot auto-detect --frame_id from source path '{source_path}'. "
            f"With {len(parts)} segments, expected at least {ts_idx + 1}. "
            f"Please specify --frame_id manually."
        )

    frame_id = parts[ts_idx]
    if len(frame_id) != 6 or not frame_id.isdigit():
        raise ValueError(
            f"Cannot auto-detect --frame_id from source path '{source_path}'. "
            f"Expected parts[{ts_idx}] (HHmmss) to be a 6-digit number, got '{frame_id}'. "
            f"Please specify --frame_id manually."
        )

    return frame_id


def _looks_like_year(part: str) -> bool:
    """True if *part* is a 4-digit string starting with 20xx or 19xx."""
    return len(part) == 4 and part.isdigit() and (part.startswith("20") or part.startswith("19"))


def auto_detect_model_sub_dir(source_path: Path) -> str:
    """Extract model_sub_dir from source_path by finding the directory after 'data'.

    Examples::

        data/0613/2026-06-13-234829              -> "0613"
        data/0608/without_sword/2026-06-08-105443 -> "0608"
    """
    parts = source_path.parts
    try:
        data_idx = parts.index("data")
        if data_idx + 1 < len(parts):
            return parts[data_idx + 1]
    except ValueError:
        pass
    raise ValueError(
        f"Cannot auto-detect --model_sub_dir from source path '{source_path}'. "
        f"Expected to find 'data' directory in the path. "
        f"Please specify --model_sub_dir manually."
    )


# ── image rename utility ────────────────────────────────────────────────────

def is_image(path: Path) -> bool:
    """Return True if *path* is a file with a recognised image extension."""
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def rename_images_sequential(
    image_dir: Path,
    start: int = 1,
    width: int = 3,
    dry_run: bool = False,
) -> int:
    """Rename images in *image_dir* to zero-padded sequential numbers.

    Images are sorted alphabetically before renaming.  Extensions are
    preserved (lower-cased).  This is typically called on ``raw_imgs/`` once
    before the pipeline so that image names match calibration expectations
    (e.g. ``001.jpg``, ``002.jpg``, …).

    Args:
        image_dir: Directory containing images.
        start: Starting index (1-based by default).
        width: Zero-padding width (3 → ``001``, ``002``, …).
        dry_run: If True, only log what would be renamed without touching files.

    Returns:
        Number of files renamed.
    """
    images = sorted(p for p in image_dir.iterdir() if is_image(p))
    if not images:
        logging.warning("No images found in %s", image_dir)
        return 0

    rename_map: list[tuple[Path, Path]] = []
    for i, old_path in enumerate(images):
        ext = old_path.suffix.lower()
        new_name = f"{start + i:0{width}d}{ext}"
        new_path = image_dir / new_name
        if old_path == new_path:
            continue
        if new_path.exists():
            raise FileExistsError(
                f"Target name already exists: {new_path} (from {old_path.name})"
            )
        rename_map.append((old_path, new_path))

    if not rename_map:
        logging.info("All images already have sequential names — nothing to do.")
        return 0

    if dry_run:
        for old, new in rename_map:
            logging.info("  [dry-run] %s → %s", old.name, new.name)
        logging.info("  Would rename %d file(s).", len(rename_map))
        return 0

    for old, new in rename_map:
        shutil.move(str(old), str(new))

    logging.info("Renamed %d image(s) sequentially (%03d…%03d).", len(rename_map), start, start + len(rename_map) - 1)
    return len(rename_map)
