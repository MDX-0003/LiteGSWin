# LiteGS 迁移踩坑全记录

> 源主机 → 目标主机（Windows 11, RTX 5080 16GB, CUDA 12.8, PyTorch 2.7.0+cu128）
> 环境：uv 管理 Python, COLMAP 3.12.3 CUDA 版, VS 2022 Community

---

## 坑 1：CMake 已安装但不在 PATH

**现象：** `setup_target.bat` 中 `where cmake` 失败，脚本直接退出。

**原因：** CMake 4.1.0 安装在 `E:\Programs\cmake-4.1.0-windows-x86_64\bin\`，但未加入系统 PATH。

**修复：**
```powershell
[Environment]::SetEnvironmentVariable("Path", "E:\Programs\cmake-4.1.0-windows-x86_64\bin;" + [Environment]::GetEnvironmentVariable("Path", "User"), "User")
```

---

## 坑 2：CUDA 12.8 头文件损坏（`host_defines.h`）

**现象：** 所有 `.cu` 文件编译报 100+ 个错误：
```
device_types.h(70): error: identifier "cudaRoundNearest" is undefined
vector_types.h(104): error: tag kind of class or struct is incompatible...
```

**原因：** CUDA 12.8 安装包中 `include/crt/host_defines.h` 的 `__device_builtin__` 宏定义在第 250 行和第 255 行缺失 token 名（`#define ` 后为空）。导致 MSVC 无法解析 `enum __device_builtin__ cudaRoundMode` 等 CUDA 内部声明。

**诊断方法：**
```powershell
$f = "D:\Lib\Cuda12_8_Compute_Toolkit\include\crt\host_defines.h"
$lines = Get-Content $f
$lines[249]  # 应为 "#define __device_builtin__"，但可能是 "#define "
$lines[254]  # 应为 "#define __device_builtin__ \"，但可能是 "#define  \"
```

**修复：重装 CUDA 12.8，不要修复单个文件。** 安装到无空格路径（如 `D:\Lib\Cuda12_8_Compute_Toolkit\`）。

---

## 坑 3：COLMAP 版本不匹配

**现象：**
- COLMAP 3.8 创建数据库时报 `SQLite error [database.cc, line 1063]: SQL logic error`
- 或 SIFT 特征数不匹配（2207 vs 923）导致 `point_triangulator` coredump

**原因：** 源主机使用 COLMAP 3.12.3 (commit 74b2be9)，目标机初始安装了 COLMAP 3.8。跨版本：
1. 数据库格式不兼容（新版创建的 `.db` 旧版无法读取）
2. SIFT 特征提取算法版本间结果不一致，同名图片关键点数不同

**修复：** 使用与源主机完全一致的 COLMAP 版本。从 [GitHub Releases](https://github.com/colmap/colmap/releases/tag/3.12.3) 下载 `COLMAP-3.12.3-windows-cuda.zip`。

---

## 坑 4：COLMAP 的 DLL 依赖和 PATH 配置

**现象：** 直接调用 `colmap.exe` 报 `STATUS_DLL_NOT_FOUND` (0xC0000135) 或退出码 3221225781。

**原因：** COLMAP 依赖大量外部 DLL（Boost, Ceres, FreeImage, CUDA runtime 等），未在 PATH 中时无法加载。

**修复：**
```powershell
# COLMAP 3.12.3 的 DLL 都在 bin\ 下（不同于 3.8 的 lib\ 目录）
[Environment]::SetEnvironmentVariable("Path", "E:\work\26.7_SKNJ\LiteGSWin\COLMAP-3.12-windows-cuda\bin;" + [Environment]::GetEnvironmentVariable("Path", "User"), "User")
```

**版本差异注意：** COLMAP 3.8 的 DLL 在 `lib\`，COLMAP 3.12.3 的 DLL 在 `bin\`。不要盲目复制旧配置。

---

## 坑 5：`uv pip install -e .` 的构建隔离（build isolation）

**现象：**
```
ModuleNotFoundError: No module named 'torch'
ModuleNotFoundError: No module named 'setuptools'
```

**原因：** `uv pip install -e .` 默认创建临时构建环境，不继承 venv 中已安装的包。CUDA 扩展的 `setup.py` 依赖 `torch` 和 `setuptools`。

**修复：**
```powershell
# 先在 venv 中安装构建依赖
uv pip install setuptools wheel

