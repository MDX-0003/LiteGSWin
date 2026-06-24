---
name: pipeline-data-structure
description: Data directory layout, file roles, and what is git-tracked vs generated
metadata:
  type: project
---

# Data Directory Structure & Git Tracking

## Directory Layout
```
data/
├── calibration/<sub_dir>/         ← Calibration (e.g. 0618)
│   ├── input/                     ← Calibration images (git-tracked)
│   ├── sparse/                    ← Calibration model: cameras.txt + images.txt (git-tracked)
│   ├── sparse_bin/                ← Binary SfM output (git-ignored, generated)
│   └── distorted/                 ← COLMAP intermediates (git-ignored)
└── <sub_dir>/<YYYY-MM-DD-HHmmss>/ ← Per-frame training data
    ├── raw_imgs/                  ← Original images (git-tracked, one-time init, never modified)
    ├── input/                     ← Working images: cleared+rebuilt each run from raw_imgs/ (git-tracked)
    ├── images/                    ← Undistorted images (git-ignored, COLMAP output)
    ├── distorted/                 ← COLMAP intermediates + database.db (git-ignored)
    ├── sparse/                    ← SfM output: cameras.bin, images.bin, points3D.ply (git-ignored)
    └── stereo/                    ← MVS output (git-ignored)
```

## Git Tracking Rules (from .gitignore)
- **Tracked**: `data/**/input/*.jpg`, `data/calibration/*/sparse/`
- **Ignored**: `*.db`, `distorted/`, `images/`, `sparse_bin/`, `stereo/`, `*.ply`, `*.bak`
- Model outputs: `results/` entirely ignored, `*.ply` at any level ignored

## Test Data Included
- 30 calibration images at `data/calibration/0618/input/` (~6 MB total)
- Pre-built calibration model at `data/calibration/0618/sparse/` (cameras.txt, images.txt)
- Training frame directory at `data/0618/2026-06-18-195909/input/` (empty — user adds images)

## Pipeline Flow
```
prepare_calibration.py → calibration sparse (cameras.txt + images.txt)
                              ↓
prepare_colmap_dataset.py → training sparse (cameras.bin + images.bin + points3D.ply)
    ├── has calib → point_triangulator (camera intrinsics from calibration)
    └── no calib  → mapper (full SfM from scratch, auto-detect or --force_no_calib)
                              ↓
example_train.py → results/<sub_dir>/<frame_id>/point_cloud/finish/point_cloud.ply
                              ↓
                   results/<sub_dir>/<sub_dir>-<frame_id>.ply  (flat copy)
```

### Frame Stride (--frame_stride N)
- Stride filter applied during copy from raw_imgs/ → input/ each run
- raw_imgs/ is populated once from frame root images, then read-only forever
- input/ is fully cleared and rebuilt each pipeline invocation
- Logs: "Frame stride 3: 114 image(s) in raw_imgs/ → 38 image(s) copied to input/."

**Why:** Calibration is reused across all training frames with the same camera setup. Each training frame gets its own timestamp directory. The calibration sparse model is the only COLMAP output tracked in git — everything else is regenerated.

**How to apply:** Place images in `input/` directories, then run `uv run python batch_run.py --sub_dir <sub_dir>`.
