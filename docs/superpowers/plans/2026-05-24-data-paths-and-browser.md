# Data Paths & Browser Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all user data (SQLite DB, config JSONs, output clips) to a persistent per-user directory that survives app upgrades, and fix Windows auto-browser-open in PyInstaller bundles.

**Architecture:** `paths.py` is the single source of truth for all data paths. It already has `app_data_dir()` → `~/.hypecutter`. We extend it with `db_path()`, `hc_config_path()`, `sm_config_path()`, `hc_output_dir()`, `sm_output_dir()`, and `downloads_dir()` — all rooted under `app_data_dir()`. Then `db.py`, `hypecutter/ui.py`, and `scene_manager/ui.py` import these instead of using hardcoded relative paths. For browser open, `run_app.py` polls the Streamlit port until it responds before opening, using `subprocess.Popen` on Windows as a fallback.

**Tech Stack:** Python 3.11, pathlib, urllib.request (stdlib only for port polling)

**Key constraint:** `app_data_dir()` already uses `~/.hypecutter` on all platforms — we keep that as the root. On Windows this resolves to `C:\Users\<name>\.hypecutter\`. Output clips go to `~/.hypecutter/output/` and downloads to `~/.hypecutter/downloads/` by default, but users can still override via the UI text field.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `paths.py` | Modify | Add all derived path helpers rooted at `app_data_dir()` |
| `db.py` | Modify | Use `paths.db_path()` instead of hardcoded `Path("data/hypecutter.db")` |
| `hypecutter/ui.py` | Modify | Use `paths.hc_config_path()`, `paths.hc_output_dir()`, `paths.downloads_dir()` |
| `scene_manager/ui.py` | Modify | Use `paths.sm_config_path()` |
| `run_app.py` | Modify | Poll port before opening browser; use `os.startfile` on Windows as fallback |

---

## Task 1: Extend `paths.py` with all data path helpers

**Files:**
- Modify: `paths.py`

- [ ] **Step 1: Replace `paths.py` with extended version**

Create `/Users/torin/Documents/Code Work/StudioKit/paths.py`:

```python
"""Central resolver for persistent file paths.

All user data lives under app_data_dir() so it survives app upgrades.
Override the root with the HYPECUTTER_APP_DATA_DIR env var (useful for Docker).
"""
import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    """Return the per-user app-data dir, creating it if missing.

    Resolution order:
    1. HYPECUTTER_APP_DATA_DIR env var (Docker / CI override)
    2. ~/.hypecutter  (same on Windows, Mac, Linux)
    """
    base = os.environ.get("HYPECUTTER_APP_DATA_DIR")
    if base:
        p = Path(base)
    else:
        p = Path.home() / ".hypecutter"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    """SQLite database path."""
    p = app_data_dir() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p / "hypecutter.db"


def hc_config_path() -> Path:
    """HypeCutter settings JSON path."""
    p = app_data_dir() / "config"
    p.mkdir(parents=True, exist_ok=True)
    return p / "hypecutter_config.json"


def sm_config_path() -> Path:
    """Scene Manager settings JSON path."""
    p = app_data_dir() / "config"
    p.mkdir(parents=True, exist_ok=True)
    return p / "scene_manager_config.json"


def hc_output_dir() -> Path:
    """Default output directory for HypeCutter clips."""
    p = app_data_dir() / "output"
    p.mkdir(parents=True, exist_ok=True)
    return p


def downloads_dir() -> Path:
    """Temporary downloads directory."""
    p = app_data_dir() / "downloads"
    p.mkdir(parents=True, exist_ok=True)
    return p
```

- [ ] **Step 2: Verify syntax**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python3 -c "import ast; ast.parse(open('paths.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Smoke-test all helpers**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python3 -c "
from paths import app_data_dir, db_path, hc_config_path, sm_config_path, hc_output_dir, downloads_dir
import os
print('app_data_dir:', app_data_dir())
print('db_path:', db_path())
print('hc_config:', hc_config_path())
print('sm_config:', sm_config_path())
print('hc_output:', hc_output_dir())
print('downloads:', downloads_dir())
# All should be under ~/.hypecutter
base = str(app_data_dir())
assert str(db_path()).startswith(base)
assert str(hc_config_path()).startswith(base)
assert str(sm_config_path()).startswith(base)
assert str(hc_output_dir()).startswith(base)
assert str(downloads_dir()).startswith(base)
print('All paths under app_data_dir: OK')
"
```

