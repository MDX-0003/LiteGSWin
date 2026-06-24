import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import time

from utils.common import (
    auto_detect_frame_id,
    auto_detect_model_sub_dir,
    LITEGS_ROOT,
    REPO_ROOT,
)

# Allow importing from LiteGS/
sys.path.insert(0, str(LITEGS_ROOT))
from cameras_bin_to_json import convert as cameras_bin_to_json_convert


def resolve_params(args: argparse.Namespace, source_path: Path) -> None:
    """Fill in auto-detected values for missing parameters."""
    if args.frame_id is None:
        args.frame_id = auto_detect_frame_id(source_path)
        logging.info("Auto-detected frame_id = %s", args.frame_id)

    if args.model_sub_dir is None:
        args.model_sub_dir = auto_detect_model_sub_dir(source_path)
        logging.info("Auto-detected model_sub_dir = %s", args.model_sub_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run COLMAP triangulation from calibration and then train LiteGS."
        )
    )
    parser.add_argument(
        "-s",
        "--source_path",
        required=True,
        type=str,
        help="Scene root path, for example ./data/0613/2026-06-13-234829.",
    )
    parser.add_argument(
        "--model_sub_dir",
        default=None,
        type=str,
        help=(
            "Calibration subdirectory name. Auto-detected from source_path "
            "(directory after 'data'). Also used under ./results."
        ),
    )
    parser.add_argument(
        "--group_id",
        default=None,
        type=int,
        help="(Deprecated) No longer used in the output path.",
    )
    parser.add_argument(
        "--frame_id",
        default=None,
        type=str,
        help=(
            "Frame id (HHmmss). Auto-detected from the last segment of "
            "source_path (e.g. 2026-06-13-234829 -> 234829)."
        ),
    )
    parser.add_argument(
        "-r",
        "--resolution",
        default=2,
        type=int,
        help="LiteGS resolution parameter.",
    )
    parser.add_argument(
        "--target_primitives",
        default=300000,
        type=int,
        help="LiteGS target_primitives parameter.",
    )
    parser.add_argument(
        "--images",
        default="images",
        type=str,
        help="LiteGS image directory argument. Defaults to the undistorted images folder.",
    )
    parser.add_argument(
        "--model_path",
        default=None,
        type=str,
        help=(
            "Override LiteGS output directory. "
            "Defaults to ./results/<model_sub_dir>/<frame_id>."
        ),
    )
    parser.add_argument(
        "--calib_sparse_path",
        default=None,
        type=str,
        help="Direct path to sparse_calib or sparse_calib/0. Overrides --model_sub_dir.",
    )
    parser.add_argument(
        "--calibration_root",
        default=str(REPO_ROOT / "data" / "calibration"),
        type=str,
        help="Calibration root used by prepare_colmap_dataset.py.",
    )
    parser.add_argument(
        "--cameras_json_path",
        default=None,
        type=str,
        help=(
            "Override output path for cameras.json. "
            "Defaults to ./results/<model_sub_dir>/cameras.json."
        ),
    )
    parser.add_argument(
        "--no_gpu",
        action="store_true",
        help="Disable GPU use for COLMAP feature extraction and matching.",
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
        help="Skip COLMAP feature extraction/matching and reuse distorted/database.db.",
    )
    parser.add_argument(
        "--skip_colmap",
        action="store_true",
        help="Skip prepare_colmap_dataset.py and train from existing COLMAP outputs.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run even if the output PLY already exists.",
    )
    parser.add_argument(
        "--iterations",
        default=30000,
        type=int,
        help="LiteGS training iterations. Default: 30000.",
    )
    parser.add_argument(
        "--frame_stride",
        default=1,
        type=int,
        help="Keep every Nth image from input. Forwarded to prepare_colmap_dataset.py.",
    )
    parser.add_argument(
        "--frame_stride_min_images",
        default=3,
        type=int,
        help="Minimum images after stride. Forwarded to prepare_colmap_dataset.py.",
    )
    parser.add_argument(
        "--force_no_calib",
        action="store_true",
        help="Force COLMAP mapper mode. Forwarded to prepare_colmap_dataset.py.",
    )
    parser.add_argument(
        "--python_executable",
        default=sys.executable,
        type=str,
        help="Python executable used to run child scripts.",
    )
    parser.add_argument(
        "--timing_output",
        default=None,
        type=str,
        help=(
            "If set, write timing JSON to this path. "
            "Used by batch_run.py to collect per-frame timings."
        ),
    )
    args, train_extra_args = parser.parse_known_args()
    args.train_extra_args = normalize_extra_args(train_extra_args)
    return args


