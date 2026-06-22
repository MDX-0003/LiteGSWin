# LiteGSWin

Windows 部署的 LiteGS 3D Gaussian Splatting 训练管线。给定一组场景照片，通过 COLMAP 重建稀疏点云，训练出可渲染的高质量 3D 高斯表示。

## Language

**Frame**:
一个时间点采集的一组训练图片，存储在 `data/<sub_dir>/<YYYY-MM-DD-HHmmss>/input/` 目录下。
_Avoid_: Scene, sample, capture

**Sub Dir**:
`data/` 下的二级目录，代表一个采集批次（如 `0613`）。也是校准数据路径 `data/calibration/<sub_dir>/` 和输出路径 `results/<sub_dir>/` 的命名依据。
_Avoid_: Dataset, group, session

**Calibration**:
使用标定板图片通过 COLMAP SfM 提前计算出的相机内参和外参位姿，存储为 sparse model（cameras.txt + images.txt）。训练帧可复用这些内参，仅做三角化。
_Avoid_: Calib, reference

**Stride**:
从输入图片中按固定间隔采样的参数。`--frame_stride 3` 表示每 3 张保留第 1 张。过滤发生在从 `raw_imgs/` 拷贝到 `input/` 时，`raw_imgs/` 始终保持完整原始数据不变。
_Avoid_: Sample rate, downsample, skip

**raw_imgs**:
Frame 目录下存放原始图片的只读目录。首次运行时由 `ensure_raw_images()` 从 frame 根目录移入图片创建，后续运行只从中拷贝到 `input/`，绝不修改其内容。
_Avoid_: Original images, source images

**Mapper**:
COLMAP 的完整 SfM 重建模式，同时求解相机内参、外参位姿和 3D 点云。当没有 calibration 数据时使用，替代 `point_triangulator`。
_Avoid_: Full SfM, reconstruction

**Point Triangulator**:
COLMAP 的三角化模式，在已知相机内外参的前提下，仅求解 3D 点云坐标。需要 calibration 数据作为输入。
_Avoid_: Triangulation
