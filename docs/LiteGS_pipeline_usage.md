# LiteGS 管线使用指南

从一组多视角图片到 3D 高斯泼溅（3DGS）ply 模型。

---

## 前置条件

每次使用前，请确保以下条件已满足：

1. **前置条件已由 `setup.ps1` 完成。** 每次新终端直接使用 `uv run python`。

---

## 快速开始

### 第一步：标定相机（仅首次，或相机变更后）

将标定用的多视角图片放入 `./data/calibration/<sub_dir>/` 目录下，然后执行：

```powershell
uv run pythonutils/prepare_calibration.py --sub_dir 0613
```

标定参数会保存在 `./data/calibration/0613/sparse/`，后续所有帧的训练都会复用这一组标定结果。**这一步只需要做一次**。

### 第二步：训练模型

将某一帧的多视角图片放入 `./data/<sub_dir>/<timestamp>/input/` 目录下，然后执行：

```powershell
uv run pythonrun_LiteGS_pipeline.py -s ./data/0613/2026-06-13-234829
uv run pythonrun_LiteGS_pipeline.py -s ./data/0613/2026-06-13-234712
```

脚本会**自动**完成以下工作：
1. COLMAP 特征提取 + 匹配
2. 基于标定参数三角化 + 去畸变
3. LiteGS 训练
4. 输出整理

**输出文件（均在 `./results/<sub_dir>/` 下）：**

| 文件 | 路径 | 说明 |
|------|------|------|
| 模型 | `./results/0613/0613-234829.ply` | 训练完成的 3D 高斯泼溅模型 |
| 相机参数 | `./results/0613/cameras.json` | 相机内外参（首次训练自动生成，同一标定会话复用） |

### 第三步：批量训练（多帧串行）

如果 `data/0613/` 下已放好多个帧目录，可以用一条命令串行处理全部：

```powershell
uv run pythonbatch_run.py --sub_dir 0613
```

常用选项：

| 选项 | 说明 |
|------|------|
| `--start_from 2026-06-13-234712` | 从指定帧开始（跳过之前的），方便断点续跑 |
| `--force` | 强制重跑已有输出的帧 |
| `--dry_run` | 只列出会处理的帧，不实际执行 |
| `-r 4 --target_primitives 500000` | 透传训练参数给每个帧（和单帧用法一致） |

示例：

```powershell
# 预演：看看哪些帧会被处理
uv run pythonbatch_run.py --sub_dir 0613 --dry_run

# 从断点续跑
uv run pythonbatch_run.py --sub_dir 0613 --start_from 2026-06-13-234712

# 强制全部重跑，带自定义训练参数
uv run pythonbatch_run.py --sub_dir 0613 --force -r 4 --target_primitives 500000
```

前面的内容已经足以完成大部分需求，结果（ply+json）均在./results/<sub_dir>下，bin在./data/calibration/<sub_dir>

### 自定义训练参数（单帧）

```powershell
uv run pythonrun_LiteGS_pipeline.py -s ./data/0613/2026-06-13-234829 -r 4 --target_primitives 500000
```