def normalize_extra_args(args: list[str]) -> list[str]:
    if args and args[0] == "--":
        return args[1:]
    return args


def run_command(command: list[str], cwd: Path) -> None:
    logging.info("Running: %s", " ".join(command))
    subprocess.run(command, cwd=str(cwd), check=True)


def build_colmap_command(args: argparse.Namespace, source_path: Path) -> list[str]:
    command = [
        args.python_executable,
        str(REPO_ROOT / "utils" / "prepare_colmap_dataset.py"),
        "-s",
        str(source_path),
        "--calibration_root",
        args.calibration_root,
        "--colmap_executable",
        args.colmap_executable,
        "--model_sub_dir",
        args.model_sub_dir,
        "--frame_stride",
        str(args.frame_stride),
        "--frame_stride_min_images",
        str(args.frame_stride_min_images),
    ]

    if args.calib_sparse_path:
        command.extend(["--calib_sparse_path", args.calib_sparse_path])
    elif not args.force_no_calib:
        # Only pass --calib_sub_dir when we intend to use calibration.
        # In auto-detect mode, prepare_colmap_dataset.py will auto-detect on its own.
        command.extend(["--calib_sub_dir", args.model_sub_dir])

    if args.no_gpu:
        command.append("--no_gpu")
    if args.skip_matching:
        command.append("--skip_matching")
    if args.force_no_calib:
        command.append("--force_no_calib")

    return command


def build_train_command(
    args: argparse.Namespace,
    source_path: Path,
    model_path: Path,
) -> list[str]:
    return [
        args.python_executable,
        str(REPO_ROOT / "LiteGS" / "example_train.py"),
        "-s",
        str(source_path),
        "-i",
        args.images,
        "-m",
        str(model_path),
        "-r",
        str(args.resolution),
        "--target_primitives",
        str(args.target_primitives),
        "--iterations",
        str(args.iterations),
        *normalize_extra_args(args.train_extra_args),
    ]


def generate_cameras_json(
    args: argparse.Namespace,
    source_path: Path,
    results_dir: Path,
) -> None:
    """Generate cameras.json from COLMAP sparse binary output.

    Uses LiteGS/cameras_bin_to_json.py to convert sparse/0/cameras.bin and
    sparse/0/images.bin into a gaussian-splatting-compatible cameras.json.
    """
    cameras_json_path = (
        Path(args.cameras_json_path)
        if args.cameras_json_path
        else results_dir / "cameras.json"
    )

    if cameras_json_path.exists():
        logging.info("cameras.json already exists at %s, skipping.", cameras_json_path)
        return

    sparse_zero = source_path / "sparse" / "0"
    cameras_bin = sparse_zero / "cameras.bin"
    images_bin = sparse_zero / "images.bin"

    if not cameras_bin.exists():
        logging.warning(
            "cameras.bin not found at %s, skipping cameras.json generation.",
            cameras_bin,
        )
        return

    if not images_bin.exists():
        logging.warning(
            "images.bin not found at %s, skipping cameras.json generation.",
            images_bin,
        )
        return

    cameras_json_path.parent.mkdir(parents=True, exist_ok=True)
    count = cameras_bin_to_json_convert(
        str(cameras_bin),
        str(images_bin),
        str(cameras_json_path),
        eval_mode=False,
        llffhold=8,
    )
    logging.info(
        "Generated cameras.json (%d cameras) at %s", count, cameras_json_path
    )


