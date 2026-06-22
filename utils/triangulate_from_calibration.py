import argparse
import logging
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CALIBRATION_ROOT = REPO_ROOT / "data" / "calibration"
COLMAP_IMAGE_ID_MAX = 2147483647


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Triangulate a scene with known COLMAP camera parameters and "
            "prepare a 3DGS-compatible COLMAP dataset."
        )
    )
    parser.add_argument(
        "-s",
        "--source_path",
        required=True,
        type=str,
        help="Scene root path. It should contain input images in ./input.",
    )

    calib_group = parser.add_mutually_exclusive_group(required=True)
    calib_group.add_argument(
        "--calib_sub_dir",
        type=str,
        help=(
            "Calibration subdirectory under ./data/calibration. The script "
            "uses ./data/calibration/<calib_sub_dir>/sparse_calib."
        ),
    )
    calib_group.add_argument(
        "--calib_sparse_path",
        type=str,
        help=(
            "Direct path to the calibration sparse text model. It may point "
            "to sparse_calib or sparse_calib/0."
        ),
    )

    parser.add_argument(
        "--calibration_root",
        default=str(DEFAULT_CALIBRATION_ROOT),
        type=str,
        help="Root directory used with --calib_sub_dir.",
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
    parser.add_argument(
        "--skip_matching",
        action="store_true",
        help="Skip feature extraction and matching, and reuse an existing database.db.",
    )
    return parser.parse_args()


def is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def move_root_images_to_input(source_path: Path) -> int:
    input_path = source_path / "input"
    input_path.mkdir(parents=True, exist_ok=True)

    moved_count = 0
    for image_path in sorted(source_path.iterdir()):
        if not is_image(image_path):
            continue

        target_path = input_path / image_path.name
        if target_path.exists():
            raise FileExistsError(f"Target image already exists: {target_path}")
        shutil.move(str(image_path), str(target_path))
        moved_count += 1

    return moved_count


def ensure_input_images(source_path: Path) -> None:
    move_root_images_to_input(source_path)

    input_path = source_path / "input"
    if not input_path.exists() or not any(is_image(path) for path in input_path.iterdir()):
        raise FileNotFoundError(f"No input images found in {input_path}")


def resolve_calibration_model(args: argparse.Namespace) -> Path:
    if args.calib_sparse_path:
        sparse_paths = [Path(args.calib_sparse_path)]
    else:
        calibration_root = Path(args.calibration_root)
        calibration_path = calibration_root / args.calib_sub_dir
        sparse_paths = [
            calibration_path / "sparse_calib",
            calibration_path / "sparse",
        ]

    checked_paths = []
    for sparse_path in sparse_paths:
        sparse_path = sparse_path.resolve()
        candidates = [sparse_path, sparse_path / "0"]
        for candidate in candidates:
            checked_paths.append(candidate)
            if (candidate / "cameras.txt").exists() and (candidate / "images.txt").exists():
                points3d_path = candidate / "points3D.txt"
                if not points3d_path.exists():
                    points3d_path.write_text("", encoding="utf-8")
                return candidate

    raise FileNotFoundError(
        "Cannot find cameras.txt and images.txt in: "
        + ", ".join(str(path) for path in checked_paths)
    )


def load_calibration_image_mapping(
    calibration_model_path: Path,
) -> dict[str, tuple[int, int]]:
    """Return image name -> (image_id, camera_id) from COLMAP images.txt."""
    images_txt = calibration_model_path / "images.txt"
    mapping: dict[str, tuple[int, int]] = {}
    expect_image_line = True

    for raw_line in images_txt.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if not expect_image_line:
            expect_image_line = True
            continue

        parts = line.split()
        if len(parts) < 10:
            raise ValueError(f"Invalid COLMAP image line in {images_txt}: {line}")

        image_id = int(parts[0])
        camera_id = int(parts[8])
        image_name = " ".join(parts[9:])
        if image_name in mapping:
            raise ValueError(f"Duplicate image name in calibration model: {image_name}")

        mapping[image_name] = (image_id, camera_id)
        expect_image_line = False

    if not mapping:
        raise ValueError(f"No image entries found in {images_txt}")
    return mapping


def table_row_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def clear_database_matches(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        matches = table_row_count(connection, "matches")
        two_view_geometries = table_row_count(connection, "two_view_geometries")
        if matches or two_view_geometries:
            connection.execute("DELETE FROM matches")
            connection.execute("DELETE FROM two_view_geometries")
            connection.commit()
            logging.info(
                "Cleared existing COLMAP matches before rematching "
                "(%d matches, %d geometries).",
                matches,
                two_view_geometries,
            )
    finally:
        connection.close()


def update_id_with_temporary_values(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    id_mapping: dict[int, int],
    upper_bound: int | None = None,
) -> None:
    changed = {old: new for old, new in id_mapping.items() if old != new}
    if not changed:
        return

    current_max = connection.execute(
        f"SELECT COALESCE(MAX({column}), 0) FROM {table}"
    ).fetchone()[0]
    max_target = max(changed.values(), default=0)
    temp_start = max(current_max, max_target) + 1
    temp_mapping = {
        old: temp_start + index for index, old in enumerate(changed)
    }
    if upper_bound is not None and max(temp_mapping.values()) >= upper_bound:
        raise ValueError(
            f"Cannot remap {table}.{column}: not enough temporary ids below "
            f"{upper_bound}."
        )

    for old_id, temp_id in temp_mapping.items():
        connection.execute(
            f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
            (temp_id, old_id),
        )
    for old_id, new_id in changed.items():
        connection.execute(
            f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
            (new_id, temp_mapping[old_id]),
        )


def update_camera_references(
    connection: sqlite3.Connection,
    camera_id_mapping: dict[int, int],
) -> None:
    changed = {old: new for old, new in camera_id_mapping.items() if old != new}
    if not changed:
        return

    temp_mapping = {old: -old for old in changed}
    for old_id, temp_id in temp_mapping.items():
        connection.execute(
            "UPDATE images SET camera_id = ? WHERE camera_id = ?",
            (temp_id, old_id),
        )
        connection.execute(
            "UPDATE frames SET rig_id = ? WHERE rig_id = ?",
            (temp_id, old_id),
        )
        connection.execute(
            "UPDATE frame_data SET sensor_id = ? WHERE sensor_id = ?",
            (temp_id, old_id),
        )
        connection.execute(
            "UPDATE rig_sensors SET sensor_id = ? WHERE sensor_id = ?",
            (temp_id, old_id),
        )
        connection.execute(
            "UPDATE rigs SET ref_sensor_id = ? WHERE ref_sensor_id = ?",
            (temp_id, old_id),
        )
        connection.execute(
            "UPDATE cameras SET camera_id = ? WHERE camera_id = ?",
            (temp_id, old_id),
        )
        connection.execute(
            "UPDATE rigs SET rig_id = ? WHERE rig_id = ?",
            (temp_id, old_id),
        )

    for old_id, new_id in changed.items():
        temp_id = temp_mapping[old_id]
        connection.execute(
            "UPDATE images SET camera_id = ? WHERE camera_id = ?",
            (new_id, temp_id),
        )
        connection.execute(
            "UPDATE frames SET rig_id = ? WHERE rig_id = ?",
            (new_id, temp_id),
        )
        connection.execute(
            "UPDATE frame_data SET sensor_id = ? WHERE sensor_id = ?",
            (new_id, temp_id),
        )
        connection.execute(
            "UPDATE rig_sensors SET sensor_id = ? WHERE sensor_id = ?",
            (new_id, temp_id),
        )
        connection.execute(
            "UPDATE rigs SET ref_sensor_id = ? WHERE ref_sensor_id = ?",
            (new_id, temp_id),
        )
        connection.execute(
            "UPDATE cameras SET camera_id = ? WHERE camera_id = ?",
            (new_id, temp_id),
        )
        connection.execute(
            "UPDATE rigs SET rig_id = ? WHERE rig_id = ?",
            (new_id, temp_id),
        )


def normalize_database_to_calibration(
    database_path: Path,
    calibration_model_path: Path,
    allow_matched_database: bool = False,
) -> None:
    """Align COLMAP database ids with calibration images.txt by image name."""
    calibration_mapping = load_calibration_image_mapping(calibration_model_path)

    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        rows = connection.execute(
            "SELECT image_id, name, camera_id FROM images ORDER BY image_id"
        ).fetchall()

        database_names = {name for _, name, _ in rows}
        calibration_names = set(calibration_mapping)
        missing_in_database = sorted(calibration_names - database_names)
        extra_in_database = sorted(database_names - calibration_names)
        if missing_in_database or extra_in_database:
            detail = []
            if missing_in_database:
                detail.append(
                    "missing in database: " + ", ".join(missing_in_database[:10])
                )
            if extra_in_database:
                detail.append(
                    "extra in database: " + ", ".join(extra_in_database[:10])
                )
            raise ValueError(
                "Database images do not match calibration images.txt ("
                + "; ".join(detail)
                + ")"
            )

        image_id_mapping: dict[int, int] = {}
        camera_id_mapping: dict[int, int] = {}
        for image_id, name, camera_id in rows:
            expected_image_id, expected_camera_id = calibration_mapping[name]
            image_id_mapping[image_id] = expected_image_id
            if (
                camera_id in camera_id_mapping
                and camera_id_mapping[camera_id] != expected_camera_id
            ):
                raise ValueError(
                    f"Camera id {camera_id} maps to multiple calibration cameras."
                )
            camera_id_mapping[camera_id] = expected_camera_id

        if len(set(image_id_mapping.values())) != len(image_id_mapping):
            raise ValueError("Calibration image ids are not unique.")
        if len(set(camera_id_mapping.values())) != len(camera_id_mapping):
            raise ValueError("Calibration camera ids are not unique.")

        changed_images = sum(
            1 for old_id, new_id in image_id_mapping.items() if old_id != new_id
        )
        matched_rows = table_row_count(connection, "matches") + table_row_count(
            connection, "two_view_geometries"
        )
        if changed_images and matched_rows and not allow_matched_database:
            raise ValueError(
                "Existing COLMAP matches were created with image ids that do not "
                "match the calibration model. Re-run without --skip_matching so "
                "the script can normalize the database before matching."
            )

        connection.execute("BEGIN")
        update_id_with_temporary_values(
            connection, "frame_data", "frame_id", image_id_mapping
        )
        update_id_with_temporary_values(
            connection, "frame_data", "data_id", image_id_mapping
        )
        update_id_with_temporary_values(
            connection, "frames", "frame_id", image_id_mapping
        )
        update_id_with_temporary_values(
            connection, "pose_priors", "image_id", image_id_mapping
        )
        update_id_with_temporary_values(
            connection, "keypoints", "image_id", image_id_mapping
        )
        update_id_with_temporary_values(
            connection, "descriptors", "image_id", image_id_mapping
        )
        update_id_with_temporary_values(
            connection,
            "images",
            "image_id",
            image_id_mapping,
            upper_bound=COLMAP_IMAGE_ID_MAX,
        )
        update_camera_references(connection, camera_id_mapping)
        connection.commit()

        changed_cameras = sum(
            1 for old_id, new_id in camera_id_mapping.items() if old_id != new_id
        )
        if changed_images or changed_cameras:
            logging.info(
                "Normalized COLMAP database ids to calibration model "
                "(%d images, %d cameras remapped).",
                changed_images,
                changed_cameras,
            )
        elif table_row_count(connection, "matches"):
            logging.info("COLMAP database ids already match calibration model.")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


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


def run_feature_extraction_and_matching(
    source_path: Path,
    calibration_model_path: Path,
    colmap_executable: str,
    use_gpu: int,
) -> None:
    input_path = source_path / "input"
    distorted_path = source_path / "distorted"
    database_path = distorted_path / "database.db"

    distorted_path.mkdir(parents=True, exist_ok=True)

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

    clear_database_matches(database_path)

    normalize_database_to_calibration(database_path, calibration_model_path)

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


def sync_calibration_keypoints(
    database_path: Path,
    calibration_images_txt: Path,
) -> None:
    """Rewrite calibration images.txt keypoint lines to match the training DB.

    COLMAP point_triangulator requires image.second.NumPoints2D() ==
    existing_image.NumPoints2D() for every image.  Since the calibration
    photos and training photos are different sets, we replace the placeholder
    keypoints written by prepare_calibration.py with the actual SIFT keypoint
    counts from the freshly-built training database.
    """
    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute(
            "SELECT i.name, k.rows "
            "FROM images i JOIN keypoints k ON i.image_id = k.image_id "
            "ORDER BY i.image_id"
        ).fetchall()
    finally:
        connection.close()

    db_counts = {name: rows_count for name, rows_count in rows}

    lines = calibration_images_txt.read_text(encoding="utf-8").splitlines()
    with calibration_images_txt.open("w", encoding="utf-8") as f:
        for raw_line in lines:
            s = raw_line.strip()
            if not s or s.startswith("#"):
                f.write(raw_line + "\n")
                continue
            parts = s.split()
            if parts[0].isdigit() and parts[-1].endswith((".jpg", ".png", ".jpeg")):
                f.write(raw_line + "\n")
                img_name = parts[-1]
                count = db_counts.get(img_name, 0)
                placeholders = " ".join(f"{i * 10.0} {i * 10.0} -1" for i in range(count))
                f.write(placeholders + "\n" if placeholders else "0 0 -1\n")

    logging.info(
        "Synced calibration keypoint counts to training DB (%d images).",
        len(db_counts),
    )


def run_point_triangulator(
    source_path: Path,
    calibration_model_path: Path,
    colmap_executable: str,
) -> None:
    output_path = source_path / "distorted" / "sparse" / "0"
    output_path.mkdir(parents=True, exist_ok=True)

    run_colmap(
        colmap_executable,
        [
            "point_triangulator",
            "--database_path",
            str(source_path / "distorted" / "database.db"),
            "--image_path",
            str(source_path / "input"),
            "--input_path",
            str(calibration_model_path),
            "--output_path",
            str(output_path),
        ],
    )


def run_image_undistorter(source_path: Path, colmap_executable: str) -> None:
    """Run COLMAP image_undistorter"""
    run_colmap(
        colmap_executable,
        [
            "image_undistorter",
            "--image_path",
            str(source_path / "input"),
            "--input_path",
            str(source_path / "distorted" / "sparse" / "0"),
            "--output_path",
            str(source_path),
            "--output_type",
            "COLMAP",
        ],
    )

def move_sparse_files_into_zero(source_path: Path) -> None:
    sparse_root = source_path / "sparse"
    sparse_zero = sparse_root / "0"
    sparse_zero.mkdir(parents=True, exist_ok=True)

    for item in list(sparse_root.iterdir()):
        if item.name == "0" or not item.is_file():
            continue

        target_path = sparse_zero / item.name
        if target_path.exists():
            target_path.unlink()
        shutil.move(str(item), str(target_path))


def validate_outputs(source_path: Path) -> None:
    images_path = source_path / "images"
    sparse_zero = source_path / "sparse" / "0"
    required_sparse_files = ["cameras.bin", "images.bin", "points3D.bin"]

    if not images_path.exists() or not any(is_image(path) for path in images_path.iterdir()):
        raise FileNotFoundError(f"No undistorted training images found in {images_path}")

    missing_sparse_files = [
        name for name in required_sparse_files if not (sparse_zero / name).exists()
    ]
    if missing_sparse_files:
        raise FileNotFoundError(
            f"Missing COLMAP sparse files in {sparse_zero}: "
            + ", ".join(missing_sparse_files)
        )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    try:
        source_path = Path(args.source_path).resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Scene root does not exist: {source_path}")

        ensure_input_images(source_path)
        calibration_model_path = resolve_calibration_model(args)
        use_gpu = 0 if args.no_gpu else 1

        if not args.skip_matching:
            run_feature_extraction_and_matching(
                source_path,
                calibration_model_path,
                args.colmap_executable,
                use_gpu,
            )
        elif not (source_path / "distorted" / "database.db").exists():
            raise FileNotFoundError(
                f"Cannot skip matching because database.db does not exist: "
                f"{source_path / 'distorted' / 'database.db'}"
            )
        else:
            normalize_database_to_calibration(
                source_path / "distorted" / "database.db",
                calibration_model_path,
            )

        sync_calibration_keypoints(
            source_path / "distorted" / "database.db",
            calibration_model_path / "images.txt",
        )
        run_point_triangulator(source_path, calibration_model_path, args.colmap_executable)
        run_image_undistorter(source_path, args.colmap_executable)
        move_sparse_files_into_zero(source_path)
        validate_outputs(source_path)
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
