---
name: pipeline-colmap-version
description: COLMAP version constraint (must be 3.12.3), PATH setup, and calibration keypoint sync mechanism
metadata:
  type: project
---

# COLMAP 3.12.3 — Version Constraint & Keypoint Sync

## Version Lock
- **Must use COLMAP 3.12.3** (commit 74b2be9, 2025-07-16, with CUDA)
- COLMAP 3.8 is **incompatible**: different SIFT results, different DB format, different DLL layout
- Download: `https://github.com/colmap/colmap/releases/tag/3.12.3` → `COLMAP-3.12.3-windows-cuda.zip`
- Local path: `E:\work\26.7_SKNJ\LiteGSWin\COLMAP-3.12-windows-cuda`

## PATH
- COLMAP 3.12.3 DLLs are in `bin\` (unlike 3.8 which used `lib\`)
- Add to PATH: `E:\work\26.7_SKNJ\LiteGSWin\COLMAP-3.12-windows-cuda\bin`
- Ignored by `.gitignore` (COLMAP is external, downloaded separately)

## Calibration Keypoint Sync (Critical Pipeline Fix)

**Problem**: Calibration images and training images share filenames (001.jpg ~ NNN.jpg) but have different content → different SIFT keypoint counts. COLMAP's `point_triangulator` hard-checks `NumPoints2D()` equality → coredump with "Check failed (923 vs. 2207)".

**Solution** (implemented in two scripts):

1. `utils/prepare_calibration.py` → `strip_calibration_keypoints()`: After `write_baseline_sparse()`, rewrites `sparse/images.txt` with placeholder keypoints (`0 0 -1` per image). Must be non-empty to keep the parser's alternating state machine working.

2. `utils/prepare_colmap_dataset.py` → `sync_calibration_keypoints()`: After feature extraction creates the training DB, reads actual keypoint counts and rewrites calibration `images.txt` with matching placeholders. Called before `point_triangulator` (calibration path only).

**Why**: Without this, `point_triangulator` crashes. The source machine may have had matching SIFT counts or a COLMAP build without this check. Our fix makes the pipeline robust regardless.

## Calibration Auto-Detect & Mapper Fallback

When no calibration data exists, `prepare_colmap_dataset.py` auto-detects and runs COLMAP `mapper` (full SfM) instead of `point_triangulator`. Detection: ① explicit `--calib_sub_dir`/`--calib_sparse_path` → calibration path ② `--force_no_calib` → mapper ③ auto-detect `data/calibration/<model_sub_dir>/sparse/`. Mapper skips calibration-specific steps (`sync_calibration_keypoints`, `normalize_database_to_calibration`).

**Known bug**: mapper `--output_path` writes to `distorted/sparse/0/0/` (extra `0/`), causing `image_undistorter` crash. Pending fix: change output_path from `distorted/sparse/0` to `distorted/sparse`.

**How to apply:** No manual action needed — both scripts handle this automatically after code changes committed.