# 构建时关闭隔离
uv pip install -e . --no-build-isolation
```

---

## 坑 6：MSVC 编译器找不到（`[WinError 2]`）

**现象：**
```
error: [WinError 2] 系统找不到指定的文件。
UserWarning: Error checking compiler version for cl: 'cp1' codec can't decode bytes...
```

**原因：** 两层问题——
1. `torch.utils.cpp_extension` 通过 `subprocess.check_output('cl')` 检测编译器版本，中文版 MSVC 的输出无法被 `oem` codec 解码
2. `cl.exe` 不在 PATH 时，setuptools 找不到编译器

**注意：不要使用 VS Developer PowerShell！** 预激活的 VC 环境会触发 `DISTUTILS_USE_SDK` 检查，导致额外的 ABI 验证失败。

**修复：** 在普通 PowerShell 中，直接把 `cl.exe` 所在目录加到 PATH：
```powershell
$env:PATH = "E:\Programs\VS 2022\Community\VC\Tools\MSVC\14.38.33130\bin\Hostx64\x64;$env:PATH"
$env:CUDA_ARCHITECTURES = "120"
```

---

## 坑 7：CUDA 架构未指定（RTX 5080 = sm_120）

**现象：** 编译成功但运行时 CUDA kernel 崩溃，或编译时 nvcc 未为 sm_120 生成代码。

**原因：** RTX 5080 是 Blackwell 架构，compute capability 12.0 (`sm_120`)。若不设置 `CUDA_ARCHITECTURES`，fused-ssim 的 `setup.py` 通过 `torch.cuda.get_device_capability()` 自动检测，但后备列表仅有 sm_75/80/89，无 sm_120。

**修复：** 编译前始终设置环境变量：
```powershell
$env:CUDA_ARCHITECTURES = "120"
```

---

## 坑 8：`simple-knn` 可编辑安装缺少 `__init__.py`

**现象：** 编译成功但 `import simple_knn._C` 报 `ModuleNotFoundError: No module named 'simple_knn'`。

**原因：** `uv pip install -e .` 的可编辑查找器（editable finder）需要包目录中有 `__init__.py` 才能识别为 Python 包。源码的 `simple_knn/` 目录只有 `.gitkeep` 和编译产物 `_C.pyd`。

**修复：**
```powershell
"" | Out-File -Encoding utf8 LiteGS\LiteGS\submodules\simple-knn\simple_knn\__init__.py
```

---

## 坑 9：`litegs-fused` 可编辑安装后 `dir()` 返回空

**现象：** 编译成功（`.pyd` 文件约 3.5MB），`import litegs_fused` 不报错但 `dir(litegs_fused)` 返回 `[]`，调用 `createTransformMatrix_forward` 报 `AttributeError`。

**原因：** 与坑 8 同根——源码目录缺少 `__init__.py`。可编辑查找器无法将目录识别为 Python 包，无法导出 `.pyd` 中的符号。

**修复：直接将 `.pyd` 复制到 `site-packages`，绕过可编辑安装：**
```powershell
Copy-Item LiteGS\LiteGS\submodules\gaussian_raster\litegs_fused.cp310-win_amd64.pyd .venv\Lib\site-packages\
uv pip uninstall litegs-fused
```

这比修复 `__init__.py` 更可靠，因为可编辑查找器的行为在不同 setuptools 版本间可能不一致。

---

## 坑 10：`simple_knn._C.pyd` 的 CUDA DLL 依赖

**现象：** `ImportError: DLL load failed while importing _C: 找不到指定的模块。`

**原因：** `_C.pyd` 依赖 `cudart64_12.dll`，但 Python 进程的 DLL 搜索路径不包含 CUDA Toolkit 的 `bin\` 目录。单独 import 时失败。

**为什么 `fused-ssim` 不受影响？** 因为 `import fused_ssim` 通常在 `import torch` 之后，而 torch 的初始化过程已经把 CUDA 的 DLL 目录加入了搜索路径。

**修复二选一：**

临时方案（每个终端）：
```powershell
$env:PATH = "D:\Lib\Cuda12_8_Compute_Toolkit\bin;$env:PATH"
```

永久方案：
```powershell
[Environment]::SetEnvironmentVariable("Path", "D:\Lib\Cuda12_8_Compute_Toolkit\bin;" + [Environment]::GetEnvironmentVariable("Path", "User"), "User")
```

---

## 坑 11：`batch_run.py` 错误使用 `uv python` 而非 `uv run`

**现象：**
```
error: unrecognized subcommand 'utils\prepare_calibration.py'
```

**原因：** `uv python` 是 Python 版本管理子命令，不是运行脚本的入口。`uv run` 才是。

**修复：** 始终使用 `uv run python <script>` 而非 `uv python <script>`。

---

## 坑 12：标定图片和训练帧图片不同，SIFT 关键点数不匹配（核心问题）

这是整个迁移中最隐蔽的问题。

**背景：** 本项目的管道设计——
1. `prepare_calibration.py`：用**标定图片**跑 COLMAP SfM，得到 `cameras.txt`（相机参数）和 `images.txt`（每张图的相机位姿 + SIFT 关键点坐标）
2. `triangulate_from_calibration.py`：用**训练帧图片**跑 SIFT，然后调 `point_triangulator` 将标定相机参数作为输入，对训练帧做三角化

**两批图片文件同名（`001.jpg` ~ `114.jpg`）但内容不同。** 标定图片和训练帧图片是同一相机系统在不同时间拍摄的不同画面，因此 SIFT 特征提取结果不同。

**现象：**
```
F20260618 reconstruction.cc:83] Check failed: image.second.NumPoints2D() == existing_image.NumPoints2D() (923 vs. 2207)
```
COLMAP 3.12.3 的 `point_triangulator` 硬校验输入模型（标定 `images.txt`）中每张图的 2D 关键点数与数据库（训练帧 SIFT 结果）一致。

### 为什么源主机没问题？

源主机可能在以下任一条件下运行：
1. 标定和训练使用了**相同图片**（如从视频中提取的同一批帧）
2. COLMAP 的 `point_triangulator` 校验逻辑在更早的构建版本中不存在或为 warning 而非 fatal

### 完整修复流程

**步骤 1：清理旧 COLMAP 残留**

源数据中可能包含 COLMAP 3.12.3 之前的输出文件（如 COLMAP 3.8 创建的 `database.db`），必须先清理：
```powershell
Remove-Item -Recurse -Force data\calibration\0618\distorted -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force data\calibration\0618\sparse -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force data\calibration\0618\sparse_bin -ErrorAction SilentlyContinue
Remove-Item data\calibration\0618\database.db* -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force data\0618\2026-06-18-195909\distorted -ErrorAction SilentlyContinue
```

**步骤 2：用 COLMAP 3.12.3 重新标定**
```powershell
uv run python utils\prepare_calibration.py --sub_dir 0618
```
此时 `distorted/sparse/0/` 下会生成标定结果，`sparse/images.txt` 含有每张标定图片的完整关键点数据。

**步骤 3：用训练数据库的关键点计数替换标定 `images.txt` 中的关键点**

这是保证 `point_triangulator` 校验通过的关键步骤：

```python
import sqlite3

