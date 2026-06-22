"""Batch runner: serially run the LiteGS pipeline on all frames under a sub_dir.

Usage:
    python batch_run.py --sub_dir 0613
    python batch_run.py --sub_dir 0613 -r 4 --target_primitives 500000
    python batch_run.py --sub_dir 0613 --start_from 2026-06-13-234712

All extra arguments are forwarded to run_LiteGS_pipeline.py.
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
DATA_ROOT = REPO_ROOT / "data"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch run the LiteGS pipeline on all frames under data/<sub_dir>/."
    )
    parser.add_argument(
        "--sub_dir",
        required=True,
        type=str,
        help="Subdirectory under ./data that contains frame directories.",
    )
    parser.add_argument(
        "--start_from",
        default=None,
        type=str,
        help="Only process frames at or after this directory name (e.g. 2026-06-13-234712).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run even if the output PLY already exists.",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="List frames that would be processed without actually running.",
    )
    parser.add_argument(
        "--python_executable",
        default=sys.executable,
        type=str,
        help="Python executable for child processes.",
    )
    args, pipeline_extra_args = parser.parse_known_args()
    args.pipeline_extra_args = pipeline_extra_args
    return args


def discover_frames(sub_dir: str, start_from: str | None = None) -> list[Path]:
    """Find all timestamp directories under data/<sub_dir>/, sorted by name."""
    sub_dir_path = (DATA_ROOT / sub_dir).resolve()
    if not sub_dir_path.exists():
        raise FileNotFoundError(f"Directory does not exist: {sub_dir_path}")

    frames = sorted(
        p for p in sub_dir_path.iterdir()
        if p.is_dir()
    )

    if start_from:
        frames = [f for f in frames if f.name >= start_from]

    return frames


def output_already_exists(sub_dir: str, frame_id: str) -> bool:
    """Check if the final PLY for this frame already exists."""
    output_ply = REPO_ROOT / "results" / sub_dir / f"{sub_dir}-{frame_id}.ply"
    return output_ply.exists()


def auto_detect_frame_id(frame_path: Path) -> str:
    """Extract frame_id from directory name, same logic as run_LiteGS_pipeline."""
    parts = frame_path.name.split("-")
    if len(parts) >= 4 and len(parts[-1]) == 6 and parts[-1].isdigit():
        return parts[-1]
    raise ValueError(f"Cannot extract frame_id from: {frame_path.name}")


def run_single(
    frame_path: Path,
    sub_dir: str,
    pipeline_extra_args: list[str],
    python_executable: str,
) -> int:
    """Run the pipeline for one frame. Returns the exit code."""
    command = [
        python_executable,
        str(REPO_ROOT / "run_LiteGS_pipeline.py"),
        "-s",
        str(frame_path),
        *pipeline_extra_args,
    ]
    logging.info("Running: %s", " ".join(command))
    result = subprocess.run(command, cwd=str(REPO_ROOT))
    return result.returncode


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    args = parse_args()

    try:
        frames = discover_frames(args.sub_dir, args.start_from)
    except FileNotFoundError as exc:
        logging.error("%s", exc)
        return 1

    if not frames:
        logging.info("No frame directories found under data/%s/.", args.sub_dir)
        return 0

    logging.info(
        "Found %d frame(s) under data/%s/%s",
        len(frames),
        args.sub_dir,
        f" (starting from {args.start_from})" if args.start_from else "",
    )

    skipped: list[Path] = []
    to_process: list[Path] = []

    for frame_path in frames:
        try:
            fid = auto_detect_frame_id(frame_path)
        except ValueError:
            logging.warning("Skipping %s (cannot extract frame_id)", frame_path.name)
            skipped.append(frame_path)
            continue

        if not args.force and output_already_exists(args.sub_dir, fid):
            logging.info(
                "Skipping %s (output already exists, use --force to re-run)",
                frame_path.name,
            )
            skipped.append(frame_path)
            continue

        to_process.append(frame_path)

    if args.dry_run:
        logging.info("Dry run — would process %d frame(s):", len(to_process))
        for fp in to_process:
            logging.info("  %s", fp.name)
        if skipped:
            logging.info("Would skip %d frame(s):", len(skipped))
            for fp in skipped:
                logging.info("  %s", fp.name)
        return 0

    if not to_process:
        logging.info("All frames already processed. Use --force to re-run.")
        return 0

    logging.info("Will process %d frame(s):", len(to_process))
    for fp in to_process:
        logging.info("  %s", fp.name)

    failed: list[tuple[Path, int]] = []
    for i, frame_path in enumerate(to_process, 1):
        logging.info(
            "=== [%d/%d] %s ===", i, len(to_process), frame_path.name,
        )
        code = run_single(
            frame_path,
            args.sub_dir,
            args.pipeline_extra_args,
            args.python_executable,
        )
        if code != 0:
            logging.error("Frame %s failed with code %d.", frame_path.name, code)
            failed.append((frame_path, code))
        else:
            logging.info("Frame %s completed.", frame_path.name)

    logging.info(
        "Batch done. %d succeeded, %d failed.",
        len(to_process) - len(failed),
        len(failed),
    )
    if failed:
        logging.error("Failed frames:")
        for fp, code in failed:
            logging.error("  %s (code %d)", fp.name, code)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
