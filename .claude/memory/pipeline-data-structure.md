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
    ├── input/                     ← Training images (git-tracked)
    ├── images/                    ← Undistorted images (git-ignored, generated)
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
triangulate_from_calibration.py → training sparse (cameras.bin + images.bin + points3D.ply)
                              ↓
example_train.py → results/<sub_dir>/<frame_id>/point_cloud/finish/point_cloud.ply
                              ↓
                   results/<sub_dir>/<sub_dir>-<frame_id>.ply  (flat copy)
```

**Why:** Calibration is reused across all training frames with the same camera setup. Each training frame gets its own timestamp directory. The calibration sparse model is the only COLMAP output tracked in git — everything else is regenerated.

**How to apply:** Place images in `input/` directories, then run `uv run python batch_run.py --sub_dir <sub_dir>`.
