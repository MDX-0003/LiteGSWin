import argparse
import re
import tempfile
import sys
from pathlib import Path

from PIL import Image, ImageOps


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def natural_key(path: Path) -> list[int | str]:
    parts = re.split(r"(\d+)", path.name.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def build_plan(source_dir: Path) -> list[tuple[Path, Path]]:
    files = sorted([path for path in source_dir.iterdir() if is_image(path)], key=natural_key)

    if not files:
        raise ValueError(f"No images found in {source_dir}.")

    return [
        (source, source_dir / f"{index:03d}.jpg")
        for index, source in enumerate(files, start=1)
    ]


def convert_to_jpeg(source: Path, destination: Path, quality: int) -> None:
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode in {"RGBA", "LA"}:
            background = Image.new("RGB", image.size, (255, 255, 255))
            alpha = image.getchannel("A")
            background.paste(image.convert("RGB"), mask=alpha)
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")
        image.save(destination, "JPEG", quality=quality, optimize=True)


def apply_plan(
    plan: list[tuple[Path, Path]],
    *,
    dry_run: bool,
    force: bool,
    quality: int,
) -> None:
    source_paths = {source.resolve() for source, _ in plan}
    target_paths = [target for _, target in plan]
    existing_targets = [
        path
        for path in target_paths
        if path.exists() and path.resolve() not in source_paths
    ]
    if existing_targets and not force:
        raise FileExistsError(
            "Target files already exist. Use --force to overwrite: "
            + ", ".join(path.name for path in existing_targets[:10])
        )

    if dry_run:
        for source, target in plan:
            print(f"{source.name} -> {target.name}")
        return

    source_dir = plan[0][0].parent
    temp_dir = Path(tempfile.mkdtemp(prefix=".rename_sequence_tmp_", dir=source_dir))
    temp_paths = [
        temp_dir / f"{index:03d}.jpg"
        for index, _ in enumerate(plan, start=1)
    ]
    cleanup_temps = True

    try:
        for (source, _), temp_path in zip(plan, temp_paths):
            convert_to_jpeg(source, temp_path, quality)

        cleanup_temps = False
        paths_to_remove = {
            path.resolve()
            for path in [*[source for source, _ in plan], *existing_targets]
            if path.exists()
        }
        for path in paths_to_remove:
            path.unlink()

        for temp_path, (_, target) in zip(temp_paths, plan):
            temp_path.rename(target)

        temp_dir.rmdir()
    except Exception:
        if cleanup_temps:
            for temp_path in temp_paths:
                if temp_path.exists():
                    temp_path.unlink()
            if temp_dir.exists():
                temp_dir.rmdir()
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert and rename images in a directory to 001.jpg, 002.jpg, ..."
        )
    )
    parser.add_argument(
        "source_dir",
        nargs="?",
        help="Image directory to process.",
    )
    parser.add_argument(
        "-s",
        "--source-dir",
        dest="source_dir_option",
        help="Image directory to process, for example: -s ./data/0617/2026-06-17-171245",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the rename plan without changing files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing sequential JPG outputs.",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=95,
        help="JPEG quality used during conversion.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.source_dir and args.source_dir_option:
            raise ValueError("Use either positional source_dir or -s/--source-dir, not both.")

        source_dir_arg = args.source_dir_option or args.source_dir
        if not source_dir_arg:
            raise ValueError("Missing source directory. Use -s ./data/0617/2026-06-17-171245.")

        source_dir = Path(source_dir_arg).resolve()
        if not source_dir.exists():
            raise FileNotFoundError(f"Source directory does not exist: {source_dir}")
        if not source_dir.is_dir():
            raise NotADirectoryError(f"Source path is not a directory: {source_dir}")
        if not 1 <= args.quality <= 100:
            raise ValueError("--quality must be between 1 and 100.")

        plan = build_plan(source_dir)
        apply_plan(plan, dry_run=args.dry_run, force=args.force, quality=args.quality)
        if not args.dry_run:
            print(f"Converted and renamed {len(plan)} images in {source_dir}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
