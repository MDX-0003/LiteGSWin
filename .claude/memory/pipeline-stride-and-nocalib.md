---
name: pipeline-stride-and-nocalib
description: Frame stride sampling and calibration-less pipeline design decisions, raw_imgs/ lifecycle
metadata:
  type: project
---

# Frame Stride & Calibration-Less Pipeline

## Design Decisions (see docs/adr/0001-*.md for full record)

### raw_imgs/ — Immutable Image Source
- First run: images move from frame root → `raw_imgs/` (one-time init).
- Every subsequent run: copy from `raw_imgs/` → `input/` with stride filter applied at copy time.
- `raw_imgs/` is **never modified** after initial population.
- `input/` is **fully cleared** each run (files and subdirs deleted, then rebuilt).
- Rationale: prevents destructive data loss, enables re-running with different stride values.

### Stride Filter (--frame_stride N)
- Defined in `run_LiteGS_pipeline.py` (not batch_run.py). Batch forwards via `pipeline_extra_args`.
- Filtering: `raw_images[0], raw_images[stride], raw_images[2*stride], ...` (sorted by filename).
- Default `--frame_stride_min_images` = 3 (permissive, originally 10, lowered after real-world 8→3 scenario).
- On copy: logs "Frame stride 3: 114 image(s) in raw_imgs/ → 38 image(s) copied to input/."

### Calibration Auto-Detect
- `prepare_colmap_dataset.py` main() branches:
  - `--force_no_calib` → mapper path always
  - `--calib_sub_dir` / `--calib_sparse_path` → point_triangulator path
  - Else auto-detect: check `data/calibration/<model_sub_dir>/sparse/` for cameras.txt + images.txt
- Mapper path skips: `normalize_database_to_calibration()`, `sync_calibration_keypoints()`

### Script Rename
- `triangulate_from_calibration.py` → `prepare_colmap_dataset.py` (9 files, 14 references)
- `--skip_triangulation` → `--skip_colmap` (run_LiteGS_pipeline.py)

### Training Iterations
- `--iterations` (default 30000) is a pipeline-level param in `run_LiteGS_pipeline.py`

### --force Forwarding Fix
- `batch_run.py --force` now appends `--force` to pipeline command in `run_single()`.
- Previously batch consumed the flag and pipeline never received it.

## Known Issue
COLMAP mapper `--output_path` → `distorted/sparse/0/0/` instead of `distorted/sparse/0/`, causing
`image_undistorter` to fail. Fix: change `run_mapper()` output_path from `distorted/sparse/0` to `distorted/sparse`.

**Why:** These decisions emerged from a grill-with-docs+diagnose design session. raw_imgs/ lifecycle was revised mid-session after the first destructive approach failed in practice.

**How to apply:** See [[pipeline-data-structure]] for directory layout, [[pipeline-colmap-version]] for COLMAP details.