Expected:
```
app_data_dir: /Users/<name>/.hypecutter
db_path: /Users/<name>/.hypecutter/data/hypecutter.db
hc_config: /Users/<name>/.hypecutter/config/hypecutter_config.json
sm_config: /Users/<name>/.hypecutter/config/scene_manager_config.json
hc_output: /Users/<name>/.hypecutter/output
downloads: /Users/<name>/.hypecutter/downloads
All paths under app_data_dir: OK
```

- [ ] **Step 4: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add paths.py
git commit -m "feat: extend paths.py with db, config, output, downloads helpers"
```

---

## Task 2: Update `db.py` to use `paths.db_path()`

**Files:**
- Modify: `db.py`

- [ ] **Step 1: Read current `db.py` top section**

```bash
head -35 "/Users/torin/Documents/Code Work/StudioKit/db.py"
```

- [ ] **Step 2: Replace the `DB_PATH` line and `_ensure_dir` function**

Find these lines in `db.py`:
```python
DB_PATH = Path("data/hypecutter.db")


def _ensure_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
```

Replace with:
```python
from paths import db_path as _db_path

DB_PATH = _db_path()


def _ensure_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 3: Verify syntax**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python3 -c "import ast; ast.parse(open('db.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Verify DB path resolves correctly**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python3 -c "import db; print('DB_PATH:', db.DB_PATH); assert '.hypecutter' in str(db.DB_PATH); print('OK')"
```

Expected: `DB_PATH: /Users/<name>/.hypecutter/data/hypecutter.db` and `OK`

- [ ] **Step 5: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add db.py
git commit -m "fix: db.py uses paths.db_path() instead of relative data/hypecutter.db"
```

---

## Task 3: Update `hypecutter/ui.py` to use persistent paths

**Files:**
- Modify: `hypecutter/ui.py`

Three changes needed:
1. `_HC_CONFIG_FILE = Path("output/hypecutter_config.json")` → use `paths.hc_config_path()`
2. `output_dir="output"` in `_make_engine()` → use `paths.hc_output_dir()`
3. `downloads_dir="downloads"` in `_make_engine()` → use `paths.downloads_dir()`

- [ ] **Step 1: Find exact lines**

```bash
grep -n "_HC_CONFIG_FILE\|output_dir=\|downloads_dir=" "/Users/torin/Documents/Code Work/StudioKit/hypecutter/ui.py"
```

- [ ] **Step 2: Replace `_HC_CONFIG_FILE` definition**

Find:
```python
_HC_CONFIG_FILE = Path("output/hypecutter_config.json")
```

Replace with:
```python
from paths import hc_config_path as _hc_config_path, hc_output_dir as _hc_output_dir, downloads_dir as _hc_downloads_dir
_HC_CONFIG_FILE = _hc_config_path()
```

- [ ] **Step 3: Replace `_make_engine()` output and downloads dirs**

Find:
```python
        downloads_dir="downloads",
        output_dir="output",
```

Replace with:
```python
        downloads_dir=str(_hc_downloads_dir()),
        output_dir=str(_hc_output_dir()),
```

- [ ] **Step 4: Verify syntax**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python3 -c "import ast; ast.parse(open('hypecutter/ui.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Verify config path resolves correctly**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python3 -c "
import hypecutter.ui as u
print('config:', u._HC_CONFIG_FILE)
assert '.hypecutter' in str(u._HC_CONFIG_FILE)
print('OK')
"
```

Expected: path contains `.hypecutter` and `OK`

- [ ] **Step 6: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add hypecutter/ui.py
git commit -m "fix: hypecutter/ui.py uses persistent paths for config, output, downloads"
```

---

## Task 4: Update `scene_manager/ui.py` to use persistent config path

**Files:**
- Modify: `scene_manager/ui.py`

- [ ] **Step 1: Find exact line**

```bash
grep -n "CONFIG_PATH" "/Users/torin/Documents/Code Work/StudioKit/scene_manager/ui.py" | head -5
```

- [ ] **Step 2: Replace `CONFIG_PATH` definition**

Find:
```python
CONFIG_PATH = Path("output/scene_manager_config.json")
```

Replace with:
```python
from paths import sm_config_path as _sm_config_path
CONFIG_PATH = _sm_config_path()
```

