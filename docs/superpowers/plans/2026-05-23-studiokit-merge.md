# StudioKit Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge HypeCutter and Spitting Screen (Scene Manager) into one Streamlit app called StudioKit with tab-based navigation, a single license gate, pyarmor obfuscation, and automated PyInstaller builds via GitHub Actions.

**Architecture:** Single Streamlit process — `app.py` runs the license gate then renders `st.tabs()`. Each tool's UI is in its own subpackage (`hypecutter/ui.py`, `scene_manager/ui.py`) exposing a `render()` function. License infrastructure is shared; configs are separate files per tool.

**Tech Stack:** Python 3.11, Streamlit ≥1.35, PyInstaller, pyarmor, GitHub Actions, faster-whisper, scenedetect, yt-dlp, FFmpeg, OpenAI/Anthropic APIs

**Source files to copy from:**
- `/Users/torin/Documents/Code Work/HypeCutter/` — HypeCutter source
- `/Users/torin/Documents/Code Work/Spitting screen/video_manager/` — Scene Manager source

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app.py` | Create | License gate + `st.tabs()` entry point |
| `run_app.py` | Create | PyInstaller launcher (frozen path + FFmpeg setup) |
| `StudioKit.spec` | Create | PyInstaller spec |
| `requirements.txt` | Create | Merged deps from both tools |
| `Dockerfile` | Create | Docker image |
| `docker-compose.yml` | Create | Docker compose |
| `.env` | Create | Local dev env vars |
| `.github/workflows/build.yml` | Create | pyarmor → PyInstaller → Release |
| `hypecutter/__init__.py` | Create | Empty package marker |
| `hypecutter/ui.py` | Create | HypeCutter UI extracted into `render()` |
| `hypecutter/core_engine.py` | Copy | Copy of HypeCutter/core_engine.py |
| `scene_manager/__init__.py` | Create | Empty package marker |
| `scene_manager/ui.py` | Create | Scene Manager UI extracted into `render()` |
| `scene_manager/analyzer.py` | Copy | Copy of Spitting screen analyzer.py |
| `scene_manager/classifier.py` | Copy | Copy of Spitting screen classifier.py |
| `scene_manager/downloader.py` | Copy | Copy of Spitting screen downloader.py |
| `scene_manager/metadata.py` | Copy | Copy of Spitting screen metadata.py |
| `scene_manager/splitter.py` | Copy | Copy of Spitting screen splitter.py |
| `license_client.py` | Copy | Copy of HypeCutter/license_client.py |
| `license_guard.py` | Copy | Copy of HypeCutter/license_guard.py |
| `heartbeat.py` | Copy | Copy of HypeCutter/heartbeat.py |
| `paths.py` | Copy | Copy of HypeCutter/paths.py |
| `config_client.py` | Copy | Copy of HypeCutter/config_client.py |
| `db.py` | Copy | Copy of HypeCutter/db.py |
| `license/` | Copy | Copy of HypeCutter/license/ directory |

---

## Task 1: Create StudioKit folder skeleton + copy shared files

**Files:**
- Create: `StudioKit/` root directory and all subdirectories
- Copy from HypeCutter: `license_client.py`, `license_guard.py`, `heartbeat.py`, `paths.py`, `config_client.py`, `db.py`, `license/`
- Copy from HypeCutter: `core_engine.py` → `hypecutter/core_engine.py`
- Copy from Scene Manager: `analyzer.py`, `classifier.py`, `downloader.py`, `metadata.py`, `splitter.py` → `scene_manager/`

- [ ] **Step 1: Create directory structure**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
mkdir -p hypecutter scene_manager license .github/workflows downloads output data/projects
```

- [ ] **Step 2: Copy shared license infrastructure files**

```bash
HC="/Users/torin/Documents/Code Work/HypeCutter"
SK="/Users/torin/Documents/Code Work/StudioKit"
cp "$HC/license_client.py" "$SK/"
cp "$HC/license_guard.py" "$SK/"
cp "$HC/heartbeat.py" "$SK/"
cp "$HC/paths.py" "$SK/"
cp "$HC/config_client.py" "$SK/"
cp "$HC/db.py" "$SK/"
cp -r "$HC/license/" "$SK/license/"
```

- [ ] **Step 3: Copy core engine and scene manager submodules**

```bash
HC="/Users/torin/Documents/Code Work/HypeCutter"
SM="/Users/torin/Documents/Code Work/Spitting screen/video_manager"
SK="/Users/torin/Documents/Code Work/StudioKit"
cp "$HC/core_engine.py" "$SK/hypecutter/core_engine.py"
cp "$SM/analyzer.py"    "$SK/scene_manager/analyzer.py"
cp "$SM/classifier.py"  "$SK/scene_manager/classifier.py"
cp "$SM/downloader.py"  "$SK/scene_manager/downloader.py"
cp "$SM/metadata.py"    "$SK/scene_manager/metadata.py"
cp "$SM/splitter.py"    "$SK/scene_manager/splitter.py"
```

- [ ] **Step 4: Create empty package `__init__.py` files**

Create `hypecutter/__init__.py`:
```python
```

Create `scene_manager/__init__.py`:
```python
```

- [ ] **Step 5: Verify structure**

```bash
find "/Users/torin/Documents/Code Work/StudioKit" -not -path "*/\.*" -not -path "*/venv/*" -not -path "*/__pycache__/*" | sort
```

Expected: all directories and copied files listed.

- [ ] **Step 6: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git init
git add .
git commit -m "chore: scaffold StudioKit, copy shared files and submodules"
```

---

## Task 2: Create `requirements.txt` and `.env`

**Files:**
- Create: `requirements.txt`
- Create: `.env`
- Create: `.gitignore`

- [ ] **Step 1: Create merged `requirements.txt`**

Create `requirements.txt`:
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

- [ ] **Step 2: Create `.env`**

Create `.env`:
```
HOST_OUTPUT_PATH=/Users/torin/Documents/Code Work/StudioKit/output
STUDIOKIT_DEV=1
```

- [ ] **Step 3: Create `.gitignore`**

Create `.gitignore`:
```
__pycache__/
*.pyc
*.pyo
.env
downloads/
output/
data/
venv/
.venv/
dist/
build/
*.spec.bak
ffmpeg_bin/
obfuscated/
license/license.json
```

- [ ] **Step 4: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add requirements.txt .env .gitignore
git commit -m "chore: add requirements.txt, .env, .gitignore"
```

---

## Task 3: Create `hypecutter/ui.py` — extract HypeCutter UI into `render()`

**Files:**
- Create: `hypecutter/ui.py`
- Source: `/Users/torin/Documents/Code Work/HypeCutter/app.py` lines 1–939

This task extracts everything from HypeCutter's `app.py` except the license gate and `st.set_page_config()` call, wraps it in a `render()` function, and fixes two things:
1. `from core_engine import` → `from hypecutter.core_engine import`
2. Config file path: `Path("output/config.json")` → `Path("output/hypecutter_config.json")`

- [ ] **Step 1: Create `hypecutter/ui.py` with correct imports and config path**

Create `hypecutter/ui.py` — full content:

