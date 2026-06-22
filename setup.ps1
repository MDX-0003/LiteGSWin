<#
.SYNOPSIS
    LiteGS Pipeline - One-click Windows setup script (PowerShell)

.DESCRIPTION
    Sets up the complete LiteGS environment on a Windows 11 machine with
    RTX 5080 / CUDA 12.8.  Run this from the repository root.

.PREREQUISITES
    Before running this script, install manually:
      1. uv (Python package manager)  → https://docs.astral.sh/uv/
         powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
      2. NVIDIA GPU Driver 551.xx+
      3. CUDA Toolkit 12.8           → https://developer.nvidia.com/cuda-downloads
      4. Visual Studio 2022 Community + "Desktop Development with C++"
      5. CMake 3.20+                 → https://cmake.org/download/
      6. COLMAP 3.12.3 CUDA          → https://github.com/colmap/colmap/releases

.EXAMPLE
    .\setup.ps1
    .\setup.ps1 -ColmapPath "C:\tools\colmap"
    .\setup.ps1 -CudaPath "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8" -ColmapPath "D:\colmap"
#>

param(
    [string]$CudaPath = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8",
    [string]$ColmapPath = "",
    [string]$VsMsbcPath = "",
    [switch]$SkipCudaExtensions = $false
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  LiteGS Pipeline - Environment Setup" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""


# ---- Step 0: Verify prerequisites ----
Write-Host "[0/6] Verifying prerequisites..." -ForegroundColor Yellow

$tools = @{
    "uv"      = "uv (Python package manager) - https://docs.astral.sh/uv/"
    "cmake"   = "CMake 3.20+ - https://cmake.org/download/"
    "nvcc"    = "CUDA Toolkit 12.8 - https://developer.nvidia.com/cuda-downloads"
}
foreach ($tool in $tools.Keys) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Host "  ERROR: $tool not found on PATH. $($tools[$tool])" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] $tool"
}

# Verify CUDA version
$cudaVer = & nvcc --version 2>&1 | Select-String "release (\d+\.\d+)" | ForEach-Object { $_.Matches.Groups[1].Value }
if ($cudaVer -ne "12.8") {
    Write-Host "  WARNING: nvcc reports CUDA $cudaVer, expected 12.8" -ForegroundColor Yellow
}

# Verify GPU
$gpuCheck = & nvidia-smi --query-gpu=name --format=csv,noheader 2>$null
if ($gpuCheck) {
    Write-Host "  [OK] GPU: $($gpuCheck.Trim())"
} else {
    Write-Host "  WARNING: Could not detect GPU via nvidia-smi" -ForegroundColor Yellow
}

# Verify VS 2022 MSVC
if ($VsMsbcPath) {
    $clPath = Join-Path $VsMsbcPath "cl.exe"
} else {
    # Auto-detect: find newest MSVC in VS 2022
    $vsBase = "${env:ProgramFiles}\Microsoft Visual Studio\2022"
    if (Test-Path $vsBase) {
        $installPath = & "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -latest -property installationPath 2>$null
        if (-not $installPath) { $installPath = $vsBase }
    } else {
        $installPath = $vsBase
    }
    $msvcDirs = Get-ChildItem (Join-Path $installPath "VC\Tools\MSVC") -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending
    if ($msvcDirs) {
        $clPath = Join-Path $msvcDirs[0].FullName "bin\Hostx64\x64\cl.exe"
    }
}

if ($clPath -and (Test-Path $clPath)) {
    Write-Host "  [OK] MSVC: $clPath"
    $env:PATH = "$(Split-Path $clPath -Parent);$env:PATH"
} else {
    Write-Host "  WARNING: MSVC cl.exe not auto-detected. CUDA extension compilation may fail." -ForegroundColor Yellow
    Write-Host "           Install VS 2022 with 'Desktop Development with C++' or use -VsMsbcPath" -ForegroundColor Yellow
}

# Verify COLMAP
if ($ColmapPath) {
    $colmapExe = Join-Path $ColmapPath "bin\colmap.exe"
} else {
    $colmapExe = Get-Command colmap -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
}
if ($colmapExe -and (Test-Path $colmapExe)) {
    Write-Host "  [OK] COLMAP: $colmapExe"
    $colmapBin = Split-Path $colmapExe -Parent
    $env:PATH = "$colmapBin;$env:PATH"
} else {
    Write-Host "  WARNING: COLMAP not found. Download COLMAP-3.12.3-windows-cuda.zip from:" -ForegroundColor Yellow
    Write-Host "           https://github.com/colmap/colmap/releases/tag/3.12.3" -ForegroundColor Yellow
    Write-Host "           Extract to a folder and use -ColmapPath <path>" -ForegroundColor Yellow
}

Write-Host ""


# ---- Step 1: Python 3.10 + venv ----
Write-Host "[1/6] Setting up Python 3.10 virtual environment..." -ForegroundColor Yellow

uv python install 3.10 2>$null
uv venv --python 3.10 .venv
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Failed to create virtual environment." -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Virtual environment created"
Write-Host ""


