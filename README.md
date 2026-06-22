# LiteGS Pipeline — Windows 部署与运行指南

> 3D Gaussian Splatting 训练管道，基于 LiteGS + COLMAP  
> 目标硬件：RTX 5080 (Blackwell sm_120), CUDA 12.8, Windows 11

---

## 快速开始（新机器）

### 前置依赖（手动安装）

| 工具 | 下载 | 验证 |
|------|------|------|
| **uv** | `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"` | `uv --version` |
| **CUDA 12.8** | [NVIDIA 下载](https://developer.nvidia.com/cuda-12-8-0-download-archive) | `nvcc --version` |
| **VS 2022** | [Visual Studio](https://visualstudio.microsoft.com/downloads/) 勾选 "Desktop Development with C++" | `cl` 能运行 |
| **CMake** | [cmake.org](https://cmake.org/download/) 勾选 "Add to PATH" | `cmake --version` |
| **COLMAP 3.12.3 CUDA** | [GitHub Releases](https://github.com/colmap/colmap/releases/tag/3.12.3) 解压后将 `bin\` 加入 PATH | `colmap --help` 显示 "with CUDA" |

### 一键部署

```powershell
# 在仓库根目录执行
.\setup.ps1
```

脚本自动完成：Python 3.10 安装 → 虚拟环境 → PyTorch 2.7.0+cu128 → 依赖 → CUDA 扩展编译

### 准备数据

```
data/
├── calibration/<sub_dir>/input/          ← 标定相机图片
├── calibration/<sub_dir>/sparse/          ← 标定结果（第一次标定后生成）
└── <sub_dir>/<YYYY-MM-DD-HHmmss>/input/   ← 训练帧图片（每帧在一个时间戳目录下）
```

> **测试数据：** 仓库自带 `data/calibration/0618/` 含 30 张标定图和预生成的标定模型。训练图片需自行放入 `data/0618/<timestamp>/input/`。

### 运行管道

```powershell
# 1. 标定相机（只需做一次，数据变化后重做）
uv run python utils\prepare_calibration.py --sub_dir 0618

# 2. 批量训练
uv run python batch_run.py --sub_dir 0618

# 单帧训练
uv run python run_LiteGS_pipeline.py -s data\0618\2026-06-18-195909
```

---

## 常用命令

```powershell
# 查看有哪些帧
uv run python batch_run.py --sub_dir 0618 --dry_run

# 跳过三角化（已有 COLMAP 结果时）
uv run python run_LiteGS_pipeline.py -s data\0618\2026-06-18-195909 --skip_triangulation

# 指定 COLMAP 路径（不在 PATH 时）
uv run python batch_run.py --sub_dir 0618 -- --colmap_executable D:\colmap\bin\colmap.exe

# 更多参数
uv run python run_LiteGS_pipeline.py --help
```

---

## 文件说明

| 路径 | 用途 |
|------|------|
| `batch_run.py` | 批量训练入口，自动发现 data 下所有帧 |
| `run_LiteGS_pipeline.py` | 单帧完整管道：三角化 → 训练 → 输出 PLY |
| `utils/prepare_calibration.py` | 标定管道：SIFT → 匹配 → SfM → 输出相机模型 |
| `utils/triangulate_from_calibration.py` | 三角化：用标定相机对训练帧做 3D 重建 |
| `LiteGS/example_train.py` | LiteGS 训练入口 |
| `LiteGS/LiteGS/submodules/` | 3 个 CUDA 扩展源码（simple-knn / fused-ssim / gaussian_raster） |
| `setup.ps1` | 一键环境部署 |
| `migration/requirements_LiteGS.txt` | pip 依赖清单 |
| `docs/MIGRATION_PITFALLS.md` | 14 个已知迁移坑及解决方案 |

---

## 故障排查

| 现象 | 解决方案 |
|------|---------|
| `module 'litegs_fused' has no attribute` | 重新编译：`uv pip install -e LiteGS\LiteGS\submodules\gaussian_raster --no-build-isolation` |
| `[WinError 2] 系统找不到指定的文件` 编译时 | 确保 `cl.exe` 在 PATH：`$env:PATH = "E:\...MSVC\...\Hostx64\x64;$env:PATH"` |
| `ImportError: DLL load failed` | CUDA DLL 不在 PATH：`$env:PATH = "D:\...CUDA\v12.8\bin;$env:PATH"` |
| COLMAP 报 SQLite / 关键点数不匹配 | 参见 [MIGRATION_PITFALLS.md](docs/MIGRATION_PITFALLS.md) 坑 3、坑 12 |
| 其他问题 | 阅读 [docs/MIGRATION_PITFALLS.md](docs/MIGRATION_PITFALLS.md) |