```python
"""HypeCutter UI — called from StudioKit app.py as render()."""

import json
import logging
import os
import re
import shutil
from pathlib import Path

import streamlit as st

import db as _db
from hypecutter.core_engine import AutoHighlightEngine

# ── Config ────────────────────────────────────────────────────────────────────
_CONFIG_FILE = Path("output/hypecutter_config.json")


@st.cache_data(ttl=60)
def _hc_load_config() -> dict:
    try:
        if _CONFIG_FILE.exists():
            return json.loads(_CONFIG_FILE.read_text())
    except Exception:
        pass
    return {}


def _hc_save_config(data: dict):
    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(data, indent=2))
    _hc_load_config.clear()


_RANGE_PRESETS: dict[str, tuple[int, int]] = {
    "Short (Under 30s)": (5, 30),
    "Standard (30s - 60s)": (30, 60),
    "Extended (60s - 90s)": (60, 90),
    "Deep-Dive (90s - 3min)": (90, 180),
    "Long-form (3min+)": (180, 600),
}

_CFG_DEFAULTS = {
    "hc_cfg_provider": "OpenAI",
    "hc_cfg_api_key": os.environ.get("OPENAI_API_KEY", "")
    or os.environ.get("ANTHROPIC_API_KEY", ""),
    "hc_cfg_base_url": "",
    "hc_cfg_llm_model": "",
    "hc_cfg_duration_mode": "Fixed Duration",
    "hc_cfg_target_duration": 60,
    "hc_cfg_duration_range": "Standard (30s - 60s)",
    "hc_cfg_n_clips": 5,
    "hc_cfg_vertical": True,
    "hc_cfg_smart_mode": False,
    "hc_cfg_condense_mode": False,
    "hc_cfg_burn_subtitles": True,
    "hc_cfg_remove_silence": False,
    "hc_cfg_max_resolution": "720p",
    "hc_cfg_auto_delete_source": True,
    "hc_cfg_whisper_model": "base",
    "hc_cfg_language": "",
    "hc_cfg_font_path": "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
}

_PROFILE_CFG_KEYS = [
    "hc_cfg_openai_key", "hc_cfg_openai_base_url", "hc_cfg_openai_model",
    "hc_cfg_gemini_key", "hc_cfg_gemini_base_url", "hc_cfg_gemini_model",
    "hc_cfg_anthropic_key", "hc_cfg_anthropic_base_url", "hc_cfg_anthropic_model",
]


def _hc_init_state():
    saved = _hc_load_config()
    for k, v in _CFG_DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = saved.get(k, v)
    for k in _PROFILE_CFG_KEYS:
        if k not in st.session_state:
            st.session_state[k] = saved.get(k, "")
    for k, v in {
        "hc_results": [],
        "hc_processing": False,
        "hc_log_lines": [],
        "hc_url_sources": [],
        "hc_file_sources": [],
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _hc_status_badge(status: str) -> str:
    return {"completed": "✅", "failed": "❌", "processing": "⏳"}.get(status, "❓")


def _hc_render_clip_card(clip: dict, key_prefix: str) -> None:
    score = float(clip.get("score", 0))
    hook = float(clip.get("hook_strength", 0))
    badge = "🟢" if score >= 8 else ("🟡" if score >= 6 else "🔴")
    st.markdown(f"**{clip['title']}**")
    clip_type = (
        f"🔀 Condensed ({clip['segment_count']} segments)"
        if clip.get("condensed")
        else "▶ Continuous"
    )
    st.markdown(
        f"{badge} Viral Score: **{score:.1f}**  |  🪝 Hook: **{hook:.1f}** / 10  |  {clip_type}"
    )
    dur = clip.get("duration") or (clip["end"] - clip["start"])
    st.caption(f"⏱️ {clip['start']:.1f}s → {clip['end']:.1f}s  ({dur:.0f}s)")
    out_path = clip.get("output_path")
    if out_path and Path(out_path).exists():
        st.video(out_path)
        with open(out_path, "rb") as fh:
            st.download_button(
                label="⬇️ Download",
                data=fh,
                file_name=Path(out_path).name,
                mime="video/mp4",
                use_container_width=True,
                key=f"{key_prefix}_dl_{out_path}",
            )
    elif clip.get("error"):
        st.error(f"Render failed: {clip['error']}")
    else:
        st.warning("Output file not found.")


def _hc_render_project_history() -> None:
    projects = _db.list_projects(limit=20)
    if not projects:
        st.info("No projects yet.")
        return
    for proj in projects:
        with st.expander(f"{_hc_status_badge(proj['status'])} {proj['name']} — {proj['created_at'][:16]}"):
            clips = _db.list_clips(proj["id"])
            if not clips:
                st.caption("No clips saved.")
                continue
            for clip in clips:
                _hc_render_clip_card(clip, key_prefix=f"hist_{proj['id']}")
                st.divider()


@st.cache_resource(show_spinner="Loading Whisper model…")
def _hc_get_engine(provider_: str, api_key_: str, llm_model_: str, whisper_model_: str, base_url_: str):
    return AutoHighlightEngine(
        provider=provider_.lower(),
        api_key=api_key_,
        llm_model=llm_model_.strip(),
        whisper_model=whisper_model_,
        base_url=base_url_.strip(),
        downloads_dir="downloads",
        output_dir="output",
    )


def render():
    """Render the HypeCutter tab. Called from StudioKit app.py."""
    _hc_init_state()
    _db.init_db()

    # ── Sidebar settings ─────────────────────────────────────────
    _PROFILE_KEYS = {
        "OpenAI":    ("hc_cfg_openai_key",    "hc_cfg_openai_base_url",    "hc_cfg_openai_model"),
        "Gemini":    ("hc_cfg_gemini_key",    "hc_cfg_gemini_base_url",    "hc_cfg_gemini_model"),
        "Anthropic": ("hc_cfg_anthropic_key", "hc_cfg_anthropic_base_url", "hc_cfg_anthropic_model"),
    }
    _BASE_URL_PLACEHOLDERS = {
        "OpenAI":    "https://api.narroai.com/v1  (leave blank for official)",
        "Gemini":    "https://generativelanguage.googleapis.com/v1beta/openai/",
        "Anthropic": "(leave blank for official Anthropic)",
    }
    _MODEL_PLACEHOLDERS = {
        "OpenAI":    "gpt-4o  /  gpt-4.1-nano-2025-04-14  (blank = gpt-4o)",
        "Gemini":    "gemini-2.0-flash  /  gemini-2.5-flash-preview-04-17  (blank = gemini-2.0-flash)",
        "Anthropic": "claude-3-5-sonnet-20241022  (blank = default)",
    }
    _PROVIDERS = ["OpenAI", "Gemini", "Anthropic"]

    with st.sidebar:
        st.subheader("✂️ HypeCutter Settings")

        def _on_provider_change():
            prov = st.session_state["hc_sb_provider"]
            _kk, _kb, _km = _PROFILE_KEYS[prov]
            _p2 = prov.lower()
            st.session_state[f"hc_sb_api_key_{_p2}"]   = st.session_state.get(_kk) or ""
            st.session_state[f"hc_sb_base_url_{_p2}"]  = st.session_state.get(_kb) or ""
            st.session_state[f"hc_sb_llm_model_{_p2}"] = st.session_state.get(_km) or ""

        provider = st.selectbox(
            "LLM Provider", _PROVIDERS,
            index=_PROVIDERS.index(st.session_state.hc_cfg_provider)
            if st.session_state.hc_cfg_provider in _PROVIDERS else 0,
            key="hc_sb_provider", on_change=_on_provider_change,
        )
        _k_key, _k_base, _k_model = _PROFILE_KEYS[provider]
        _p = provider.lower()
        if f"hc_sb_api_key_{_p}" not in st.session_state:
            st.session_state[f"hc_sb_api_key_{_p}"]   = st.session_state.get(_k_key) or st.session_state.hc_cfg_api_key
            st.session_state[f"hc_sb_base_url_{_p}"]  = st.session_state.get(_k_base) or ""
            st.session_state[f"hc_sb_llm_model_{_p}"] = st.session_state.get(_k_model) or ""

        api_key  = st.text_input("API Key", type="password", key=f"hc_sb_api_key_{_p}")
        base_url = st.text_input("Base URL", placeholder=_BASE_URL_PLACEHOLDERS.get(provider, ""), key=f"hc_sb_base_url_{_p}")
        llm_model = st.text_input("LLM Model (blank = default)", placeholder=_MODEL_PLACEHOLDERS.get(provider, ""), key=f"hc_sb_llm_model_{_p}")

        if st.button("💾 Save API Profile", key="hc_save_profile", use_container_width=True):
            st.session_state[_k_key]   = api_key
            st.session_state[_k_base]  = base_url
            st.session_state[_k_model] = llm_model
            saved_cfg = _hc_load_config()
            saved_cfg.update({_k_key: api_key, _k_base: base_url, _k_model: llm_model})
            _hc_save_config(saved_cfg)
            st.success(f"✅ {provider} profile saved.")

        st.divider()
        st.subheader("🎬 Clip Settings")

        duration_mode = st.radio(
            "Duration Mode", ["Fixed Duration", "Range-Based (AI Optimized)"],
            index=["Fixed Duration", "Range-Based (AI Optimized)"].index(st.session_state.hc_cfg_duration_mode),
            key="hc_sb_duration_mode", horizontal=True,
        )
        range_lo, range_hi = 30, 60
        target_duration = st.session_state.hc_cfg_target_duration

        if duration_mode == "Fixed Duration":
            dur_col1, dur_col2 = st.columns([3, 1])
            with dur_col1:
                target_duration = st.slider("Target duration (s)", 15, 180, value=st.session_state.hc_cfg_target_duration, step=5, key="hc_sb_dur_slider")
            with dur_col2:
                target_duration_num = st.number_input("s", min_value=15, max_value=180, value=target_duration, step=1, key="hc_sb_dur_num")
            if target_duration_num != target_duration:
                target_duration = target_duration_num
            duration_range = st.session_state.hc_cfg_duration_range
        else:
            duration_range = st.radio("Duration Range", list(_RANGE_PRESETS.keys()),
                index=list(_RANGE_PRESETS.keys()).index(st.session_state.hc_cfg_duration_range), key="hc_sb_duration_range")
            range_lo, range_hi = _RANGE_PRESETS[duration_range]
            st.caption(f"🎯 AI will find the natural semantic endpoint within **{range_lo}s – {range_hi}s**.")

        smart_mode = st.toggle("🧠 Smart Count", value=st.session_state.hc_cfg_smart_mode, key="hc_sb_smart_mode")
        n_clips = st.slider("Max clips" if smart_mode else "Number of clips", 1, 20, value=st.session_state.hc_cfg_n_clips, key="hc_sb_n_clips")
        condense_mode = st.toggle("🧩 Condense Mode", value=st.session_state.hc_cfg_condense_mode, key="hc_sb_condense_mode")
        vertical = st.toggle("Vertical 9:16 output", value=st.session_state.hc_cfg_vertical, key="hc_sb_vertical")
        burn_subtitles = st.checkbox("🔤 Burn-in Subtitles", value=st.session_state.hc_cfg_burn_subtitles, key="hc_sb_burn_subtitles")
        remove_silence = st.checkbox("🔇 Auto-remove Silence", value=st.session_state.hc_cfg_remove_silence, key="hc_sb_remove_silence")

        st.divider()
        st.subheader("⬇️ Download Settings")
        resolution_options = ["1080p", "720p", "480p"]
        max_resolution = st.selectbox("Max download resolution", resolution_options,
            index=resolution_options.index(st.session_state.hc_cfg_max_resolution), key="hc_sb_max_resolution")
        auto_delete_source = st.checkbox("🗑️ Auto-delete source after processing",
            value=st.session_state.hc_cfg_auto_delete_source, key="hc_sb_auto_delete_source")

        st.divider()
        st.subheader("🎙️ Whisper Model")
        whisper_options = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
        whisper_model = st.selectbox("Model size", whisper_options,
            index=whisper_options.index(st.session_state.hc_cfg_whisper_model), key="hc_sb_whisper_model")
        language = st.text_input("Language code (optional)", value=st.session_state.hc_cfg_language,
            placeholder="en / zh / ja …", key="hc_sb_language")

        st.divider()
        st.subheader("🔤 CJK Font (Docker)")
        font_path_input = st.text_input("Font file path", value=st.session_state.hc_cfg_font_path, key="hc_sb_font_path")

        st.divider()
        if st.button("💾 Save Configuration", key="hc_save_cfg", use_container_width=True):
            cfg = {
                "hc_cfg_provider": provider, "hc_cfg_api_key": api_key,
                "hc_cfg_base_url": base_url, "hc_cfg_llm_model": llm_model,
                "hc_cfg_duration_mode": duration_mode, "hc_cfg_target_duration": target_duration,
                "hc_cfg_duration_range": duration_range, "hc_cfg_n_clips": n_clips,
                "hc_cfg_vertical": vertical, "hc_cfg_smart_mode": smart_mode,
                "hc_cfg_condense_mode": condense_mode, "hc_cfg_burn_subtitles": burn_subtitles,
                "hc_cfg_remove_silence": remove_silence, "hc_cfg_max_resolution": max_resolution,
                "hc_cfg_auto_delete_source": auto_delete_source,
                "hc_cfg_whisper_model": whisper_model, "hc_cfg_language": language,
                "hc_cfg_font_path": font_path_input,
            }
            for k, v in cfg.items():
                st.session_state[k] = v
            _hc_save_config(cfg)
            st.success("✅ Saved.")

    # ── Main area ────────────────────────────────────────────────
    st.title("✂️ HypeCutter")
    st.caption("Automatically extract ranked viral clips from long-form videos — powered by AI.")

    tab_url, tab_file, tab_history = st.tabs(["🔗 URL Input", "📂 Local File Upload", "📋 Project History"])

    with tab_url:
        url_text = st.text_area("Enter video URL(s) — one per line", height=110,
            placeholder="https://www.youtube.com/watch?v=...", key="hc_url_textarea")
        st.session_state.hc_url_sources = (
            [u.strip() for u in url_text.splitlines() if u.strip()] if url_text.strip() else []
        )

    with tab_file:
        uploaded = st.file_uploader("Upload video file(s)", type=["mp4", "mov", "avi", "mkv", "webm"],
            accept_multiple_files=True, key="hc_file_uploader")
        if uploaded:
            upload_dir = Path("downloads")
            upload_dir.mkdir(exist_ok=True)
            saved = []
            for f in uploaded:
                dest = upload_dir / f.name
                if not dest.exists():
                    dest.write_bytes(f.read())
                saved.append(str(dest))
            st.session_state.hc_file_sources = saved
            st.success(f"Ready: {len(saved)} file(s)")
        else:
            st.session_state.hc_file_sources = []

    with tab_history:
        _hc_render_project_history()

    all_sources = st.session_state.hc_url_sources + st.session_state.hc_file_sources
    st.divider()

    col_run, col_clear = st.columns([5, 1])
    with col_run:
        run_btn = st.button("🚀 Start Processing", type="primary", use_container_width=True,
            disabled=(not all_sources or st.session_state.hc_processing), key="hc_run_btn")
    with col_clear:
        if st.button("🗑️ Clear", use_container_width=True, key="hc_clear_btn"):
            st.session_state.hc_results = []
            st.session_state.hc_log_lines = []
            st.rerun()

    STAGE_PCT = {
        "⬇️ Downloading": 0.08, "✅ Video ready": 0.15, "🔇 Removing": 0.20,
        "✅ Silence": 0.25, "🎙️ Transcribing": 0.28, "✅ Transcription": 0.55,
        "🧠 AI analyzing": 0.60, "✅ Found": 0.68, "🎬 Rendering": 0.72, "🎉 All clips": 1.00,
    }

    if run_btn:
        if not api_key:
            st.error("Enter your API key in the sidebar first.")
            st.stop()

        st.session_state.hc_processing = True
        st.session_state.hc_results = []
        st.session_state.hc_log_lines = []

        engine = _hc_get_engine(provider, api_key, llm_model, whisper_model, base_url)
        progress_bar = st.progress(0.0, text="Starting…")
        status_placeholder = st.empty()
        log_placeholder = st.empty()

        def status_cb(msg: str):
            st.session_state.hc_log_lines.append(msg)
            status_placeholder.info(msg)
            for key, pct in STAGE_PCT.items():
                if key in msg:
                    progress_bar.progress(pct, text=msg[:90])
                    break
            log_placeholder.code("\n".join(st.session_state.hc_log_lines[-6:]))

        _settings_snapshot = {
            "duration_mode": duration_mode, "target_duration": target_duration,
            "duration_range": duration_range, "range_lo": range_lo, "range_hi": range_hi,
            "n_clips": n_clips, "smart_mode": smart_mode, "condense_mode": condense_mode,
            "whisper_model": whisper_model, "vertical": vertical, "max_resolution": max_resolution,
        }

        all_results = []
        for idx, src in enumerate(all_sources):
            label = Path(src).name if not src.startswith("http") else src[:70]
            st.markdown(f"#### 📹 Source {idx + 1}: `{label}`")
            is_url = src.startswith(("http://", "https://"))
            proj_id = _db.create_project(
                name=label, source_url=src if is_url else "",
                source_path="" if is_url else src, settings=_settings_snapshot,
            )

            def _clip_saved(clip: dict, _pid: str = proj_id) -> None:
                _db.save_clip(_pid, clip)

            try:
                res = engine.process(
                    source=src, target_duration=target_duration, n_clips=n_clips,
                    vertical=vertical, language=language.strip() or None,
                    font_path=font_path_input.strip() or None,
                    burn_subtitles=burn_subtitles, remove_silence=remove_silence,
                    smart_mode=smart_mode, condense_mode=condense_mode,
                    range_mode=(duration_mode == "Range-Based (AI Optimized)"),
                    range_label=duration_range, range_lo=range_lo, range_hi=range_hi,
                    max_resolution=int(max_resolution.replace("p", "")),
                    auto_delete_source=auto_delete_source,
                    status_callback=status_cb, clip_saved_callback=_clip_saved,
                )
                all_results.extend(res)
                _db.update_project_status(proj_id, "completed")
                progress_bar.progress(1.0, text="✅ Done!")
            except Exception as e:
                _db.update_project_status(proj_id, "failed")
                st.error(f"❌ Failed: {e}")
                logging.exception("Processing error")

        st.session_state.hc_results = all_results
        st.session_state.hc_processing = False
        status_placeholder.empty()

    # ── Results gallery ──────────────────────────────────────────
    if st.session_state.hc_results:
        st.divider()
        _hdr_col, _btn_col = st.columns([4, 1])
        with _hdr_col:
            st.subheader("🏆 Generated Clips")
        with _btn_col:
            _host_out = os.environ.get("HOST_OUTPUT_PATH", "")
            _out_display = _host_out if _host_out else str(Path("output").resolve())
            if st.button("📂 Open Folder", use_container_width=True, key="hc_open_folder"):
                st.info(f"📁 **Output path:**\n\n`{_out_display}`")

        results = st.session_state.hc_results
        cols_per_row = 2
        for i in range(0, len(results), cols_per_row):
            row = results[i: i + cols_per_row]
            cols = st.columns(cols_per_row)
            for col, res in zip(cols, row):
                with col:
                    _hc_render_clip_card(res, key_prefix=f"res_{i}")
                    st.divider()
```