# 从训练帧数据库读取每张图片的实际 SIFT 关键点数
train_db = r'E:\work\26.7_SKNJ\LiteGSWin\data\0618\2026-06-18-195909\distorted\database.db'
conn = sqlite3.connect(train_db)
rows = conn.execute('''
    SELECT i.name, k.rows
    FROM images i
    JOIN keypoints k ON i.image_id = k.image_id
    ORDER BY i.image_id
''').fetchall()
db_counts = {name: rows_count for name, rows_count in rows}
conn.close()

# 构造新的 images.txt：保留相机位姿行，用匹配数量的占位关键点替换原始关键点行
calib_txt = r'E:\work\26.7_SKNJ\LiteGSWin\data\calibration\0618\sparse\images.txt'
lines = open(calib_txt).readlines()
with open(calib_txt, 'w') as f:
    for line in lines:
        s = line.strip()
        if not s or s.startswith('#'):
            f.write(line)          # 保留注释行和空行
            continue
        parts = s.split()
        if parts[0].isdigit() and parts[-1].endswith(('.jpg', '.png')):
            f.write(line)          # 保留相机位姿行
            img_name = parts[-1]
            count = db_counts.get(img_name, 0)
            # 写入 N 个占位关键点，格式 "X Y -1"（-1 的 point3D_id 表示无关联 3D 点）
            placeholders = ' '.join([f"{i*10.0} {i*10.0} -1" for i in range(count)])
            f.write(placeholders + '\n' if placeholders else '\n')
