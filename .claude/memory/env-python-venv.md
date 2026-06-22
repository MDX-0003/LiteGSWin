---
name: env-python-venv
description: Python 3.10.20 venv managed by uv, key dependencies and setup flow
metadata:
  type: project
---

# Python Environment (uv-managed venv)

## Setup
```powershell
uv python install 3.10         # Python 3.10.20 from python-build-standalone
uv venv --python 3.10 .venv    # Creates .venv/ at repo root
```

## Key Dependencies
- **PyTorch**: 2.7.0+cu128 (CUDA 12.8) from `https://download.pytorch.org/whl/cu128`
  - torchvision 0.22.0, torchaudio 2.7.0
- **Core**: numpy==2.2.6, opencv-python==4.13.0.92, pillow==12.2.0
- **Gaussian Splatting**: plyfile==1.1.4, torchmetrics==1.9.0
- **Utilities**: tqdm, matplotlib, colorama, filelock, fsspec, jinja2, mpmath, networkx, sympy, lightning-utilities
- **Build**: setuptools, wheel
- Full list: `migration/requirements_LiteGS.txt`

## Usage
- Always `uv run python <script>` (auto-activates venv)
- Or `.venv\Scripts\activate` then `python <script>` directly
- **No conda needed** — this project uses uv exclusively

## uvrpip Caveats
- `uv pip install -e . --no-build-isolation` required for CUDA extensions
- Cross-filesystem hardlink warning is harmless (cache on different drive)
- Fix: `$env:UV_LINK_MODE = "copy"` or ignore

**Why:** uv is faster than conda/pip for dependency resolution. Python 3.10 is required by LiteGS. PyTorch 2.7.0+cu128 matches CUDA 12.8.

**How to apply:** See [[env-cuda-toolchain]] and `setup.ps1`.