- [ ] **Step 3: Verify syntax**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python3 -c "import ast; ast.parse(open('scene_manager/ui.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Verify config path**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python3 -c "
import scene_manager.ui as u
print('config:', u.CONFIG_PATH)
assert '.hypecutter' in str(u.CONFIG_PATH)
print('OK')
"
```

Expected: path contains `.hypecutter` and `OK`

- [ ] **Step 5: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add scene_manager/ui.py
git commit -m "fix: scene_manager/ui.py uses persistent path for config"
```

---

## Task 5: Fix Windows auto-browser open in `run_app.py`

**Files:**
- Modify: `run_app.py`

The current approach (`time.sleep(3)` then `webbrowser.open`) fails on Windows in PyInstaller bundles because:
1. 3 seconds may not be enough for Streamlit to start
2. `webbrowser` sometimes has no registered browser on Windows frozen apps

Fix: poll `http://localhost:8501` until it responds (up to 30s), then use `os.startfile` on Windows or `webbrowser.open` on Mac/Linux.

- [ ] **Step 1: Replace `run_app.py` with fixed version**

Create `/Users/torin/Documents/Code Work/StudioKit/run_app.py`:

```python
import sys
import os
from pathlib import Path


def get_app_path():
    if getattr(sys, "frozen", False):
        return str(Path(sys._MEIPASS) / "app.py")
    return str(Path(__file__).parent / "app.py")


def setup_ffmpeg():
    if getattr(sys, "frozen", False):
        ffmpeg_dir = Path(sys._MEIPASS) / "ffmpeg_bin"
        if ffmpeg_dir.exists():
            os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")


def _open_browser_when_ready(url: str, timeout: int = 30) -> None:
    """Poll url until it responds (up to timeout seconds), then open browser."""
    import time
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            break  # server is up
        except Exception:
            time.sleep(0.5)

    # Open browser — os.startfile is more reliable in Windows frozen bundles
    if sys.platform == "win32":
        os.startfile(url)  # type: ignore[attr-defined]
    else:
        import webbrowser
        webbrowser.open(url)


if __name__ == "__main__":
    setup_ffmpeg()
    if getattr(sys, "frozen", False):
        os.environ.pop("STUDIOKIT_DEV", None)

    import threading
    t = threading.Thread(
        target=_open_browser_when_ready,
        args=("http://localhost:8501",),
        daemon=True,
    )
    t.start()

    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run", get_app_path(),
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--global.developmentMode=false",
    ]
    sys.exit(stcli.main())
```

- [ ] **Step 2: Verify syntax**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python3 -c "import ast; ast.parse(open('run_app.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add run_app.py
git commit -m "fix: poll port before opening browser; use os.startfile on Windows"
```

---

## Task 6: Push and tag v1.0.6

- [ ] **Step 1: Push and tag**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git push
git tag v1.0.6
git push origin v1.0.6
```

- [ ] **Step 2: Confirm tag pushed**

```bash
git tag --list | grep v1.0.6
```

Expected: `v1.0.6`

---

## Self-Review

**Spec coverage:**
- ✅ DB path moved to `~/.hypecutter/data/` — Task 2
- ✅ HypeCutter config moved to `~/.hypecutter/config/` — Task 3
- ✅ Scene Manager config moved to `~/.hypecutter/config/` — Task 4
- ✅ HypeCutter output/downloads moved to `~/.hypecutter/output|downloads/` — Task 3
- ✅ Windows browser open fixed — Task 5
- ✅ All helpers in single `paths.py` — Task 1

**Placeholder scan:** None found.

**Type consistency:**
- All path helpers return `Path`, callers that need `str` use `str()` explicitly ✅
- `_HC_CONFIG_FILE` stays a `Path` object (no str conversion needed, `Path.read_text()` works) ✅
- `CONFIG_PATH` in scene_manager stays a `Path` object ✅

**Important notes for implementer:**
- `from paths import ...` must be added at module level (top of file), not inside a function
- The `Path("output/...")` relative paths in `_load_config` / `_save_config` display strings (`_out_display`, `_out2_display`) in hypecutter/ui.py are for UI display only — they show the resolved absolute path to the user. These do NOT need changing since they just call `Path("output").resolve()` which will show wherever the CWD is. Those display strings are cosmetic only; the actual engine gets the correct absolute path from `_hc_output_dir()`.
- On first upgrade: users' old `output/` relative folder (from previous installs) still exists in their old app dir. New clips go to `~/.hypecutter/output/`. Old clips are not migrated — this is acceptable since old app dir may be a different folder.
