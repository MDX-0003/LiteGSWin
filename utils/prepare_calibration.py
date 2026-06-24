import argparse
import logging
import shutil
import struct
import subprocess
import sys
from pathlib import Path
#uv run python utils/prepare_calibration.py --sub_dir 0624
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from utils.common import rename_images_sequential

READ_WRITE_MODEL_ROOT = REPO_ROOT / "gaussian-splatting" / "utils"
sys.path.insert(0, str(READ_WRITE_MODEL_ROOT))
from read_write_model import read_images_binary


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


CALIBRATION_ROOT = REPO_ROOT / "data" / "calibration"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare COLMAP calibration baseline data."
    )
    parser.add_argument(
        "--sub_dir",
        required=True,
        type=str,
        help="Subdirectory under ./data/calibration that contains calibration images.",
    )
    parser.add_argument(
        "--no_gpu",
        action="store_true",
        help="Disable GPU use in COLMAP SIFT extraction and matching.",
    )
    parser.add_argument(
        "--colmap_executable",
        default="colmap",
        type=str,
        help="COLMAP executable path or command name.",
    )
    return parser.parse_args()


def resolve_calibration_path(sub_dir: str) -> Path:
    calibration_root = CALIBRATION_ROOT.resolve()
    source_path = (calibration_root / sub_dir).resolve()

    try:
        source_path.relative_to(calibration_root)
    except ValueError as exc:
        raise ValueError(
            f"sub_dir must point inside {calibration_root}: {sub_dir}"
        ) from exc

    return source_path


def is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def _resolve_image_dir(source_path: Path) -> Path:
    """Find the directory that actually contains calibration images.

    *If* ``source_path`` itself has images → return ``source_path``.
    *Else if* exactly one immediate subdirectory has images → return that
    subdirectory.  All other situations (no images at all, or multiple
    subdirectories with images) raise an error.
    """
    # Case 1: images directly in source_path
    if any(is_image(p) for p in source_path.iterdir()):
        return source_path

    # Case 2: look in immediate subdirectories
    subdirs_with_images: list[Path] = []
    for sub in sorted(source_path.iterdir()):
        if not sub.is_dir():
            continue
        if any(is_image(p) for p in sub.iterdir()):
            subdirs_with_images.append(sub)

    if len(subdirs_with_images) == 1:
        logging.info("Using images from subdirectory: %s", subdirs_with_images[0].name)
        return subdirs_with_images[0]

    if len(subdirs_with_images) == 0:
        raise FileNotFoundError(
            f"No images found in {source_path} or its immediate subdirectories. "
            f"Please place calibration images in this directory."
        )

    raise FileNotFoundError(
        f"Ambiguous: multiple subdirectories contain images in {source_path}. "
        f"Please place images directly in this directory, or keep only one "
        f"subdirectory with images. Found: "
        + ", ".join(d.name for d in subdirs_with_images)
    )


def move_images_to_input(source_path: Path) -> int:
    image_dir = _resolve_image_dir(source_path)
    input_path = source_path / "input"
    input_path.mkdir(parents=True, exist_ok=True)

    moved_count = 0
    for image_path in sorted(image_dir.iterdir()):
        if not is_image(image_path):
            continue

        target_path = input_path / image_path.name
        if target_path.exists():
            raise FileExistsError(f"Target image already exists: {target_path}")

        shutil.move(str(image_path), str(target_path))
        moved_count += 1

    return moved_count


def has_input_images(source_path: Path) -> bool:
    input_path = source_path / "input"
    return input_path.exists() and any(is_image(path) for path in input_path.iterdir())


def run_colmap(colmap_executable: str, args: list[str]) -> None:
    command = [colmap_executable, *args]
    step_name = args[0] if args else "command"
    logging.info("COLMAP %s ...", step_name)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr or result.stdout or "(no output)"
        logging.error("COLMAP %s failed (code %d):\n%s", step_name, result.returncode, detail)
        raise subprocess.CalledProcessError(
            result.returncode, command, result.stdout, result.stderr
        )
    logging.info("COLMAP %s done.", step_name)


