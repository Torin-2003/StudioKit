# StudioKit Cython Protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compile StudioKit's core Python files into platform-native binaries (.pyd on Windows, .so on Mac) using Cython, so PyInstaller bundles binary extensions instead of readable source code.

**Architecture:** A `build_cython.py` script compiles 5 target files (core_engine.py, license_guard.py, license_client.py, analyzer.py, classifier.py) into C extensions. The compiled .pyd/.so files are placed back in their original package directories. PyInstaller's spec is updated to exclude the .py sources and include the compiled extensions. GitHub Actions runs the Cython build step before PyInstaller on both Mac and Windows.

**Tech Stack:** Python 3.11, Cython 3.x, setuptools, PyInstaller, GitHub Actions (macos-latest + windows-latest)

**Key constraint:** Files use modern Python type annotations (`list[str]`, `dict[str, int]`, `tuple[float, float]`). Cython 3.x handles these natively with `# cython: language_level=3` directive — no source changes needed.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `build_cython.py` | Create | One-command Cython build for all 5 target files |
| `StudioKit.spec` | Modify | Add compiled extensions to binaries, exclude .py sources from datas |
| `.github/workflows/build.yml` | Modify | Add Cython build step before PyInstaller on Mac + Windows |

**Files being compiled (no changes to these files themselves):**
- `hypecutter/core_engine.py` → `hypecutter/core_engine.pyd` / `.so`
- `license_guard.py` → `license_guard.pyd` / `.so`
- `license_client.py` → `license_client.pyd` / `.so`
- `scene_manager/analyzer.py` → `scene_manager/analyzer.pyd` / `.so`
- `scene_manager/classifier.py` → `scene_manager/classifier.pyd` / `.so`

---

## Task 1: Create `build_cython.py`

**Files:**
- Create: `build_cython.py`

- [ ] **Step 1: Create `build_cython.py`**

Create `/Users/torin/Documents/Code Work/StudioKit/build_cython.py`:

```python
"""
Build script: compile target Python files to Cython C extensions.
Run from the StudioKit root directory:
    python build_cython.py build_ext --inplace
"""
from setuptools import setup, Extension
from Cython.Build import cythonize
import sys
import os
import shutil

# Files to compile. Paths are relative to the StudioKit root.
TARGETS = [
    "hypecutter/core_engine.py",
    "license_guard.py",
    "license_client.py",
    "scene_manager/analyzer.py",
    "scene_manager/classifier.py",
]

extensions = []
for target in TARGETS:
    # Module name: hypecutter/core_engine.py -> hypecutter.core_engine
    module_name = target.replace("/", ".").replace("\\", ".").replace(".py", "")
    ext = Extension(
        name=module_name,
        sources=[target],
        extra_compile_args=["/O2"] if sys.platform == "win32" else ["-O2"],
    )
    extensions.append(ext)

setup(
    name="studiokit_extensions",
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
        },
        quiet=True,
    ),
)
```

- [ ] **Step 2: Verify syntax**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python3 -c "import ast; ast.parse(open('build_cython.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add build_cython.py
git commit -m "feat: add build_cython.py to compile core files to binary extensions"
```

---

## Task 2: Test Cython build locally on Mac

**Files:**
- No file changes — just running the build

- [ ] **Step 1: Install Cython**

```bash
/opt/homebrew/opt/python@3.14/bin/python3.14 -m pip install cython --break-system-packages
```

Expected: `Successfully installed Cython-3.x.x` (or already installed)

- [ ] **Step 2: Run Cython build**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python3 build_cython.py build_ext --inplace 2>&1 | tail -20
```

Expected: No errors. Build completes with lines like:
```
building 'hypecutter.core_engine' extension
...
copying build/lib.macosx-.../hypecutter/core_engine.cpython-311-darwin.so -> hypecutter/
```

- [ ] **Step 3: Verify .so files exist in correct locations**

```bash
find "/Users/torin/Documents/Code Work/StudioKit" \
  -name "*.so" -o -name "*.pyd" | grep -v build/ | sort
```

Expected output (Mac):
```
./hypecutter/core_engine.cpython-3xx-darwin.so
./license_client.cpython-3xx-darwin.so
./license_guard.cpython-3xx-darwin.so
./scene_manager/analyzer.cpython-3xx-darwin.so
./scene_manager/classifier.cpython-3xx-darwin.so
```

- [ ] **Step 4: Verify the compiled modules can be imported**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python3 -c "
import sys
sys.path.insert(0, '.')
import license_guard; print('license_guard OK')
import license_client; print('license_client OK')
from hypecutter import core_engine; print('core_engine OK')
from scene_manager import analyzer; print('analyzer OK')
from scene_manager import classifier; print('classifier OK')
"
```

Expected: All 5 print `OK`

- [ ] **Step 5: Add build artifacts to .gitignore**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
cat >> .gitignore << 'EOF'

# Cython build artifacts
*.so
*.pyd
*.c
build/
*.egg-info/
EOF
```

- [ ] **Step 6: Commit .gitignore update**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add .gitignore
git commit -m "chore: add Cython build artifacts to .gitignore"
```

---

## Task 3: Update `StudioKit.spec` to use compiled extensions

**Files:**
- Modify: `StudioKit.spec`

The spec needs two changes:
1. Remove the `.py` source files that will be compiled from `datas` (they'll be replaced by `.pyd`/`.so`)
2. Add a `collect_dynamic_libs` call to pick up the compiled extensions

- [ ] **Step 1: Read current spec**

```bash
cat "/Users/torin/Documents/Code Work/StudioKit/StudioKit.spec"
```

- [ ] **Step 2: Replace `StudioKit.spec` with updated version**

Create `/Users/torin/Documents/Code Work/StudioKit/StudioKit.spec`:

```python
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

