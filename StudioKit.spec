# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata
import glob
import os
import sys

# ── Compiled Cython extensions (.pyd on Windows, .so on Mac/Linux) ────────────
def collect_cython_extensions():
    """Collect all compiled Cython .pyd/.so files as binaries."""
    binaries = []
    ext = ".pyd" if sys.platform == "win32" else ".so"
    patterns = [
        f"*{ext}",
        f"hypecutter/*{ext}",
        f"scene_manager/*{ext}",
    ]
    for pattern in patterns:
        for path in glob.glob(pattern):
            # dest is the directory inside the bundle
            dest = os.path.dirname(path) or "."
            binaries.append((path, dest))
    return binaries

# ── Data files ────────────────────────────────────────────────────────────────
datas = [
    ("app.py", "."),
    ("run_app.py", "."),
    ("i18n.py", "."),
    # UI files (not compiled — Streamlit UI can't be Cython compiled)
    ("hypecutter/ui.py", "hypecutter/"),
    ("hypecutter/__init__.py", "hypecutter/"),
    # Scene manager UI + submodules (ui.py not compiled; others are compiled)
    ("scene_manager/ui.py", "scene_manager/"),
    ("scene_manager/__init__.py", "scene_manager/"),
    ("scene_manager/downloader.py", "scene_manager/"),
    ("scene_manager/metadata.py", "scene_manager/"),
    ("scene_manager/splitter.py", "scene_manager/"),
    # License files (compiled; only the license/ key directory needed as data)
    ("license/", "license/"),
    # Config entry points (not compiled)
    ("paths.py", "."),
    ("config_client.py", "."),
    ("db.py", "."),
    ("heartbeat.py", "."),
]

if os.path.exists("ffmpeg_bin"):
    datas += [("ffmpeg_bin/", "ffmpeg_bin/")]

datas += collect_data_files("streamlit")
datas += collect_data_files("altair")
datas += collect_data_files("scenedetect")
datas += collect_data_files("faster_whisper")  # includes silero_vad_v6.onnx and other assets

datas += copy_metadata("streamlit")
datas += copy_metadata("requests")
datas += copy_metadata("altair")
datas += copy_metadata("packaging")
datas += copy_metadata("scenedetect")
datas += copy_metadata("opencv-python")
datas += copy_metadata("Pillow")
datas += copy_metadata("openai")
datas += copy_metadata("anthropic")
datas += copy_metadata("faster-whisper")
datas += copy_metadata("yt-dlp")

# ── Hidden imports ────────────────────────────────────────────────────────────
hiddenimports = collect_submodules("streamlit")
hiddenimports += collect_submodules("altair")
hiddenimports += collect_submodules("scenedetect")
hiddenimports += collect_submodules("cv2")
hiddenimports += collect_submodules("openai")
hiddenimports += collect_submodules("anthropic")
hiddenimports += collect_submodules("faster_whisper")
hiddenimports += collect_submodules("yt_dlp")

# ── Compiled extensions ───────────────────────────────────────────────────────
extra_binaries = collect_cython_extensions()

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=extra_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StudioKit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="StudioKit",
)
app = BUNDLE(
    coll,
    name="StudioKit.app",
    icon=None,
    bundle_identifier="com.studiokit.app",
)
