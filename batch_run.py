"""Batch runner: serially run the LiteGS pipeline on all frames under a sub_dir.

Usage:
    uv run python batch_run.py --sub_dir 0613
    python batch_run.py --sub_dir 0613 -r 4 --target_primitives 500000
    python batch_run.py --sub_dir 0613 --start_from 2026-06-13-234712
    python batch_run.py --sub_dir 0613 --frame_stride 3
    uv run python batch_run.py --sub_dir 0618 --frame_stride 1 --force_no_calib --force  --iterations 10000   
    
    # 帧采样 — 每 3 张保留 1 张
    uv run python batch_run.py --sub_dir 0618 --frame_stride 3

    # 无标定数据模式 — COLMAP mapper 从零重建
    uv run python batch_run.py --sub_dir 0618 --force_no_calib

    # 组合使用 — 抽帧 + 无标定
    uv run python batch_run.py --sub_dir 0618 --frame_stride 3 --force_no_calib

    # 单帧也支持
    uv run python run_LiteGS_pipeline.py -s data\0618\2026-06-18-195909 --frame_stride 3

All extra arguments are forwarded to run_LiteGS_pipeline.py.
"""

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from utils.common import auto_detect_frame_id, REPO_ROOT, DATA_ROOT


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
    parser.add_argument(
        "--frames",
        nargs="*",
        default=None,
        type=str,
        help="Only process these specific frame directory names (space-separated). "
             "If omitted, all frame directories under data/<sub_dir>/ are processed.",
    )
    parser.add_argument(
        "--worker-status",
        type=str,
        default=None,
        help="Path to write a JSON status file during training "
             "(for distributed monitoring by v7 pipeline).",
    )
    args, pipeline_extra_args = parser.parse_known_args()
    args.pipeline_extra_args = pipeline_extra_args
    return args


def discover_frames(sub_dir: str, start_from: str | None = None,
                    frames: list[str] | None = None) -> list[Path]:
    """Find all timestamp directories under data/<sub_dir>/, sorted by name.

    If *frames* is given, only directories whose names appear in the list
    are returned (useful for distributed training where each worker only
    processes a subset of frames).
    """
    sub_dir_path = (DATA_ROOT / sub_dir).resolve()
    if not sub_dir_path.exists():
        raise FileNotFoundError(f"Directory does not exist: {sub_dir_path}")

    all_frames = sorted(
        p for p in sub_dir_path.iterdir()
        if p.is_dir()
    )

    if start_from:
        all_frames = [f for f in all_frames if f.name >= start_from]

    if frames is not None:
        frame_set = set(frames)
        all_frames = [f for f in all_frames if f.name in frame_set]

    return all_frames


def output_already_exists(sub_dir: str, frame_id: str) -> bool:
    """Check if the final PLY for this frame already exists."""
    output_ply = REPO_ROOT / "results" / sub_dir / f"{sub_dir}-{frame_id}.ply"
    return output_ply.exists()


def _frame_timing_path(sub_dir: str, frame_id: str) -> Path:
    """Intermediate per-frame timing file written by run_LiteGS_pipeline.py."""
    return REPO_ROOT / "results" / sub_dir / f"{frame_id}_timing.json"


def _batch_timing_path(sub_dir: str) -> Path:
    """Aggregated batch timing file."""
    return REPO_ROOT / "results" / sub_dir / "batch_timing.json"


