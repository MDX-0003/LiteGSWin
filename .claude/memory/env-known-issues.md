---
name: env-known-issues
description: Quick-reference for common errors and their fixes without re-debugging
metadata:
  type: project
---

# Known Issues Quick-Reference

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| `ModuleNotFoundError: No module named 'simple_knn'` | Missing `__init__.py` or editable finder bug | Create `__init__.py` in `simple_knn/`, or verify editable install |
| `dir(litegs_fused)` returns `[]` | Editable finder can't discover `.pyd` exports | Copy `.pyd` to `site-packages/`, uninstall editable version |
| `ImportError: DLL load failed` for `simple_knn._C` | `cudart64_12.dll` not on PATH | Import `torch` first, or add CUDA bin to PATH |
| `[WinError 2] 系统找不到指定的文件` during `uv pip install -e .` | MSVC not on PATH | `$env:PATH = "E:\...MSVC\...\Hostx64\x64;$env:PATH"` |
| `Error checking compiler version for cl: 'cp1' codec` | Chinese MSVC output encoding | **Warning only** — compilation still works |
| `nvcc fatal: Could not set up environment for MSVC 14.44` | CUDA 12.8 doesn't support MSVC 14.44 | Use MSVC 14.38.33130 instead |
| `DISTUTILS_USE_SDK` error | VS Developer PowerShell pre-activates VC env | Use **normal PowerShell**, don't use Developer Shell |
| COLMAP `SQLite error database.cc:1063` | Old COLMAP 3.8 database format | Delete `database.db` and regenerate with 3.12.3 |
| `Check failed: NumPoints2D() (923 vs. 2207)` | Calibration/training keypoint count mismatch | Auto-fixed by `sync_calibration_keypoints()` in prepare_colmap_dataset.py |
| `Database images do not match calibration` (only even images missing) | Empty keypoint lines break parser state machine | Use non-empty placeholder keypoints: `0 0 -1` |
| `batch_run.py --force` doesn't force re-run | `--force` not forwarded to `run_LiteGS_pipeline.py` | Use `-- --force` after batch args |
| `uv python utils\script.py` fails | `uv python` manages Python versions, doesn't run scripts | Use `uv run python utils\script.py` |
| COLMAP `STATUS_DLL_NOT_FOUND` (0xC0000135) | COLMAP DLLs not on PATH | Add COLMAP `bin\` to PATH |
| `nvcc warning: support for architectures prior to sm_75 will be removed` | Harmless — nvcc deprecation notice | Ignore or add `-Wno-deprecated-gpu-targets` |

**Why:** All of these were encountered and resolved during the initial migration. This reference prevents re-debugging the same issues.

**How to apply:** Search this table by symptom keyword. For detailed explanations see `docs/MIGRATION_PITFALLS.md` and linked memory files.
