# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata
import os

datas = [
    ("app.py", "."),
    ("run_app.py", "."),
    ("hypecutter/", "hypecutter/"),
    ("scene_manager/", "scene_manager/"),
    ("license_client.py", "."),
    ("license_guard.py", "."),
    ("heartbeat.py", "."),
    ("paths.py", "."),
    ("config_client.py", "."),
    ("db.py", "."),
    ("license/", "license/"),
]

if os.path.exists("ffmpeg_bin"):
    datas += [("ffmpeg_bin/", "ffmpeg_bin/")]

datas += collect_data_files("streamlit")
datas += collect_data_files("altair")
datas += collect_data_files("scenedetect")

datas += copy_metadata("streamlit")
datas += copy_metadata("requests")
datas += copy_metadata("altair")
datas += copy_metadata("packaging")
datas += copy_metadata("scenedetect")
datas += copy_metadata("opencv-python")
datas += copy_metadata("Pillow")

hiddenimports = collect_submodules("streamlit")
hiddenimports += collect_submodules("altair")
hiddenimports += collect_submodules("scenedetect")
hiddenimports += collect_submodules("cv2")

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=[],
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