- [ ] **Step 2: Verify the file is syntactically valid**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python -c "import ast; ast.parse(open('hypecutter/ui.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add hypecutter/ui.py
git commit -m "feat: add hypecutter/ui.py with render() function"
```

---

## Task 4: Create `scene_manager/ui.py` — extract Scene Manager UI into `render()`

**Files:**
- Create: `scene_manager/ui.py`
- Source: `/Users/torin/Documents/Code Work/Spitting screen/video_manager/app.py` lines 1–1156

Extract all UI code into a `render()` function. Key changes:
1. Remove `st.set_page_config()` (already called in `app.py`)
2. Config path: `Path(__file__).parent / "config.json"` → `Path("output/scene_manager_config.json")`
3. All `from xxx import` → `from scene_manager.xxx import`
4. All session state keys prefixed with `sm_`
5. All widget `key=` parameters prefixed with `sm_`

- [ ] **Step 1: Create `scene_manager/ui.py`**

Create `scene_manager/ui.py`:

```python
"""Scene Manager UI — called from StudioKit app.py as render()."""

import base64
import csv
import io
import json
import os
import shutil
import tempfile
from pathlib import Path

import streamlit as st
from openai import OpenAI

from scene_manager.metadata import (
    compute_file_hash, is_already_processed, register_processed_video,
    list_existing_folders, load_folder_metadata, save_folder_metadata,
    remove_clip_from_metadata, update_clip_in_metadata,
)
from scene_manager.splitter import detect_scenes, split_video, extract_frames
from scene_manager.analyzer import analyze_clip_frames, cleanup_frames
from scene_manager.classifier import resolve_target_folder, place_clip
from scene_manager.downloader import (
    check_ytdlp, get_video_info, download_video,
    is_valid_url, check_disk_space,
)