常用可选参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-r` / `--resolution` | `2` | 图片下采样倍率 |
| `--target_primitives` | `300000` | 目标高斯球数量 |
| `--iterations` | LiteGS 默认 | 训练迭代次数（通过 `--iterations 20000` 追加） |

---

## 参数参考

### `run_LiteGS_pipeline.py` 全部参数

| 参数 | 必须 | 默认值 | 说明 |
|------|------|--------|------|
| `-s` / `--source_path` | **是** | — | 训练帧数据根目录，内含 `input/` 子目录 |
| `--model_sub_dir` | 否 | 自动从路径提取 | 标定子目录名，同时用于 `./results/` 下的输出目录 |
| `--frame_id` | 否 | 自动从路径提取 | 帧号（HHmmss），从时间戳目录名末尾截取 |
| `--group_id` | 否 | — | 已废弃，不再用于输出路径 |
| `-r` / `--resolution` | 否 | `2` | LiteGS 图片分辨率参数 |
| `--target_primitives` | 否 | `300000` | LiteGS 目标高斯球数量 |
| `--images` | 否 | `images` | LiteGS 读取图片的子目录名 |
| `--model_path` | 否 | `./results/<model_sub_dir>` | 覆盖 LiteGS 输出目录 |
| `--cameras_json_path` | 否 | `./results/<model_sub_dir>/cameras.json` | 覆盖 cameras.json 输出路径 |
| `--calib_sparse_path` | 否 | 自动从 `--model_sub_dir` 推导 | 直接指定标定 sparse 目录 |
| `--calibration_root` | 否 | `./data/calibration` | 标定数据根目录 |
| `--colmap_executable` | 否 | `colmap` | COLMAP 可执行文件路径 |
| `--python_executable` | 否 | 当前 Python | 运行子脚本的 Python 解释器 |
| `--no_gpu` | 否 | 关闭 | 禁用 COLMAP GPU 加速 |
| `--skip_matching` | 否 | 关闭 | 跳过 COLMAP 特征提取和匹配 |
| `--skip_colmap` | 否 | 关闭 | 跳过 COLMAP 步骤，直接用已有 COLMAP 输出训练 |
| `--frame_stride` | 否 | 1 | 每 N 张输入图片保留 1 张，减少训练数据量 |
| `--frame_stride_min_images` | 否 | 10 | stride 过滤后最少保留的图片数 |
| `--force_no_calib` | 否 | 关闭 | 强制 COLMAP mapper 模式（即使有标定数据） |

### `prepare_calibration.py` 参数

| 参数 | 必须 | 默认值 | 说明 |
|------|------|--------|------|
| `--sub_dir` | **是** | — | 标定数据子目录，对应 `./data/calibration/<sub_dir>/` |
| `--no_gpu` | 否 | 关闭 | 禁用 COLMAP GPU 加速 |
| `--colmap_executable` | 否 | `colmap` | COLMAP 可执行文件路径 |

---

## 目录结构约定

```
DanceSmashTest/
├── data/
│   ├── calibration/
│   │   └── <sub_dir>/               ← 标定图片（如 0613）
│   │       ├── input/               ← 原始标定图片（脚本自动移入）
│   │       └── sparse/              ← 标定输出（cameras.txt, images.txt）
│   └── <sub_dir>/                   ← 训练数据（如 0613）
│       └── YYYY-MM-DD-HHmmss/       ← 单帧目录（如 2026-06-13-234829）
│           └── input/               ← 原始训练图片
├── results/
│   └── <sub_dir>/                   ← 训练结果
│       ├── <sub_dir>-<frame_id>.ply ← 最终模型（方便直接取用）
│       ├── cameras.json             ← 相机内外参（同一标定会话复用）
│       └── <frame_id>/              ← 单帧训练产物
│           └── point_cloud/finish/  ← LiteGS 原始输出
└── run_LiteGS_pipeline.py
```

---

## 高级用法

### 跳过三角化（已有 COLMAP 输出）

如果 `sparse/0/` 和 `images/` 已经存在：

```powershell
uv run python run_LiteGS_pipeline.py -s ./data/0613/2026-06-13-234829 --skip_colmap
```

### 跳过特征匹配（复用已有 database.db）

不推荐，除非你确定特征匹配结果仍然有效：

```powershell
uv run pythonrun_LiteGS_pipeline.py -s ./data/0613/2026-06-13-234829 --skip_matching
```

### 手动指定标定路径

```powershell
uv run pythonrun_LiteGS_pipeline.py -s ./data/0613/2026-06-13-234829 --calib_sparse_path ./data/calibration/0613/sparse_calib/0
```

### 手动指定所有参数

当自动推导失败（如非标准目录结构），可手动指定：

```powershell
uv run pythonrun_LiteGS_pipeline.py -s /custom/path/scene --model_sub_dir 0613 --frame_id 234829
```

### 只生成训练数据，不训练

```powershell
uv run python utils/prepare_colmap_dataset.py -s ./data/0608/without_sword/2026-06-08-105443 --calib_sub_dir 0608
```

---

## 常见问题

**Q: 报错 "Cannot auto-detect --frame_id"？**

A: 你的 source_path 最后一段不符合 `YYYY-MM-DD-HHmmss` 格式。请手动指定 `--frame_id`。

**Q: 报错 "Cannot auto-detect --model_sub_dir"？**

A: 你的路径中没有 `data/` 目录。请手动指定 `--model_sub_dir`。

**Q: cameras.json 是什么？**

A: 包含每张图片的相机内外参（位置、旋转、焦距、图片尺寸），是使用 ply 模型进行渲染的必需文件。格式与 3D Gaussian Splatting 兼容。

**Q: 训练失败但 COLMAP 步骤已完成？**

A: 下次运行可以加 `--skip_colmap` 跳过 COLMAP 步骤，直接从训练开始。
