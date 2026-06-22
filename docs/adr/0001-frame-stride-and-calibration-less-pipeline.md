# Frame stride sampling and calibration-less pipeline support

We decided to add two capabilities to the pipeline: (1) `--frame_stride N` to sample every Nth image from input before COLMAP, and (2) automatic calibration-less mode where COLMAP mapper replaces point_triangulator when no calibration data exists.

**Why**: Users often capture many frames and want to train on a sparse subset to reduce computation. Users also need to process scenes without prior camera calibration.

## Considered Options

**Stride insertion point**: Before COLMAP (filter in `ensure_input_images()`) vs after COLMAP but before training. Chose before COLMAP — saves SIFT+matching time which is O(n²), and the code change is a single insertion point.

**Calibration-less architecture**: Fork inside `prepare_colmap_dataset.py` (one script, two code paths) vs separate utility script. Chose fork — shared logic (feature_extractor, exhaustive_matcher, image_undistorter) avoids duplication, and the pipeline orchestration stays simple.

**No-calib detection**: Explicit `--no_calib` flag vs auto-detect by checking `data/calibration/<sub_dir>/sparse/`. Chose auto-detect with `--force_no_calib` override — batch runs naturally have homogeneous calibration state per sub_dir, and zero-config is better UX.

## Consequences

- `triangulate_from_calibration.py` renamed to `prepare_colmap_dataset.py` (9 files, 12 references updated)
- `--skip_triangulation` renamed to `--skip_colmap` in run_LiteGS_pipeline.py
- Stride filtering happens after `move_root_images_to_input()` but before COLMAP feature extraction
- Non-matching images are deleted; at least 1 image always survives
- Minimum image count threshold defaults to 10, configurable via `--frame_stride_min_images`