def copy_final_ply(model_path: Path, results_dir: Path, args: argparse.Namespace) -> None:
    """Copy the finished PLY to a flat, easy-to-find output path."""
    finish_ply = model_path / "point_cloud" / "finish" / "point_cloud.ply"
    if not finish_ply.exists():
        logging.warning(
            "Finished PLY not found at %s. Training may have failed or "
            "the output structure has changed.",
            finish_ply,
        )
        return

    output_name = f"{args.model_sub_dir}-{args.frame_id}.ply"
    output_path = results_dir / output_name
    shutil.copy2(str(finish_ply), str(output_path))
    logging.info("Copied final PLY to %s", output_path)


def check_output_exists(model_sub_dir: str, frame_id: str) -> Path | None:
    """Return the path if the output PLY already exists, else None."""
    output_ply = REPO_ROOT / "results" / model_sub_dir / f"{model_sub_dir}-{frame_id}.ply"
    return output_ply if output_ply.exists() else None


def write_frame_timing(
    timing_output: str,
    frame_name: str,
    frame_id: str,
    model_sub_dir: str,
    colmap_seconds: float,
    train_seconds: float,
) -> None:
    """Write per-frame timing JSON. Only called when --timing_output is set."""
    timing = {
        "frame_name": frame_name,
        "frame_id": frame_id,
        "model_sub_dir": model_sub_dir,
        "colmap_seconds": round(colmap_seconds, 1),
        "train_seconds": round(train_seconds, 1),
        "total_seconds": round(colmap_seconds + train_seconds, 1),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    timing_path = Path(timing_output)
    timing_path.parent.mkdir(parents=True, exist_ok=True)
    timing_path.write_text(json.dumps(timing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logging.info("Timing written to %s", timing_path)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    try:
        source_path = Path(args.source_path).resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Scene root does not exist: {source_path}")

        resolve_params(args, source_path)

        # Smart skip: don't re-run if output already exists
        existing = check_output_exists(args.model_sub_dir, args.frame_id)
        if existing and not args.force:
            logging.info(
                "Output already exists at %s. Skipping. Use --force to re-run.",
                existing,
            )
            return 0

        # Model output goes to results/<model_sub_dir>/<frame_id>/
        if args.model_path:
            model_path = Path(args.model_path).resolve()
        else:
            model_path = (
                REPO_ROOT / "results" / args.model_sub_dir / args.frame_id
            ).resolve()
        model_path.mkdir(parents=True, exist_ok=True)

        # Shared results at results/<model_sub_dir>/
        results_dir = model_path.parent

        colmap_seconds = 0.0
        train_seconds = 0.0

        if not args.skip_colmap:
            t0 = time.time()
            colmap_command = build_colmap_command(args, source_path)
            run_command(colmap_command, REPO_ROOT)
            colmap_seconds = time.time() - t0
            generate_cameras_json(args, source_path, results_dir)

        t0 = time.time()
        train_command = build_train_command(args, source_path, model_path)
        run_command(train_command, REPO_ROOT)
        train_seconds = time.time() - t0

        copy_final_ply(model_path, results_dir, args)

        if args.timing_output:
            write_frame_timing(
                args.timing_output,
                source_path.name,
                args.frame_id,
                args.model_sub_dir,
                colmap_seconds,
                train_seconds,
            )

    except subprocess.CalledProcessError as exc:
        logging.error("Command failed with code %s.", exc.returncode)
        return exc.returncode
    except Exception as exc:
        logging.error("%s", exc)
        return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    time_start = time.time()
    exit_code = main()
    time_total = time.time() - time_start
    logging.info("Total time: %.1f seconds (%.1f minutes)", time_total, time_total / 60)
    sys.exit(exit_code)
