---
name: env-cuda-extension-build
description: Per-extension compilation quirks for simple-knn, fused-ssim, litegs-fused
metadata:
  type: project
---

# CUDA Extension Build Quirks

## Common Prerequisites
```powershell
uv pip install setuptools wheel  # must be in venv before building
$env:CUDA_ARCHITECTURES = "120"  # RTX 5080 = Blackwell sm_120
```

## simple-knn
- Uses `CUDAExtension(name="simple_knn._C")` — import as `simple_knn._C`
- **Requires `__init__.py`** in `simple_knn/` dir for editable install to work
- DLL dependency: needs `cudart64_12.dll` — resolved by `import torch` before `import simple_knn._C`
- Path: `LiteGS\LiteGS\submodules\simple-knn`

## fused-ssim (LiteGS version)
- Uses custom `CustomBuildExtension` with GPU arch auto-detection
- **Must use LiteGS version** (path: `LiteGS/LiteGS/submodules/fused_ssim/`), NOT fast_splat version
- LiteGS version has `fused_l1_ssim_loss` — trainer.py depends on this
- Has CUDA/MPS/XPU backends; auto-selects CUDA when `torch.cuda.is_available()`
- Path: `LiteGS\LiteGS\submodules\fused_ssim`

## litegs-fused (gaussian_raster)
- **Editable finder bug**: after `uv pip install -e .`, `dir(litegs_fused)` returns empty
- **Workaround**: copy `.pyd` directly to `site-packages` and uninstall editable version
  ```powershell
  Copy-Item LiteGS\LiteGS\submodules\gaussian_raster\litegs_fused.cp310-win_amd64.pyd .venv\Lib\site-packages\
  uv pip uninstall litegs-fused
  ```
- Source files: `binning.cu`, `compact.cu`, `raster.cu`, `transform.cu`, `ext_cuda.cpp`
- Exports: `createTransformMatrix_forward/backward`, `mvp_transform_forward/backward`, rasterization functions
- Path: `LiteGS\LiteGS\submodules\gaussian_raster`

**Why:** Each extension has different setup.py structure. simple-knn and litegs-fused use standard `BuildExtension`; fused-ssim has custom arch detection. The editable finder bug in litegs-fused is a setuptools/uv compatibility issue.

**How to apply:** After running `setup.ps1`, verify with:
```powershell
.venv\Scripts\python.exe -c "import torch; import simple_knn._C; import litegs_fused; import fused_ssim; print('All OK')"
```