def _write_worker_status(status_path: str | None, **fields) -> None:
    """Write a JSON status file for distributed monitoring (v7 pipeline).

    If *status_path* is None this is a no-op, so the behaviour is identical
    to the unmodified batch_run when the flag is not passed.

    The file is written atomically (tmp + rename).
    """
    if status_path is None:
        return
    import time as _time
    fields.setdefault("timestamp", _time.time())
    p = Path(status_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(fields, f, ensure_ascii=False, indent=2)
    tmp.replace(p)


def load_frame_timing(timing_path: Path) -> dict | None:
    """Read a per-frame timing JSON, or None if the file doesn't exist."""
    if not timing_path.exists():
        return None
    try:
        return json.loads(timing_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def upsert_batch_timing(sub_dir: str, frame_id: str, timing: dict) -> None:
    """Insert or update one frame's timing record in the batch JSON."""
    batch_path = _batch_timing_path(sub_dir)
    batch_path.parent.mkdir(parents=True, exist_ok=True)

    if batch_path.exists():
        try:
            batch = json.loads(batch_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            batch = {}
    else:
        batch = {}

    batch.setdefault("sub_dir", sub_dir)
    batch.setdefault("frames", {})
    batch["frames"][frame_id] = timing
    batch["updated_at"] = datetime.now(timezone.utc).isoformat()

    batch_path.write_text(json.dumps(batch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_single(
    frame_path: Path,
    frame_id: str,
    sub_dir: str,
    pipeline_extra_args: list[str],
    python_executable: str,
    force: bool = False,
) -> tuple[int, dict | None]:
    """Run the pipeline for one frame. Returns (exit_code, timing_dict_or_None)."""
    timing_output_path = _frame_timing_path(sub_dir, frame_id)

    command = [
        python_executable,
        str(REPO_ROOT / "run_LiteGS_pipeline.py"),
        "-s",
        str(frame_path),
        "--timing_output",
        str(timing_output_path),
        *pipeline_extra_args,
    ]
    if force:
        command.append("--force")
    logging.info("Running: %s", " ".join(command))
    result = subprocess.run(command, cwd=str(REPO_ROOT))

    timing = load_frame_timing(timing_output_path)
    return result.returncode, timing


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    args = parse_args()

    try:
        frames = discover_frames(args.sub_dir, args.start_from, args.frames)
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

    skipped: list[tuple[Path, str]] = []   # (path, reason)
    to_process: list[tuple[Path, str]] = []  # (path, frame_id)

    for frame_path in frames:
        try:
            fid = auto_detect_frame_id(frame_path)
        except ValueError:
            logging.warning("Skipping %s (cannot extract frame_id)", frame_path.name)
            skipped.append((frame_path, "cannot extract frame_id"))
            continue

        if not args.force and output_already_exists(args.sub_dir, fid):
            logging.info(
                "Skipping %s (output already exists, use --force to re-run)",
                frame_path.name,
            )
            skipped.append((frame_path, "output exists"))
            continue

        to_process.append((frame_path, fid))

    if args.dry_run:
        logging.info("Dry run — would process %d frame(s):", len(to_process))
        for fp, _fid in to_process:
            logging.info("  %s", fp.name)
        if skipped:
            logging.info("Would skip %d frame(s):", len(skipped))
            for fp, _reason in skipped:
                logging.info("  %s", fp.name)
        return 0

    if not to_process:
        logging.info("All frames already processed. Use --force to re-run.")
        return 0

    logging.info("Will process %d frame(s):", len(to_process))
    for fp, _fid in to_process:
        logging.info("  %s", fp.name)

    failed: list[tuple[Path, str, int]] = []  # (path, frame_id, exit_code)
    succeeded: list[tuple[Path, str, dict]] = []  # (path, frame_id, timing)
    total_colmap = 0.0
    total_train = 0.0
    start_time = time.time()

    # initial status file (v7 distributed monitoring)
    _write_worker_status(args.worker_status,
                         status="running",
                         current_frame="",
                         current_stage="starting",
                         total_frames=len(to_process),
                         completed_frames=0,
                         failed_frames=0,
                         elapsed_seconds=0.0)

    for i, (frame_path, fid) in enumerate(to_process, 1):
        logging.info(
            "=== [%d/%d] %s ===", i, len(to_process), frame_path.name,
        )

        # status: starting this frame
        _write_worker_status(args.worker_status,
                             status="running",
                             current_frame=frame_path.name,
                             current_stage="colmap",
                             total_frames=len(to_process),
                             completed_frames=len(succeeded),
                             failed_frames=len(failed),
                             elapsed_seconds=time.time() - start_time)

        code, timing = run_single(
            frame_path,
            fid,
            args.sub_dir,
            args.pipeline_extra_args,
            args.python_executable,
            force=args.force,
        )

        if code != 0:
            logging.error("Frame %s failed with code %d.", frame_path.name, code)
            failed.append((frame_path, fid, code))
            _write_worker_status(args.worker_status,
                                 status="running",
                                 current_frame=frame_path.name,
                                 current_stage="failed",
                                 total_frames=len(to_process),
                                 completed_frames=len(succeeded),
                                 failed_frames=len(failed),
                                 elapsed_seconds=time.time() - start_time)
            continue

        if timing:
            upsert_batch_timing(args.sub_dir, fid, timing)
            succeeded.append((frame_path, fid, timing))
            total_colmap += timing.get("colmap_seconds", 0.0)
            total_train += timing.get("train_seconds", 0.0)
            logging.info(
                "Frame %s completed: %.1fs (colmap: %.1fs, train: %.1fs)",
                fid,
                timing.get("total_seconds", 0),
                timing.get("colmap_seconds", 0),
                timing.get("train_seconds", 0),
            )
        else:
            # Completed but no timing file produced (should not normally happen)
            succeeded.append((frame_path, fid, {}))
            logging.info("Frame %s completed (no timing).", frame_path.name)

    # final status
    _write_worker_status(args.worker_status,
                         status="done",
                         current_frame="",
                         current_stage="done",
                         total_frames=len(to_process),
                         completed_frames=len(succeeded),
                         failed_frames=len(failed),
                         elapsed_seconds=time.time() - start_time)

    n_total = len(to_process)
    n_ok = len(succeeded)
    n_fail = len(failed)
    total_seconds = total_colmap + total_train

    logging.info(
        "Batch done. %d succeeded, %d failed%s.",
        n_ok,
        n_fail,
        f", {len(skipped)} skipped" if skipped else "",
    )
    if n_ok:
        logging.info(
            "Timing summary — total: %.1fs (%.1f min), colmap: %.1fs, train: %.1fs, avg/frame: %.1fs",
            total_seconds,
            total_seconds / 60,
            total_colmap,
            total_train,
            total_seconds / n_ok,
        )
        logging.info(
            "Timing saved to %s",
            _batch_timing_path(args.sub_dir),
        )
    if failed:
        logging.error("Failed frames:")
        for fp, fid, code in failed:
            logging.error("  %s (%s, code %d)", fp.name, fid, code)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