# ── Config ────────────────────────────────────────────────────────────────────
_SM_CONFIG_PATH = Path("output/scene_manager_config.json")


def _sm_load_config() -> dict:
    if _SM_CONFIG_PATH.exists():
        try:
            cfg = json.loads(_SM_CONFIG_PATH.read_text())
            cfg["api_key"] = base64.b64decode(cfg["api_key_b64"]).decode() if cfg.get("api_key_b64") else ""
            if "profiles" not in cfg:
                cfg["profiles"] = {"Default": {"output_dir": cfg.get("output_dir", ""), "topic": ""}}
                cfg["active_profile"] = "Default"
            return cfg
        except Exception:
            pass
    return {
        "api_key": "", "api_key_b64": "", "base_url": "", "model_name": "gpt-4o",
        "threshold": 27.0, "num_frames": 3, "granularity": "medium",
        "active_profile": "", "profiles": {},
    }


def _sm_save_config(cfg: dict) -> None:
    _SM_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    to_save = {k: v for k, v in cfg.items() if k != "api_key"}
    if cfg.get("api_key"):
        to_save["api_key_b64"] = base64.b64encode(cfg["api_key"].encode()).decode()
    _SM_CONFIG_PATH.write_text(json.dumps(to_save, indent=2))


def _sm_active_output_dir() -> str:
    p = st.session_state.sm_active_profile
    return st.session_state.sm_profiles.get(p, {}).get("output_dir", "")