datas += copy_metadata("streamlit")
datas += copy_metadata("requests")
datas += copy_metadata("altair")
datas += copy_metadata("packaging")
datas += copy_metadata("scenedetect")
datas += copy_metadata("opencv-python")
datas += copy_metadata("Pillow")

# ── Hidden imports ────────────────────────────────────────────────────────────
hiddenimports = collect_submodules("streamlit")
hiddenimports += collect_submodules("altair")
hiddenimports += collect_submodules("scenedetect")
hiddenimports += collect_submodules("cv2")

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
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add StudioKit.spec
git commit -m "feat: update StudioKit.spec to bundle Cython compiled extensions"
```

---

## Task 4: Update GitHub Actions to run Cython before PyInstaller

**Files:**
- Modify: `.github/workflows/build.yml`

- [ ] **Step 1: Update `.github/workflows/build.yml`**

Replace the file content with:

```yaml
name: Build StudioKit

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write

jobs:
  build-mac:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install FFmpeg
        run: brew install ffmpeg

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pyinstaller cython setuptools

      - name: Bundle FFmpeg
        run: |
          mkdir -p ffmpeg_bin
          cp $(which ffmpeg) ffmpeg_bin/ffmpeg
          cp $(which ffprobe) ffmpeg_bin/ffprobe

      - name: Compile Cython extensions
        run: python build_cython.py build_ext --inplace

      - name: Verify compiled extensions exist
        run: |
          ls hypecutter/*.so || ls hypecutter/*.pyd
          ls *.so || ls *.pyd
          ls scene_manager/*.so || ls scene_manager/*.pyd

      - name: Build Mac app
        run: pyinstaller StudioKit.spec

      - name: Zip Mac app
        run: |
          cd dist
          zip -r StudioKit-mac.zip StudioKit.app

      - name: Upload Mac artifact
        uses: actions/upload-artifact@v4
        with:
          name: StudioKit-mac
          path: dist/StudioKit-mac.zip

  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install FFmpeg
        run: |
          choco install ffmpeg -y
          echo "C:\ProgramData\chocolatey\bin" >> $env:GITHUB_PATH

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pyinstaller cython setuptools

      - name: Bundle FFmpeg
        run: |
          mkdir ffmpeg_bin
          copy "C:\ProgramData\chocolatey\bin\ffmpeg.exe" ffmpeg_bin\ffmpeg.exe
          copy "C:\ProgramData\chocolatey\bin\ffprobe.exe" ffmpeg_bin\ffprobe.exe

      - name: Compile Cython extensions
        run: python build_cython.py build_ext --inplace

      - name: Verify compiled extensions exist
        run: |
          dir hypecutter\*.pyd
          dir *.pyd
          dir scene_manager\*.pyd

      - name: Build Windows exe
        run: pyinstaller StudioKit.spec

      - name: Zip Windows exe
        run: Compress-Archive -Path dist\StudioKit -DestinationPath dist\StudioKit-windows.zip

      - name: Upload Windows artifact
        uses: actions/upload-artifact@v4
        with:
          name: StudioKit-windows
          path: dist\StudioKit-windows.zip

  release:
    needs: [build-mac, build-windows]
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Download Mac artifact
        uses: actions/download-artifact@v4
        with:
          name: StudioKit-mac

      - name: Download Windows artifact
        uses: actions/download-artifact@v4
        with:
          name: StudioKit-windows

      - name: Create Release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            StudioKit-mac.zip
            StudioKit-windows.zip
```

- [ ] **Step 2: Commit and push, trigger build**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add .github/workflows/build.yml
git commit -m "ci: add Cython compilation step before PyInstaller"
git push
git tag v1.0.4
git push origin v1.0.4
```

- [ ] **Step 3: Monitor build**

Watch: https://github.com/Torin-2003/StudioKit/actions

Expected: Both Mac and Windows jobs show "Compile Cython extensions" step passing, followed by successful PyInstaller build and Release creation.

---

## Self-Review

**Spec coverage:**
- ✅ `build_cython.py` created — Task 1
- ✅ Local Mac build tested — Task 2
- ✅ `StudioKit.spec` updated to reference compiled extensions — Task 3
- ✅ GitHub Actions updated for Mac + Windows Cython build — Task 4

**Placeholder scan:** None found.

**Type consistency:**
- `collect_cython_extensions()` in spec returns `list[tuple[str, str]]` matching PyInstaller `binaries` format ✅
- `build_cython.py` uses same file paths as spec ✅

**Important notes for implementer:**
- Windows CI needs Visual C++ Build Tools — `windows-latest` runner has it pre-installed ✅
- Mac CI needs Xcode Command Line Tools — `macos-latest` runner has it pre-installed ✅
- Cython 3.x handles `list[str]` annotations natively with `language_level=3` — no source file changes needed ✅
- The `scene_manager/downloader.py`, `metadata.py`, `splitter.py` are NOT compiled (they have fewer secrets, and keeping them as .py reduces risk of import issues)
- `app.py`, `run_app.py`, `hypecutter/ui.py`, `scene_manager/ui.py` are NOT compiled — Streamlit requires these to be importable as normal Python modules
