---
name: env-cuda-toolchain
description: CUDA 12.8 toolchain locations, PATH requirements, and MSVC compiler configuration
metadata:
  type: project
---

# CUDA 12.8 + MSVC Toolchain

## Paths
- **CUDA Toolkit**: `D:\Lib\Cuda12_8_Compute_Toolkit` (no spaces in path — critical)
- **nvcc**: `D:\Lib\Cuda12_8_Compute_Toolkit\bin\nvcc.exe` (release 12.8, V12.8.61)
- **CUDA DLLs**: `cudart64_12.dll`, `cublas64_12.dll` etc. in `bin\`
- **VS 2022**: `E:\Programs\VS 2022\Community`
- **MSVC (working)**: `14.38.33130` at `E:\Programs\VS 2022\Community\VC\Tools\MSVC\14.38.33130\bin\Hostx64\x64\cl.exe`
- **MSVC (NOT working with CUDA 12.8)**: `14.44.35207` — nvcc can't set up environment
- **CMake**: `E:\Programs\cmake-4.1.0-windows-x86_64\bin\cmake.exe` (must be on PATH)

## Permanent PATH (User level)
```
D:\Lib\Cuda12_8_Compute_Toolkit\bin;E:\work\26.7_SKNJ\LiteGSWin\COLMAP-3.12-windows-cuda\bin;E:\Programs\cmake-4.1.0-windows-x86_64\bin
```

## CUDA Extension Compilation
```
$env:PATH = "E:\Programs\VS 2022\Community\VC\Tools\MSVC\14.38.33130\bin\Hostx64\x64;D:\Lib\Cuda12_8_Compute_Toolkit\bin;$env:PATH"
$env:CUDA_ARCHITECTURES = "120"
uv pip install -e . --no-build-isolation
```

**Why:** CUDA 12.8 + MSVC 14.44 doesn't work. Use MSVC 14.38. Don't use VS Developer PowerShell (triggers DISTUTILS_USE_SDK ABI check). Chinese MSVC output causes torch.cpp_extension compiler detection warning but doesn't block compilation.

**How to apply:** See [[env-cuda-extension-build]] for per-extension quirks.