def _sm_active_topic() -> str:
    p = st.session_state.sm_active_profile
    return st.session_state.sm_profiles.get(p, {}).get("topic", "")


def _sm_persist_config():
    cfg = _sm_load_config()
    cfg["api_key"]       = st.session_state.sm_cfg_api_key
    cfg["base_url"]      = st.session_state.sm_cfg_base_url
    cfg["model_name"]    = st.session_state.sm_cfg_model
    cfg["threshold"]     = st.session_state.sm_cfg_threshold
    cfg["num_frames"]    = st.session_state.sm_cfg_num_frames
    cfg["granularity"]   = st.session_state.sm_cfg_granularity
    cfg["min_clip_enabled"]       = st.session_state.sm_cfg_min_clip_enabled
    cfg["min_clip_sec"]           = st.session_state.sm_cfg_min_clip_sec
    cfg["black_filter"]           = st.session_state.sm_cfg_black_filter
    cfg["brightness_threshold"]   = st.session_state.sm_cfg_brightness_thr
    cfg["active_profile"]  = st.session_state.sm_active_profile
    cfg["profiles"]        = st.session_state.sm_profiles
    _sm_save_config(cfg)


def _sm_init_state():
    if "sm_config_loaded" in st.session_state:
        return
    saved = _sm_load_config()
    st.session_state.sm_cfg_api_key           = saved.get("api_key", "")
    st.session_state.sm_cfg_base_url          = saved.get("base_url", "")
    st.session_state.sm_cfg_model             = saved.get("model_name", "gpt-4o")
    st.session_state.sm_cfg_threshold         = float(saved.get("threshold", 27.0))
    st.session_state.sm_cfg_num_frames        = int(saved.get("num_frames", 3))
    st.session_state.sm_cfg_granularity       = saved.get("granularity", "medium")
    st.session_state.sm_cfg_min_clip_enabled  = bool(saved.get("min_clip_enabled", True))
    st.session_state.sm_cfg_min_clip_sec      = float(saved.get("min_clip_sec", 3.0))
    st.session_state.sm_cfg_black_filter      = bool(saved.get("black_filter", True))
    st.session_state.sm_cfg_brightness_thr    = float(saved.get("brightness_threshold", 15.0))
    st.session_state.sm_active_profile        = saved.get("active_profile", "")
    st.session_state.sm_profiles              = saved.get("profiles", {})
    st.session_state.sm_config_loaded         = True


def _sm_validate_output_dir(path: str) -> tuple[bool, str]:
    if not path:
        return False, "Output directory is required."
    if not Path(path).is_absolute():
        return False, "Path must be absolute (start with /)."
    return True, ""


def _sm_validate_api_key(key: str) -> tuple[bool, str]:
    if not key or not key.strip():
        return False, "API key is required."
    return True, ""


def _sm_make_openai_client() -> OpenAI:
    base = st.session_state.sm_cfg_base_url.strip()
    return OpenAI(
        api_key=st.session_state.sm_cfg_api_key,
        base_url=base if base else None,
    )


