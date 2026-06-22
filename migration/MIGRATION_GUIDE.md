# LiteGS Pipeline — 迁移部署指南

> 源主机 → 目标主机（Windows 11, RTX 5080 16GB）  
> 使用 uv 管理 Python 环境

---

## 源主机环境快照

| 项目 | 配置 |
|------|------|
| **OS** | Windows 11 Pro 10.0.22621 |
| **GPU** | NVIDIA GeForce RTX 5080 (16 GB, Blackwell sm_120) |
| **Driver** | 596.49 |
| **CUDA Toolkit** | 12.8 |
| **PyTorch** | 2.7.0+cu128 |
| **Python** | 3.10.20 |
| **COLMAP** | 3.12.3 with CUDA |
| **Build Tools** | VS 2022 Community + CMake 4.1.0 |

---

## 部署

**新机部署请按 `../README.md` 的「快速开始」操作：**

```powershell
# 1. 手动安装前置依赖（uv / CUDA 12.8 / VS 2022 C++ / CMake / COLMAP 3.12.3）
# 2. 一键部署
.\setup.ps1
```

详细踩坑记录见 [`../docs/MIGRATION_PITFALLS.md`](../docs/MIGRATION_PITFALLS.md)。

---

## 关键依赖版本

| 依赖 | 版本 | 来源 |
|------|------|------|
| Python | 3.10.x | uv (python-build-standalone) |
| PyTorch | 2.7.0+cu128 | pytorch.org (CUDA 12.8) |
| torchvision | 0.22.0 | pytorch.org |
| CUDA 扩展 | 本地编译 | `LiteGS/LiteGS/submodules/` |
| COLMAP | 3.12.3 CUDA | GitHub Releases |
| CUDA Toolkit | 12.8 | NVIDIA |
| MSVC | VS 2022 | Microsoft |
| CMake | 3.20+ | Kitware |
| uv | 最新版 | astral.sh |
