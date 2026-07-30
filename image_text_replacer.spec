# -*- mode: python ; coding: utf-8 -*-
"""批量图片文字替换工具 - PyInstaller spec 文件（修复版 v2）。
修复内容（解决 "python314.dll 找不到指定模块"）：
  1. 全量打包 Win SDK UCRT 41 个 DLL（含 ucrtbase.dll 及所有 api-ms-win-*）
  2. 全量打包 VS2022 Release CRT 10 个 DLL（新版 vcruntime140 / msvcp140_1/2 / concrt140 / vcruntime140_threads 等）
  3. 覆盖 PyInstaller 自动收集的旧版 CRT DLL，避免版本不匹配

用法:
    pyinstaller image_text_replacer.spec
产物: dist/ImageTextReplacer/ImageTextReplacer.exe（onedir 形式，用于后续打包安装包）

注意: Python 3.14 官方要求 Windows 10 1809 及以上版本。
      如仍报 "找不到指定模块"，请在目标电脑安装：
        - Visual C++ 2015-2022 Redistributable (x64)
        - Windows 更新 KB2999226 (UCRT，旧 Win10 需要)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)

PROJECT_ROOT = Path(SPECPATH).resolve()
SITE_PACKAGES = Path(sys.prefix) / "Lib" / "site-packages"

# ── main entry ────────────────────────────────────────────────────────────────
entry_script = str(PROJECT_ROOT / "main.py")
app_name = "ImageTextReplacer"

# ════════════════════════════════════════════════════════════════════════════════
# ══ FIX: 全量 CRT DLLs（覆盖 PyInstaller 自动收集的旧版本） ════════════════════
# ════════════════════════════════════════════════════════════════════════════════
# 1) Win SDK UCRT: C:\Program Files (x86)\Windows Kits\10\Redist\ucrt\DLLs\x64
#    包含 ucrtbase.dll + 40 个 api-ms-win-{core,crt}-*.dll
UCRT_DIR = Path(r"C:\Program Files (x86)\Windows Kits\10\Redist\ucrt\DLLs\x64")
binaries_ucrt = []
if UCRT_DIR.exists():
    for dll in sorted(UCRT_DIR.glob("*.dll")):
        # PyInstaller binaries 格式: (src_path, dest_dir_in_bundle)
        # 放在顶层和 _internal 都放一份，确保 bootloader 和 python314.dll 都能找到
        binaries_ucrt.append((str(dll), "."))
        binaries_ucrt.append((str(dll), "_internal"))
    print(f"[SPEC] UCRT DLLs 已添加: {len(binaries_ucrt)//2} 个 × 2 位置 = {len(binaries_ucrt)} 条目")
else:
    print(f"[WARN] UCRT 目录不存在: {UCRT_DIR}（缺少它可能导致 python314.dll LoadLibrary 失败）")

# 2) VS2022 Release CRT (x64): D:\vs\project\VC\Redist\MSVC\14.51.36231\x64\Microsoft.VC145.CRT
#    包含 concrt140.dll / msvcp140{,_1,_2,_atomic_wait,_codecvt_ids}.dll
#         vccorlib140.dll / vcruntime140{,_1,_threads}.dll
VS_CRT_DIR = Path(r"D:\vs\project\VC\Redist\MSVC\14.51.36231\x64\Microsoft.VC145.CRT")
binaries_vc = []
if VS_CRT_DIR.exists():
    for dll in sorted(VS_CRT_DIR.glob("*.dll")):
        binaries_vc.append((str(dll), "."))
        binaries_vc.append((str(dll), "_internal"))
    print(f"[SPEC] VS CRT DLLs 已添加: {len(binaries_vc)//2} 个 × 2 位置 = {len(binaries_vc)} 条目")
else:
    # 回退: 从 C:\Python314 取 vcruntime140.dll / vcruntime140_1.dll
    print(f"[WARN] VS CRT 目录不存在: {VS_CRT_DIR}，尝试使用 Python314 自带的 vcruntime")
    py_dll_dir = Path(r"C:\Python314")
    for name in ["vcruntime140.dll", "vcruntime140_1.dll"]:
        p = py_dll_dir / name
        if p.exists():
            binaries_vc.append((str(p), "."))
            binaries_vc.append((str(p), "_internal"))

# ── 1. RapidOCR 资源 ──────────────────────────────────────────────────────────
rapidocr_root = SITE_PACKAGES / "rapidocr"
datas_rapidocr = []
for f in ["config.yaml", "default_models.yaml"]:
    src = rapidocr_root / f
    if src.exists():
        datas_rapidocr.append((str(src), "rapidocr"))
models_dir = rapidocr_root / "models"
if models_dir.exists():
    for src in models_dir.iterdir():
        if src.is_file():
            datas_rapidocr.append((str(src), "rapidocr/models"))
arch_cfg = rapidocr_root / "inference_engine" / "pytorch" / "networks" / "architectures" / "arch_config.yaml"
if arch_cfg.exists():
    datas_rapidocr.append((str(arch_cfg), "rapidocr/inference_engine/pytorch/networks/architectures"))
datas_rapidocr += collect_data_files("rapidocr", include_py_files=False, excludes=["**/__pycache__/**"])

# ── 2. ONNX Runtime ────────────────────────────────────────────────────────────
hiddenimports_onnx = collect_submodules("onnxruntime")
binaries_onnx = collect_dynamic_libs("onnxruntime")
datas_onnx = collect_data_files("onnxruntime", include_py_files=False)
datas_onnx += copy_metadata("onnxruntime")

# ── 3. PySide6 ─────────────────────────────────────────────────────────────────
hiddenimports_pyside = collect_submodules("PySide6")
hiddenimports_pyside += [
    "PySide6.QtSvg",
    "PySide6.QtPrintSupport",
]
datas_pyside = collect_data_files("PySide6", include_py_files=False)
binaries_pyside = collect_dynamic_libs("PySide6")

# ── 4. OpenCV ──────────────────────────────────────────────────────────────────
hiddenimports_cv = collect_submodules("cv2")
binaries_cv = collect_dynamic_libs("cv2")
datas_cv = collect_data_files("cv2", include_py_files=False)

# ── 5. Pillow / numpy / openpyxl / omegaconf ──────────────────────────────────
hiddenimports_misc = [
    *collect_submodules("PIL"),
    *collect_submodules("numpy"),
    *collect_submodules("openpyxl"),
    *collect_submodules("omegaconf"),
    *collect_submodules("importlib.metadata"),
    *collect_submodules("importlib.resources"),
]
datas_misc = (
    collect_data_files("PIL", include_py_files=False)
    + collect_data_files("numpy", include_py_files=False)
    + collect_data_files("openpyxl", include_py_files=False)
    + collect_data_files("omegaconf", include_py_files=False)
    + copy_metadata("rapidocr")
    + copy_metadata("opencv-python")
    + copy_metadata("Pillow")
    + copy_metadata("PySide6")
    + copy_metadata("numpy")
    + copy_metadata("openpyxl")
    + copy_metadata("omegaconf")
)

# ── 6. 本项目其它数据文件 ──────────────────────────────────────────────────────
datas_project = []
for fname in ["config_template.xlsx", "README.md"]:
    fp = PROJECT_ROOT / fname
    if fp.exists():
        datas_project.append((str(fp), "."))

# ════════════════════════════════════════════════════════════════════════════════
# ══ 汇总：注意 binaries_ucrt / binaries_vc 放最前面，确保版本优先覆盖 ══════════
# ════════════════════════════════════════════════════════════════════════════════
datas = datas_rapidocr + datas_onnx + datas_pyside + datas_cv + datas_misc + datas_project
binaries = binaries_ucrt + binaries_vc + binaries_onnx + binaries_pyside + binaries_cv
hiddenimports = (
    hiddenimports_onnx
    + hiddenimports_pyside
    + hiddenimports_cv
    + hiddenimports_misc
    + [
        # RapidOCR 引擎后端（按需 import，需显式声明）
        "rapidocr.inference_engine.onnxruntime",
        "rapidocr.inference_engine.onnxruntime.main",
        "rapidocr.inference_engine.onnxruntime.provider_config",
        # 子任务模块
        "rapidocr.ch_ppocr_det",
        "rapidocr.ch_ppocr_det.main",
        "rapidocr.ch_ppocr_det.utils",
        "rapidocr.ch_ppocr_cls",
        "rapidocr.ch_ppocr_cls.main",
        "rapidocr.ch_ppocr_cls.utils",
        "rapidocr.ch_ppocr_rec",
        "rapidocr.ch_ppocr_rec.main",
        "rapidocr.ch_ppocr_rec.utils",
        "rapidocr.ch_ppocr_rec.typings",
        "rapidocr.cal_rec_boxes",
        "rapidocr.cal_rec_boxes.main",
        # 工具链
        "rapidocr.utils.parse_parameters",
        "rapidocr.utils.download_file",
        "rapidocr.utils.download_models",
        "rapidocr.utils.load_image",
        "rapidocr.utils.log",
        "rapidocr.utils.output",
        "rapidocr.utils.process_img",
        "rapidocr.utils.to_json",
        "rapidocr.utils.to_markdown",
        "rapidocr.utils.typings",
        "rapidocr.utils.utils",
        "rapidocr.utils.vis_res",
        "rapidocr.utils.model_resolver",
    ]
)

a = Analysis(
    [entry_script],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 不使用的后端引擎，减小体积
        "torch",
        "paddle",
        "paddlepaddle",
        "openvino",
        "tensorrt",
        "mnn",
        "matplotlib",
        "scipy",
        "pandas",
        "pytest",
        "IPython",
        "jupyter",
        "notebook",
        "tqdm",
        "requests",
        "httpx",
        "urllib3",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,   # GUI 程序无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=app_name,
)