# ---- Step 2: PyTorch ----
Write-Host "[2/6] Installing PyTorch 2.7.0 with CUDA 12.8..." -ForegroundColor Yellow

uv pip install torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 `
    --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: PyTorch install failed." -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] PyTorch 2.7.0+cu128 installed"
Write-Host ""


# ---- Step 3: Pip dependencies ----
Write-Host "[3/6] Installing pip dependencies..." -ForegroundColor Yellow

uv pip install -r migration\requirements_LiteGS.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Dependency install failed." -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Dependencies installed"
Write-Host ""


# ---- Step 4: CUDA extensions ----
if (-not $SkipCudaExtensions) {
    Write-Host "[4/6] Compiling CUDA extensions (this may take several minutes)..." -ForegroundColor Yellow

    # Detect GPU architecture
    $arch = $null
    try {
        $archStr = .venv\Scripts\python.exe -c "import torch; cc=torch.cuda.get_device_capability(); print(f'{cc[0]}{cc[1]}')" 2>$null
        if ($archStr -match '^\d+$') {
            $arch = $archStr.Trim()
        }
    } catch { }
    if (-not $arch) {
        Write-Host "  GPU detection failed, defaulting to sm_120 (RTX 5080 Blackwell)" -ForegroundColor Yellow
        $arch = "120"
    }
    $env:CUDA_ARCHITECTURES = $arch
    Write-Host "  GPU architecture: sm_$arch"

    # Install build tools
    uv pip install setuptools wheel

    # Build extensions
    $extensions = @(
        @{Name="simple-knn";     Dir="LiteGS\LiteGS\submodules\simple-knn";       Init="LiteGS\LiteGS\submodules\simple-knn\simple_knn\__init__.py"},
        @{Name="fused-ssim";     Dir="LiteGS\LiteGS\submodules\fused_ssim"},
        @{Name="litegs-fused";   Dir="LiteGS\LiteGS\submodules\gaussian_raster"}
    )

    foreach ($ext in $extensions) {
        Write-Host "  Building $($ext.Name)..."
        Push-Location $ext.Dir
        uv pip install -e . --no-build-isolation
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  WARNING: $($ext.Name) build failed." -ForegroundColor Yellow
            Write-Host "    Try manually: cd $($ext.Dir) && `$env:CUDA_ARCHITECTURES='$arch' && uv pip install -e . --no-build-isolation"
        } else {
            Write-Host "    [OK]"
        }
        Pop-Location

        # Create __init__.py if specified
        if ($ext.Init) {
            $initPath = Join-Path $RootDir $ext.Init
            if (-not (Test-Path $initPath)) {
                "" | Out-File -Encoding utf8 $initPath
            }
        }
    }

    # Workaround: litegs-fused editable finder bug - copy .pyd directly
    $litegsPyd = Get-ChildItem "LiteGS\LiteGS\submodules\gaussian_raster" -Filter "*.pyd" -ErrorAction SilentlyContinue
    if ($litegsPyd) {
        Copy-Item $litegsPyd.FullName .venv\Lib\site-packages\ -Force
    }

    Write-Host ""
}


# ---- Step 5: Verify ----
Write-Host "[5/6] Verifying installation..." -ForegroundColor Yellow

.venv\Scripts\python.exe -c @"
import torch
print(f'PyTorch: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'GPU: {torch.cuda.get_device_name(0)}')
print(f'Arch: sm_{"".join(map(str, torch.cuda.get_device_capability()))}')
"@

if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: PyTorch verification failed." -ForegroundColor Red
    exit 1
}

if (-not $SkipCudaExtensions) {
    Write-Host "  Verifying CUDA extensions..."
    .venv\Scripts\python.exe -c "import torch; import simple_knn._C; print('  simple_knn: OK')" 2>$null
    .venv\Scripts\python.exe -c "import torch; import litegs_fused; print('  litegs_fused: OK')" 2>$null
    .venv\Scripts\python.exe -c "import torch, fused_ssim; img=torch.rand(1,3,128,128,device='cuda'); fused_ssim.fused_l1_ssim_loss(img,img); print('  fused_ssim: OK')" 2>$null
}

Write-Host ""
Write-Host "[6/6] Setup complete!" -ForegroundColor Green
Write-Host ""


# ---- Done ----
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  NEXT STEPS" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Ensure COLMAP 3.12.3 is available on PATH or use --colmap_executable"
Write-Host ""
Write-Host "2. Prepare your data:"
Write-Host "   data\calibration\<sub_dir>\input\        (calibration images)"
Write-Host "   data\<sub_dir>\<YYYY-MM-DD-HHmmss>\input\ (training images)"
Write-Host ""
Write-Host "3. Run calibration:"
Write-Host "   uv run python utils\prepare_calibration.py --sub_dir <sub_dir>"
Write-Host ""
Write-Host "4. Train:"
Write-Host "   uv run python batch_run.py --sub_dir <sub_dir>"
Write-Host ""
Write-Host "See docs\MIGRATION_PITFALLS.md for known issues and solutions."
Write-Host "=============================================="