def render():
    """Render the Scene Manager tab. Called from StudioKit app.py."""
    _sm_init_state()

    # ── Sidebar ───────────────────────────────────────────────────
    with st.sidebar:
        st.subheader("🎬 Scene Manager Settings")

        # Profile selector
        st.markdown("**📁 Library Profile**")
        profiles = st.session_state.sm_profiles
        profile_names = list(profiles.keys())

        if not profile_names:
            st.warning("No profiles yet. Create one below.")
        else:
            current_idx = profile_names.index(st.session_state.sm_active_profile) \
                if st.session_state.sm_active_profile in profile_names else 0
            selected_profile = st.selectbox("Active library", profile_names,
                index=current_idx, key="sm_profile_selector")
            if selected_profile != st.session_state.sm_active_profile:
                st.session_state.sm_active_profile = selected_profile
                st.session_state.sm_browse_dir = _sm_active_output_dir()
                _sm_persist_config()
                st.rerun()

            current_profile = st.session_state.sm_active_profile
            prof = profiles.get(current_profile, {})
            new_out = st.text_input("Output directory", value=prof.get("output_dir", ""),
                key=f"sm_prof_output_{current_profile}", placeholder="/Users/yourname/Videos/NFL")
            new_topic = st.text_input("Topic hint for GPT", value=prof.get("topic", ""),
                key=f"sm_prof_topic_{current_profile}", placeholder="e.g. NFL American Football highlights")

            col_save, col_del = st.columns([3, 1])
            with col_save:
                if st.button("💾 Save Profile", use_container_width=True, key="sm_save_profile_btn"):
                    if new_out and not Path(new_out).is_absolute():
                        st.error("Path must start with /")
                    else:
                        profiles[current_profile]["output_dir"] = new_out
                        profiles[current_profile]["topic"] = new_topic
                        st.session_state.sm_profiles = profiles
                        st.session_state.sm_browse_dir = new_out
                        _sm_persist_config()
                        st.success("Saved!")
            with col_del:
                if st.button("🗑", help=f"Delete profile '{current_profile}'",
                        use_container_width=True, key="sm_del_profile_btn"):
                    st.session_state[f"sm_confirm_del_profile_{current_profile}"] = True

            if st.session_state.get(f"sm_confirm_del_profile_{current_profile}"):
                st.warning(f"Delete **{current_profile}**?")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Yes, delete", key="sm_confirm_del_yes"):
                        del profiles[current_profile]
                        st.session_state.sm_profiles = profiles
                        st.session_state.sm_active_profile = list(profiles.keys())[0] if profiles else ""
                        st.session_state[f"sm_confirm_del_profile_{current_profile}"] = False
                        _sm_persist_config()
                        st.rerun()
                with c2:
                    if st.button("Cancel", key="sm_confirm_del_no"):
                        st.session_state[f"sm_confirm_del_profile_{current_profile}"] = False
                        st.rerun()

        st.divider()
        with st.expander("➕ New Profile"):
            new_name = st.text_input("Profile name", placeholder="NFL", key="sm_new_profile_name")
            new_dir  = st.text_input("Output directory", placeholder="/Users/yourname/Videos/NFL", key="sm_new_profile_dir")
            new_top  = st.text_input("Topic hint", placeholder="NFL American Football games", key="sm_new_profile_topic")
            if st.button("Create", key="sm_btn_create_profile"):
                if not new_name.strip():
                    st.error("Name required.")
                elif new_name in profiles:
                    st.error(f"'{new_name}' already exists.")
                elif new_dir and not Path(new_dir).is_absolute():
                    st.error("Path must start with /")
                else:
                    profiles[new_name] = {"output_dir": new_dir, "topic": new_top}
                    st.session_state.sm_profiles = profiles
                    st.session_state.sm_active_profile = new_name
                    st.session_state.sm_browse_dir = new_dir
                    _sm_persist_config()
                    st.success(f"Profile '{new_name}' created!")
                    st.rerun()

        st.divider()
        st.markdown("**⚙️ API Settings**")
        api_key = st.text_input("API Key", type="password", value=st.session_state.sm_cfg_api_key,
            placeholder="sk-...", key="sm_cfg_api_key_input")
        if api_key != st.session_state.sm_cfg_api_key:
            st.session_state.sm_cfg_api_key = api_key
        base_url = st.text_input("Base URL (optional)", value=st.session_state.sm_cfg_base_url,
            placeholder="https://api.openai.com/v1", key="sm_cfg_base_url_input")
        if base_url != st.session_state.sm_cfg_base_url:
            st.session_state.sm_cfg_base_url = base_url
        model_name = st.text_input("Model name", value=st.session_state.sm_cfg_model,
            placeholder="gpt-4o", key="sm_cfg_model_input")
        if model_name != st.session_state.sm_cfg_model:
            st.session_state.sm_cfg_model = model_name

        threshold = st.slider("Scene threshold", 10.0, 60.0,
            value=st.session_state.sm_cfg_threshold, step=0.5, key="sm_cfg_threshold_slider")
        num_frames = st.slider("Frames per clip", 1, 10,
            value=st.session_state.sm_cfg_num_frames, key="sm_cfg_num_frames_slider")
        granularity = st.selectbox("Analysis granularity", ["low", "medium", "high"],
            index=["low", "medium", "high"].index(st.session_state.sm_cfg_granularity),
            key="sm_cfg_granularity_sel")
        min_clip_enabled = st.checkbox("Enable min clip duration",
            value=st.session_state.sm_cfg_min_clip_enabled, key="sm_cfg_min_clip_enabled_cb")
        min_clip_sec = st.number_input("Min clip duration (s)", min_value=0.5, max_value=30.0,
            value=st.session_state.sm_cfg_min_clip_sec, step=0.5, key="sm_cfg_min_clip_sec_input",
            disabled=not min_clip_enabled)
        black_filter = st.checkbox("Filter black/dark frames",
            value=st.session_state.sm_cfg_black_filter, key="sm_cfg_black_filter_cb")
        brightness_thr = st.slider("Brightness threshold", 0.0, 50.0,
            value=st.session_state.sm_cfg_brightness_thr, step=0.5,
            key="sm_cfg_brightness_thr_slider", disabled=not black_filter)

        if st.button("💾 Save Settings", use_container_width=True, key="sm_save_settings_btn"):
            st.session_state.sm_cfg_threshold       = threshold
            st.session_state.sm_cfg_num_frames      = num_frames
            st.session_state.sm_cfg_granularity     = granularity
            st.session_state.sm_cfg_min_clip_enabled = min_clip_enabled
            st.session_state.sm_cfg_min_clip_sec    = min_clip_sec
            st.session_state.sm_cfg_black_filter    = black_filter
            st.session_state.sm_cfg_brightness_thr  = brightness_thr
            _sm_persist_config()
            st.success("✅ Settings saved.")

    # ── Main area ─────────────────────────────────────────────────
    st.title("🎬 Scene Manager")
    st.caption("Split videos into scenes, analyse with GPT vision, and organise into a library.")

    # Show active profile
    if st.session_state.sm_active_profile:
        st.info(f"📁 Active profile: **{st.session_state.sm_active_profile}** → `{_sm_active_output_dir()}`")
    else:
        st.warning("⚠️ No active profile. Create one in the sidebar first.")

    tab_process, tab_library = st.tabs(["Process Videos", "Browse Library"])

    with tab_process:
        # Input sub-tabs
        input_upload, input_local, input_youtube = st.tabs(["📤 Upload Files", "📂 Local File Paths", "🌐 URL Download"])

        with input_upload:
            uploaded_files = st.file_uploader("Upload video file(s)",
                type=["mp4", "mov", "avi", "mkv", "webm"],
                accept_multiple_files=True, key="sm_upload_files")
            use_gpt_upload = st.checkbox("Use GPT vision analysis", value=True, key="sm_use_gpt_upload")
            if st.button("▶ Process Uploaded Files", key="sm_process_upload_btn",
                    disabled=not uploaded_files):
                ok, err = _sm_validate_api_key(st.session_state.sm_cfg_api_key)
                if not ok:
                    st.error(err)
                elif not st.session_state.sm_active_profile:
                    st.error("Create a profile in the sidebar first.")
                elif not _sm_active_output_dir():
                    st.error("Set an output directory for the active profile.")
                else:
                    client = _sm_make_openai_client()
                    for uf in uploaded_files:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uf.name).suffix) as tmp:
                            tmp.write(uf.read())
                            tmp_path = tmp.name
                        with st.spinner(f"Processing {uf.name}…"):
                            result = _sm_process_video_file(tmp_path, uf.name, client, use_gpt_upload)
                        _sm_show_result(result)
                        Path(tmp_path).unlink(missing_ok=True)

        with input_local:
            local_paths_text = st.text_area("Local file paths — one per line", height=100,
                key="sm_local_paths_input")
            use_gpt_local = st.checkbox("Use GPT vision analysis", value=True, key="sm_use_gpt_local")
            if st.button("▶ Process Local Files", key="sm_process_local_btn"):
                paths = [p.strip() for p in local_paths_text.splitlines() if p.strip()]
                if not paths:
                    st.error("Enter at least one path.")
                else:
                    ok, err = _sm_validate_api_key(st.session_state.sm_cfg_api_key)
                    if not ok:
                        st.error(err)
                    elif not st.session_state.sm_active_profile:
                        st.error("Create a profile in the sidebar first.")
                    else:
                        client = _sm_make_openai_client()
                        for p in paths:
                            if not Path(p).exists():
                                st.error(f"Not found: {p}")
                                continue
                            with st.spinner(f"Processing {Path(p).name}…"):
                                result = _sm_process_video_file(p, Path(p).name, client, use_gpt_local)
                            _sm_show_result(result)

        with input_youtube:
            yt_url = st.text_input("YouTube / video URL", key="sm_yt_url_input")
            use_gpt_yt = st.checkbox("Use GPT vision analysis", value=True, key="sm_use_gpt_yt")
            if st.button("▶ Download & Process", key="sm_process_yt_btn"):
                if not yt_url.strip():
                    st.error("Enter a URL.")
                elif not is_valid_url(yt_url.strip()):
                    st.error("Invalid URL.")
                elif not st.session_state.sm_active_profile:
                    st.error("Create a profile in the sidebar first.")
                else:
                    ok, err = _sm_validate_api_key(st.session_state.sm_cfg_api_key)
                    if not ok:
                        st.error(err)
                    else:
                        with st.spinner("Downloading…"):
                            dl_path, dl_err = download_video(yt_url.strip(), "downloads")
                        if dl_err:
                            st.error(f"Download failed: {dl_err}")
                        else:
                            client = _sm_make_openai_client()
                            with st.spinner(f"Processing {Path(dl_path).name}…"):
                                result = _sm_process_video_file(dl_path, Path(dl_path).name, client, use_gpt_yt)
                            _sm_show_result(result)

    with tab_library:
        browse_dir = _sm_active_output_dir()
        if not browse_dir:
            st.info("Set an output directory in the sidebar profile to browse.")
        else:
            folders = list_existing_folders(browse_dir)
            if not folders:
                st.info("No folders in library yet.")
            else:
                for folder in folders:
                    meta = load_folder_metadata(folder)
                    clips = meta.get("clips", [])
                    with st.expander(f"📂 {Path(folder).name} ({len(clips)} clips)"):
                        for clip in clips:
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.text(clip.get("filename", ""))
                                st.caption(clip.get("summary", ""))
                            with col2:
                                clip_path = Path(folder) / clip.get("filename", "")
                                if clip_path.exists():
                                    st.video(str(clip_path))