def run_reconstruction(source_path: Path, colmap_executable: str, use_gpu: int) -> None:
    input_path = source_path / "input"
    distorted_path = source_path / "distorted"
    database_path = distorted_path / "database.db"
    sparse_path = distorted_path / "sparse"

    sparse_path.mkdir(parents=True, exist_ok=True)

    run_colmap(
        colmap_executable,
        [
            "feature_extractor",
            "--database_path",
            str(database_path),
            "--image_path",
            str(input_path),
            "--ImageReader.single_camera",
            "0",
            "--SiftExtraction.use_gpu",
            str(use_gpu),
        ],
    )

    run_colmap(
        colmap_executable,
        [
            "exhaustive_matcher",
            "--database_path",
            str(database_path),
            "--SiftMatching.use_gpu",
            str(use_gpu),
        ],
    )

    run_colmap(
        colmap_executable,
        [
            "mapper",
            "--database_path",
            str(database_path),
            "--image_path",
            str(input_path),
            "--output_path",
            str(sparse_path),
            "--Mapper.ba_global_function_tolerance=0.000001",
        ],
    )


def read_colmap_binary_count(path: Path) -> int:
    with path.open("rb") as file:
        return struct.unpack("<Q", file.read(8))[0]


def sorted_input_image_names(source_path: Path) -> list[str]:
    input_path = source_path / "input"
    return sorted(path.name for path in input_path.iterdir() if is_image(path))


def read_sparse_image_names(sparse_bin_path: Path) -> list[str]:
    images = read_images_binary(str(sparse_bin_path / "images.bin"))
    return sorted(image.name for image in images.values())


def find_best_sparse_model(source_path: Path) -> Path:
    sparse_root = source_path / "distorted" / "sparse"
    required_bins = ["cameras.bin", "images.bin", "points3D.bin"]
    input_names = sorted_input_image_names(source_path)
    input_name_set = set(input_names)
    candidates: list[tuple[int, int, Path, list[str]]] = []

    for sparse_bin_path in sorted(path for path in sparse_root.iterdir() if path.is_dir()):
        missing_bins = [
            name for name in required_bins if not (sparse_bin_path / name).exists()
        ]
        if missing_bins:
            continue

        image_count = read_colmap_binary_count(sparse_bin_path / "images.bin")
        point_count = read_colmap_binary_count(sparse_bin_path / "points3D.bin")
        image_names = read_sparse_image_names(sparse_bin_path)
        candidates.append((image_count, point_count, sparse_bin_path, image_names))

    if not candidates:
        raise FileNotFoundError(
            f"No complete COLMAP sparse model found in {sparse_root}"
        )

    complete_candidates = [
        candidate
        for candidate in candidates
        if set(candidate[3]) == input_name_set and candidate[0] == len(input_names)
    ]
    if not complete_candidates:
        logging.error(
            "No COLMAP sparse model covers all calibration input images. "
            "Input images: %d.",
            len(input_names),
        )
        for image_count, point_count, sparse_bin_path, image_names in sorted(
            candidates,
            key=lambda item: item[:2],
            reverse=True,
        ):
            image_name_set = set(image_names)
            missing = sorted(input_name_set - image_name_set)
            extra = sorted(image_name_set - input_name_set)
            logging.error(
                "Candidate %s: %d/%d images, %d points, missing=%d, extra=%d%s%s",
                sparse_bin_path,
                image_count,
                len(input_names),
                point_count,
                len(missing),
                len(extra),
                f", missing examples={missing[:10]}" if missing else "",
                f", extra examples={extra[:10]}" if extra else "",
            )
        raise ValueError(
            "COLMAP calibration reconstruction is incomplete. "
            "Do not reuse this calibration; improve matching/capture quality "
            "until one sparse model registers every input image."
        )

    image_count, point_count, sparse_bin_path, _ = max(
        complete_candidates,
        key=lambda item: item[:2],
    )
    logging.info(
        "Selected complete calibration sparse model %s (%d/%d images, %d points).",
        sparse_bin_path,
        image_count,
        len(input_names),
        point_count,
    )
    return sparse_bin_path


def reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_sparse_bin_model(source_path: Path, sparse_bin_path: Path) -> Path:
    sparse_bin_output_path = source_path / "sparse_bin"
    reset_directory(sparse_bin_output_path)

    for source_file in sorted(sparse_bin_path.iterdir()):
        if not source_file.is_file():
            continue
        shutil.copy2(source_file, sparse_bin_output_path / source_file.name)

    logging.info("Copied selected calibration binary sparse model to %s.", sparse_bin_output_path)
    return sparse_bin_output_path


def convert_sparse_model(
    source_path: Path,
    sparse_bin_path: Path,
    colmap_executable: str,
) -> Path:
    sparse_tmp_path = source_path / "distorted" / "sparse_tmp"

    reset_directory(sparse_tmp_path)
    run_colmap(
        colmap_executable,
        [
            "model_converter",
            "--input_path",
            str(sparse_bin_path),
            "--output_path",
            str(sparse_tmp_path),
            "--output_type",
            "TXT",
        ],
    )

    return sparse_tmp_path


def strip_calibration_keypoints(images_txt_path: Path) -> None:
    """Replace per-image keypoint lines with a single placeholder.

    COLMAP point_triangulator requires 2D point counts to match between the
    calibration model and the training database.  Since calibration images
    and training images differ, we strip the original keypoints and write one
    dummy entry ``0 0 -1`` per image.  The matching counts will be filled in
    by prepare_colmap_dataset.py after the training database is built.

    A non-empty keypoint line is mandatory: load_calibration_image_mapping()
    uses an alternating state machine that skips empty lines without toggling
    state, which would silently drop every other image.
    """
    lines = images_txt_path.read_text(encoding="utf-8").splitlines()
    with images_txt_path.open("w", encoding="utf-8") as f:
        for raw_line in lines:
            s = raw_line.strip()
            if not s or s.startswith("#"):
                f.write(raw_line + "\n")
                continue
            parts = s.split()
            if parts[0].isdigit() and parts[-1].endswith((".jpg", ".png", ".jpeg")):
                f.write(raw_line + "\n")
                f.write("0 0 -1\n")  # placeholder keypoint, keeps parser state correct
    logging.info("Stripped calibration keypoints in %s.", images_txt_path)


def write_baseline_sparse(source_path: Path, sparse_tmp_path: Path) -> None:
    baseline_sparse_path = source_path / "sparse"
    reset_directory(baseline_sparse_path)

    for name in ["cameras.txt", "images.txt"]:
        source_file = sparse_tmp_path / name
        if not source_file.exists():
            raise FileNotFoundError(f"Missing converted sparse file: {source_file}")
        shutil.copy2(source_file, baseline_sparse_path / name)

    (baseline_sparse_path / "points3D.txt").write_text("", encoding="utf-8")

    # Strip per-image keypoints so they can be synced with training DB later
    strip_calibration_keypoints(baseline_sparse_path / "images.txt")

    logging.info("Wrote reusable calibration text sparse model to %s.", baseline_sparse_path)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    try:
        source_path = resolve_calibration_path(args.sub_dir)

        if not source_path.exists():
            source_path.mkdir(parents=True, exist_ok=True)
            logging.error(
                "Calibration directory does not exist: %s. "
                "Please place calibration images in this directory and try again.",
                source_path,
            )
            return 1

        move_images_to_input(source_path)
        rename_images_sequential(source_path / "input")
        if not has_input_images(source_path):
            logging.error(
                "No calibration images found in %s. "
                "Please place images in this directory.",
                source_path / "input",
            )
            return 1

        use_gpu = 0 if args.no_gpu else 1
        run_reconstruction(source_path, args.colmap_executable, use_gpu)
        sparse_bin_path = find_best_sparse_model(source_path)
        copy_sparse_bin_model(source_path, sparse_bin_path)
        sparse_tmp_path = convert_sparse_model(
            source_path,
            sparse_bin_path,
            args.colmap_executable,
        )
        write_baseline_sparse(source_path, sparse_tmp_path)
    except subprocess.CalledProcessError as exc:
        logging.error("COLMAP command failed with code %s.", exc.returncode)
        return exc.returncode
    except Exception as exc:
        logging.error("%s", exc)
        return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