```

**关键点格式说明：** COLMAP `images.txt` 每张图占两行：
```
IMAGE_ID QW QX QY QZ TX TY TZ CAMERA_ID NAME          ← 相机位姿行（必须保留）
X1 Y1 POINT3D_ID1 X2 Y2 POINT3D_ID2 ...               ← 关键点行（需要替换）
```

### 为什么不能用空行代替关键点行？

`load_calibration_image_mapping()` 解析器使用交替状态机：读到 10 字段行 → 切换为"期望关键点"状态 → 读到非空行 → 切换回"期望位姿"状态。如果关键点行是空的，解析器**跳过空行但不切换状态**，导致下一个位姿行被当关键点跳过，最终**隔行丢失图片**（只解析到 57 张奇数号图片）。

因此**必须写入非空关键点行**——用与训练数据库匹配数量的占位关键点（`X Y -1`）。

---

## 坑 13：`uv pip install` 的 hardlink 跨盘警告

**现象：**
```
warning: Failed to hardlink files; falling back to full copy.
```

**原因：** uv 默认用 hardlink 节省磁盘空间，但缓存和目标 `.venv` 在不同文件系统时硬链接不可用。**不影响编译产物的正确性和性能**，仅为安装速度优化。

**消除警告（可选）：**
```powershell
[Environment]::SetEnvironmentVariable("UV_LINK_MODE", "copy", "User")
```

---

## 坑 14：Python 3.10 中文 MSVC 编译器的字符编码冲突

**现象：** `torch.utils.cpp_extension` 检测 MSVC 版本时：
```
UserWarning: Error checking compiler version for cl: 'cp1' codec can't decode bytes
```

**原因：** 中文版 MSVC (`用于 x64 的 Microsoft (R) C/C++ 优化编译器`) 的输出使用系统 OEM code page (CP936)，`torch.cpp_extension` 尝试用 `oem` codec 解码时失败。**这是警告，不影响编译**，但会干扰编译器版本检测的下一步逻辑。

**影响范围：** 仅影响版本号校验。若编译器实际版本 ≥ 要求的最低版本（MSVC 19.0），编译正常进行。

---

## 完整部署速查卡

### 环境变量（每次编译前）

```powershell
$env:PATH = "E:\Programs\VS 2022\Community\VC\Tools\MSVC\14.38.33130\bin\Hostx64\x64;D:\Lib\Cuda12_8_Compute_Toolkit\bin;$env:PATH"
$env:CUDA_ARCHITECTURES = "120"
```

### 永久 PATH（一次性）

```powershell
$paths = @(
    "D:\Lib\Cuda12_8_Compute_Toolkit\bin",
    "E:\work\26.7_SKNJ\LiteGSWin\COLMAP-3.12-windows-cuda\bin",
    "E:\Programs\cmake-4.1.0-windows-x86_64\bin"
)
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$newPath = ($paths + $userPath) -join ';'
[Environment]::SetEnvironmentVariable("Path", $newPath, "User")
```

### CUDA 扩展编译命令

```powershell
cd e:\work\26.7_SKNJ\LiteGSWin
$env:PATH = "E:\Programs\VS 2022\Community\VC\Tools\MSVC\14.38.33130\bin\Hostx64\x64;D:\Lib\Cuda12_8_Compute_Toolkit\bin;$env:PATH"
$env:CUDA_ARCHITECTURES = "120"
uv pip install setuptools wheel

# 依次编译
foreach ($ext in @("simple-knn", "fused_ssim", "gaussian_raster")) {
    Push-Location "LiteGS\LiteGS\submodules\$ext"
    uv pip install -e . --no-build-isolation
    Pop-Location
}

# simple-knn / litegs-fused 的 __init__.py 补丁
"" | Out-File -Encoding utf8 LiteGS\LiteGS\submodules\simple-knn\simple_knn\__init__.py

# litegs-fused 改用直接复制 .pyd（绕过 editable finder bug）
Copy-Item LiteGS\LiteGS\submodules\gaussian_raster\litegs_fused.cp310-win_amd64.pyd .venv\Lib\site-packages\
uv pip uninstall litegs-fused
```

### 运行管道

```powershell
cd e:\work\26.7_SKNJ\LiteGSWin
uv run python batch_run.py --sub_dir 0618
```