def _sm_process_video_file(src_path: str, display_name: str, client: OpenAI, use_gpt: bool) -> dict:
    output_dir = _sm_active_output_dir()
    topic = _sm_active_topic()
    cfg = {
        "threshold": st.session_state.sm_cfg_threshold,
        "num_frames": st.session_state.sm_cfg_num_frames,
        "granularity": st.session_state.sm_cfg_granularity,
        "min_clip_enabled": st.session_state.sm_cfg_min_clip_enabled,
        "min_clip_sec": st.session_state.sm_cfg_min_clip_sec,
        "black_filter": st.session_state.sm_cfg_black_filter,
        "brightness_threshold": st.session_state.sm_cfg_brightness_thr,
        "model_name": st.session_state.sm_cfg_model or "gpt-4o",
    }
    try:
        file_hash = compute_file_hash(src_path)
        if is_already_processed(file_hash, output_dir):
            return {"status": "skipped", "name": display_name, "reason": "Already processed"}

        scenes = detect_scenes(src_path, threshold=cfg["threshold"])
        clips_info = split_video(src_path, scenes, output_dir, cfg)

        results = []
        for clip_info in clips_info:
            frames = extract_frames(clip_info["path"], cfg["num_frames"])
            if use_gpt and frames:
                analysis = analyze_clip_frames(frames, client, cfg)
                cleanup_frames(frames)
                target_folder = resolve_target_folder(analysis, output_dir, topic, client, cfg)
                final_path = place_clip(clip_info["path"], target_folder, analysis)
                results.append({"path": final_path, "analysis": analysis})
            else:
                results.append({"path": clip_info["path"], "analysis": {}})

        register_processed_video(file_hash, display_name, output_dir)
        return {"status": "ok", "name": display_name, "clips": results}
    except Exception as e:
        return {"status": "error", "name": display_name, "error": str(e)}


def _sm_show_result(result: dict):
    if result["status"] == "skipped":
        st.info(f"⏭️ {result['name']}: {result['reason']}")
    elif result["status"] == "error":
        st.error(f"❌ {result['name']}: {result['error']}")
    else:
        clips = result.get("clips", [])
        st.success(f"✅ {result['name']}: {len(clips)} clips")
        for c in clips[:3]:
            st.caption(c.get("analysis", {}).get("summary", c["path"]))
```

- [ ] **Step 2: Verify syntax**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python -c "import ast; ast.parse(open('scene_manager/ui.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add scene_manager/ui.py
git commit -m "feat: add scene_manager/ui.py with render() function"
```

---

## Task 5: Create `app.py` — license gate + tab switcher

**Files:**
- Create: `app.py`

- [ ] **Step 1: Create `app.py`**

Create `app.py`:

```python
"""StudioKit — unified entry point."""

import os
import streamlit as st

# ── License gate ──────────────────────────────────────────────────────────────
_DEV_MODE = os.environ.get("STUDIOKIT_DEV") == "1"

if not _DEV_MODE:
    import requests as _requests
    import license_guard as _lg
    import license_client as _lc

    _LICENSE_SERVER_URL = os.environ.get("LICENSE_SERVER_URL", "https://hype-cutter.vercel.app")
    _status, _payload = _lg.verify_local_license()

    if _status != "active":
        st.set_page_config(page_title="StudioKit — Activate", page_icon="🔑")
        st.title("🔑 Activate StudioKit")
        _STATUS_MSGS = {
            "none":     "No license found. Enter your license key to activate.",
            "expired":  "Your license has expired. Please renew.",
            "mismatch": "This license is bound to another machine.",
            "tampered": "License file is corrupted. Please re-activate.",
            "invalid":  "Invalid license. Please re-activate.",
        }
        st.warning(_STATUS_MSGS.get(_status, "License required."))
        _token_input = st.text_input("License Key", type="password",
                                     placeholder="Paste your license key here")
        if st.button("Activate", type="primary", use_container_width=True):
            if not _token_input.strip():
                st.error("Please enter a license key.")
            else:
                try:
                    _resp = _requests.post(
                        f"{_LICENSE_SERVER_URL}/activate",
                        json={"token": _token_input.strip(),
                              "machine_id": _lc.get_machine_id()},
                        timeout=15,
                    )
                    if _resp.ok and _resp.json().get("status") in ("activated", "already_active"):
                        _pl = _lc.verify_token_signature(_token_input.strip())
                        _lc.save_license(
                            _token_input.strip(),
                            expires_at=_pl.get("expires_at"),
                            plan=_pl.get("plan", "lifetime"),
                        )
                        st.success("✅ Activated! Reloading…")
                        st.rerun()
                    else:
                        st.error(f"❌ {_resp.json().get('detail', 'Activation failed.')}")
                except Exception as _e:
                    st.error(f"❌ Network error: {_e}")
        st.stop()

    from heartbeat import start_heartbeat_scheduler as _start_hb
    _start_hb()
# ── End license gate ──────────────────────────────────────────────────────────

st.set_page_config(
    page_title="StudioKit",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── License status in sidebar ─────────────────────────────────────────────────
with st.sidebar:
    st.title("🎬 StudioKit")
    st.divider()
    if _DEV_MODE:
        st.caption("🛠️ Dev Mode — license bypass active")
    else:
        import license_client as _lc2
        _lic = _lc2.load_license()
        if _lic:
            _plan = _lic.get("plan", "lifetime").capitalize()
            _exp = _lic.get("expires_at")
            if _exp:
                from datetime import datetime as _dt, timezone as _tz
                _days = (_dt.fromisoformat(_exp) - _dt.now(_tz.utc)).days
                _exp_label = f"· Expires in {_days}d"
            else:
                _exp_label = "· Lifetime"
            st.success(f"✅ Licensed {_exp_label}")
            st.caption(f"Plan: **{_plan}**  |  Machine bound")
        else:
            st.warning("⚠️ No license")
    st.divider()

# ── Tool tabs ─────────────────────────────────────────────────────────────────
tab_hc, tab_sm = st.tabs(["✂️ HypeCutter", "🎬 Scene Manager"])

with tab_hc:
    from hypecutter.ui import render as _render_hc
    _render_hc()

with tab_sm:
    from scene_manager.ui import render as _render_sm
    _render_sm()
```

- [ ] **Step 2: Verify syntax**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python -c "import ast; ast.parse(open('app.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add app.py
git commit -m "feat: add app.py with license gate and st.tabs() entry point"
```

---

## Task 6: Create `run_app.py` and smoke-test local dev launch

**Files:**
- Create: `run_app.py`

- [ ] **Step 1: Create `run_app.py`**

Create `run_app.py`:

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


if __name__ == "__main__":
    setup_ffmpeg()
    if getattr(sys, "frozen", False):
        os.environ.pop("STUDIOKIT_DEV", None)
    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run", get_app_path(),
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--global.developmentMode=false",
    ]
    sys.exit(stcli.main())
```

- [ ] **Step 2: Install deps (in a venv)**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Expected: All packages install without conflict errors.

