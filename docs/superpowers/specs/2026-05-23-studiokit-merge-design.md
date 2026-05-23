# StudioKit Merge Design

## Goal

Merge HypeCutter and Spitting Screen (Scene Manager) into one unified Streamlit app called **StudioKit**, with tab-based navigation, a single license gate, pyarmor obfuscation, and automated PyInstaller packaging via GitHub Actions.

## Architecture

Single Streamlit process. `app.py` is the entry point: it runs the license gate, then renders `st.tabs()` with one tab per tool. Each tool's UI logic lives in its own subpackage (`hypecutter/ui.py`, `scene_manager/ui.py`), exposing a single `render()` function. Tools share license infrastructure but have separate config files.

**Tech Stack:** Streamlit, PyInstaller, pyarmor, GitHub Actions, FastAPI (Vercel), Supabase, faster-whisper, scenedetect, yt-dlp, FFmpeg

---

## Project Structure

```
StudioKit/
├── app.py                          # License gate + st.tabs() entry point
├── run_app.py                      # PyInstaller launcher (frozen path + FFmpeg setup)
├── StudioKit.spec                  # PyInstaller spec
├── requirements.txt                # Merged deps from both tools
├── Dockerfile
├── docker-compose.yml
├── .env
├── .github/
│   └── workflows/
│       └── build.yml               # pyarmor → PyInstaller → GitHub Release
├── license/                        # Ed25519 public key
├── license_client.py
├── license_guard.py
├── heartbeat.py
├── paths.py
├── config_client.py
├── db.py
├── hypecutter/
│   ├── __init__.py
│   ├── ui.py                       # render() — all HypeCutter Streamlit UI
│   └── core_engine.py              # AutoHighlightEngine + pipeline classes
└── scene_manager/
    ├── __init__.py
    ├── ui.py                       # render() — all Scene Manager Streamlit UI
    ├── analyzer.py
    ├── classifier.py
    ├── downloader.py
    ├── metadata.py
    └── splitter.py
```

---

## Component Details

### app.py — Entry Point

```python
# License gate (same pattern as HypeCutter/app.py)
_DEV_MODE = os.environ.get("STUDIOKIT_DEV") == "1"
if not _DEV_MODE:
    # verify license, show activation UI if not active
    ...
    st.stop()

st.set_page_config(page_title="StudioKit", page_icon="🎬", layout="wide")

tab_hc, tab_sm = st.tabs(["✂️ HypeCutter", "🎬 Scene Manager"])
with tab_hc:
    from hypecutter.ui import render as render_hc
    render_hc()
with tab_sm:
    from scene_manager.ui import render as render_sm
    render_sm()
```

- License server URL: `https://hype-cutter.vercel.app` (reuse existing Vercel API)
- Dev bypass env var renamed to `STUDIOKIT_DEV` to avoid confusion with old projects
- Sidebar: shared license status card at the bottom (same as HypeCutter)

### hypecutter/ui.py

- Extract all Streamlit UI code from `HypeCutter/app.py` into a `render()` function
- Config file path: `output/hypecutter_config.json`
- All imports of `core_engine` become `from hypecutter.core_engine import ...`
- Session state keys prefixed with `hc_` to avoid collisions with Scene Manager

### hypecutter/core_engine.py

- Direct copy of `HypeCutter/core_engine.py` — no changes needed

### scene_manager/ui.py

- Extract all Streamlit UI code from `Spitting screen/video_manager/app.py` into a `render()` function
- Config file path: `output/scene_manager_config.json` (was `config.json` next to app.py)
- All imports of submodules become `from scene_manager.xxx import ...`
- Session state keys prefixed with `sm_` to avoid collisions with HypeCutter
- `st.set_page_config()` call removed (already called in `app.py`)

### scene_manager/ submodules

- Direct copies of `analyzer.py`, `classifier.py`, `downloader.py`, `metadata.py`, `splitter.py`
- No changes needed except import paths

### requirements.txt (merged)

```
# Streamlit
streamlit>=1.35.0
# Downloader
yt-dlp>=2024.5.1
# Transcription
faster-whisper>=1.0.0
# AI providers
openai>=1.30.0
anthropic>=0.28.0
# Video processing
moviepy>=1.0.3
imageio>=2.34.0
imageio-ffmpeg>=0.4.9
numpy>=1.26.0
# Scene detection (Scene Manager)
scenedetect[opencv]>=0.6.3
opencv-python>=4.9.0
Pillow>=10.0.0
# Utilities
requests>=2.31.0
tqdm>=4.66.0
cryptography>=41.0.0
ffmpeg-python>=0.2.0
```

---

## License Gate

- One license covers both tools — no changes to Vercel API or Supabase schema
- License file stored at same path as HypeCutter (`license/license.json`)
- `license_client.py`, `license_guard.py`, `heartbeat.py` copied unchanged from HypeCutter
- Dev mode env var: `STUDIOKIT_DEV=1` (renamed from `HYPECUTTER_DEV`)

---

## pyarmor + PyInstaller Pipeline

### Local build order
```
1. pyarmor gen --output obfuscated/ app.py run_app.py hypecutter/ scene_manager/ \
       license_client.py license_guard.py heartbeat.py paths.py config_client.py db.py
2. pyinstaller StudioKit.spec  (reads from obfuscated/ sources)
```

### GitHub Actions (build.yml)
Triggered by `v*` tags. Steps:
1. Checkout
2. Install Python deps + pyarmor + PyInstaller
3. Download FFmpeg binary into `ffmpeg_bin/`
4. Run pyarmor obfuscation
5. Run PyInstaller
6. Zip output
7. Upload to GitHub Release

Produces: `StudioKit-mac.zip` and `StudioKit-windows.zip`

### StudioKit.spec
- Same structure as `HypeCutter.spec`
- Adds `scene_manager/` data files
- Adds `copy_metadata` for `scenedetect`, `opencv-python`, `Pillow`
- Entry point: `run_app.py` (obfuscated version)
- `console=True` for debugging builds; `False` for release

---

## run_app.py

Same pattern as HypeCutter:
```python
# Sets up FFmpeg from ffmpeg_bin/ if frozen
# Removes STUDIOKIT_DEV from env if frozen
# Launches streamlit run app.py
```

---

## Data / State

- Downloads: `downloads/`
- HypeCutter output: `output/` (clips)
- Scene Manager output: per-profile folders (user-configured)
- HypeCutter config: `output/hypecutter_config.json`
- Scene Manager config: `output/scene_manager_config.json`
- License: `license/license.json`
- DB: `data/` (HypeCutter project DB)

---

## Update Workflow

When HypeCutter or Spitting screen gets new features:
1. Make changes in the original project folder
2. Tell Claude: "sync HypeCutter changes" or "sync Spitting screen changes"
3. Claude copies changed files into `StudioKit/hypecutter/` or `StudioKit/scene_manager/` and updates imports

---

## Testing

- Run locally: `STUDIOKIT_DEV=1 streamlit run app.py`
- Verify HypeCutter tab: upload a video, check clip generation
- Verify Scene Manager tab: upload a video, check scene splitting
- Verify license gate: unset `STUDIOKIT_DEV`, confirm activation screen appears
- PyInstaller smoke test: run `.exe`/`.app`, verify both tabs load