- [ ] **Step 3: Smoke-test local launch**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
source venv/bin/activate
STUDIOKIT_DEV=1 streamlit run app.py --server.headless=true &
sleep 5
curl -s http://localhost:8501/_stcore/health
```

Expected: `{"status":"ok"}` (or similar health check response)

- [ ] **Step 4: Stop dev server**

```bash
pkill -f "streamlit run app.py"
```

- [ ] **Step 5: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add run_app.py
git commit -m "feat: add run_app.py PyInstaller launcher"
```

---

## Task 7: Create `StudioKit.spec` for PyInstaller

**Files:**
- Create: `StudioKit.spec`

- [ ] **Step 1: Create `StudioKit.spec`**

Create `StudioKit.spec`:

```python
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
```

- [ ] **Step 2: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add StudioKit.spec
git commit -m "chore: add StudioKit.spec for PyInstaller"
```

---

## Task 8: Create `Dockerfile` and `docker-compose.yml`

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Create `Dockerfile`**

Create `Dockerfile`:

```dockerfile
FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg gcc g++ libgomp1 curl fontconfig libass-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && fc-cache -fv && apt-get clean && rm -rf /var/lib/apt/lists/* \
    || (echo "WARNING: CJK font install failed" && apt-get clean && rm -rf /var/lib/apt/lists/*)

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app.py run_app.py license_client.py license_guard.py heartbeat.py paths.py config_client.py db.py ./
COPY hypecutter/ ./hypecutter/
COPY scene_manager/ ./scene_manager/
COPY license/ ./license/

RUN mkdir -p downloads output data/projects

ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    PYTHONUNBUFFERED=1

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py"]
```

- [ ] **Step 2: Create `docker-compose.yml`**

Create `docker-compose.yml`:

```yaml
services:
  studiokit:
    build: .
    image: studiokit:latest
    container_name: studiokit
    ports:
      - "8601:8501"
    volumes:
      - ./app.py:/app/app.py
      - ./hypecutter/:/app/hypecutter/
      - ./scene_manager/:/app/scene_manager/
      - ./license_client.py:/app/license_client.py
      - ./license_guard.py:/app/license_guard.py
      - ./heartbeat.py:/app/heartbeat.py
      - ./paths.py:/app/paths.py
      - ./config_client.py:/app/config_client.py
      - ./db.py:/app/db.py
      - ./license:/app/license
      - ./downloads:/app/downloads
      - ./output:/app/output
      - ./data:/app/data
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
      - WHISPER_MODEL=${WHISPER_MODEL:-base}
      - HOST_OUTPUT_PATH=${HOST_OUTPUT_PATH:-}
      - STUDIOKIT_DEV=${STUDIOKIT_DEV:-}
    restart: unless-stopped
    shm_size: "2gb"
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add Dockerfile docker-compose.yml
git commit -m "chore: add Dockerfile and docker-compose.yml"
```

---

## Task 9: Create GitHub Actions `build.yml` with pyarmor + PyInstaller

**Files:**
- Create: `.github/workflows/build.yml`

- [ ] **Step 1: Create `.github/workflows/build.yml`**

Create `.github/workflows/build.yml`:

```yaml
name: Build StudioKit

on:
  push:
    tags:
      - 'v*'

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
          pip install pyinstaller pyarmor

      - name: Bundle FFmpeg
        run: |
          mkdir -p ffmpeg_bin
          cp $(which ffmpeg) ffmpeg_bin/ffmpeg
          cp $(which ffprobe) ffmpeg_bin/ffprobe

      - name: Obfuscate with pyarmor
        run: |
          pyarmor gen --output obfuscated \
            app.py run_app.py \
            hypecutter/ scene_manager/ \
            license_client.py license_guard.py \
            heartbeat.py paths.py config_client.py db.py

      - name: Copy non-obfuscated assets
        run: |
          cp -r license obfuscated/license
          cp -r ffmpeg_bin obfuscated/ffmpeg_bin
          cp StudioKit.spec obfuscated/
          cp requirements.txt obfuscated/

      - name: Build Mac app
        run: |
          cd obfuscated
          pyinstaller StudioKit.spec

      - name: Zip Mac app
        run: |
          cd obfuscated/dist
          zip -r StudioKit-mac.zip StudioKit.app

      - name: Upload Mac artifact
        uses: actions/upload-artifact@v4
        with:
          name: StudioKit-mac
          path: obfuscated/dist/StudioKit-mac.zip

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
          pip install pyinstaller pyarmor

      - name: Bundle FFmpeg
        run: |
          mkdir ffmpeg_bin
          copy "C:\ProgramData\chocolatey\bin\ffmpeg.exe" ffmpeg_bin\ffmpeg.exe
          copy "C:\ProgramData\chocolatey\bin\ffprobe.exe" ffmpeg_bin\ffprobe.exe

      - name: Obfuscate with pyarmor
        run: |
          pyarmor gen --output obfuscated `
            app.py run_app.py `
            hypecutter/ scene_manager/ `
            license_client.py license_guard.py `
            heartbeat.py paths.py config_client.py db.py

      - name: Copy non-obfuscated assets
        run: |
          xcopy /E /I license obfuscated\license
          xcopy /E /I ffmpeg_bin obfuscated\ffmpeg_bin
          copy StudioKit.spec obfuscated\
          copy requirements.txt obfuscated\

      - name: Build Windows exe
        run: |
          cd obfuscated
          pyinstaller StudioKit.spec

      - name: Zip Windows exe
        run: Compress-Archive -Path obfuscated\dist\StudioKit -DestinationPath obfuscated\dist\StudioKit-windows.zip

      - name: Upload Windows artifact
        uses: actions/upload-artifact@v4
        with:
          name: StudioKit-windows
          path: obfuscated\dist\StudioKit-windows.zip

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

- [ ] **Step 2: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add .github/workflows/build.yml
git commit -m "ci: add GitHub Actions build with pyarmor obfuscation"
```

---

## Task 10: Push to GitHub and verify

- [ ] **Step 1: Create private GitHub repo**

Go to https://github.com/new and create a **private** repo named `StudioKit`. Do NOT initialize with README.

- [ ] **Step 2: Add remote and push**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git remote add origin git@github.com:<YOUR_GITHUB_USERNAME>/StudioKit.git
git branch -M main
git push -u origin main
```

Replace `<YOUR_GITHUB_USERNAME>` with your actual GitHub username.

- [ ] **Step 3: Trigger a build by tagging**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git tag v1.0.0
git push origin v1.0.0
```

- [ ] **Step 4: Check GitHub Actions**

Go to `https://github.com/<YOUR_GITHUB_USERNAME>/StudioKit/actions` and confirm both Mac and Windows jobs start running.

---

## Self-Review Notes

- All session state keys are prefixed (`hc_` / `sm_`) — no collision risk ✅
- `st.set_page_config()` called once in `app.py` only — removed from both `ui.py` files ✅
- Config paths: `output/hypecutter_config.json` and `output/scene_manager_config.json` — no overlap ✅
- `from core_engine import` → `from hypecutter.core_engine import` in `hypecutter/ui.py` ✅
- `from xxx import` → `from scene_manager.xxx import` in `scene_manager/ui.py` ✅
- pyarmor runs before PyInstaller in CI — obfuscated code goes through spec ✅
- License env var renamed `STUDIOKIT_DEV` — `run_app.py` pops it in frozen builds ✅
- Spec includes `scenedetect`, `cv2`, `Pillow` metadata and submodules ✅
