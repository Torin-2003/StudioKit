"""
hypecutter/ui.py
HypeCutter Streamlit UI — extracted for embedding in StudioKit.
Call render() inside a Streamlit tab or page.
"""

import json
import logging
import os
import re
import shutil
from pathlib import Path

import streamlit as st

import db as _db

# ─────────────────────────────────────────────────────────────────
# Config / constants
# ─────────────────────────────────────────────────────────────────

_HC_CONFIG_FILE = Path("output/hypecutter_config.json")

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

STAGE_PCT = {
    "⬇️ Downloading": 0.08,
    "✅ Video ready": 0.15,
    "🔇 Removing": 0.20,
    "✅ Silence": 0.25,
    "🎙️ Transcribing": 0.28,
    "✅ Transcription": 0.55,
    "🧠 AI analyzing": 0.60,
    "✅ Found": 0.68,
    "🎬 Rendering": 0.72,
    "🎉 All clips": 1.00,
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# ─────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def _hc_load_config() -> dict:
    try:
        if _HC_CONFIG_FILE.exists():
            return json.loads(_HC_CONFIG_FILE.read_text())
    except Exception:
        pass
    return {}


def _hc_save_config(data: dict):
    _HC_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _HC_CONFIG_FILE.write_text(json.dumps(data, indent=2))
    _hc_load_config.clear()


def _hc_init_state():
    saved = _hc_load_config()
    for k, v in _CFG_DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = saved.get(k, v)
    # Load per-provider profile slots
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
    return {
        "completed": "🟢 Completed",
        "processing": "🔄 Processing",
        "failed": "🔴 Failed",
    }.get(status, f"⚪ {status}")


def _hc_render_clip_card(clip: dict, key_prefix: str) -> None:
    score = float(clip.get("viral_score", 0))
    hook = float(clip.get("hook_score", 0))
    badge = "🟢" if score >= 8 else ("🟡" if score >= 6 else "🔴")
    dur = float(clip.get("duration", 0))
    clip_type = (
        f"🔀 Condensed ({clip.get('segment_count', '?')} segs)"
        if clip.get("condensed")
        else "▶ Continuous"
    )
    st.markdown(f"**{clip.get('title', 'Untitled')}**")
    st.markdown(
        f"{badge} Score: **{score:.1f}** | 🪝 Hook: **{hook:.1f}** | {clip_type} | ⏱️ {dur:.0f}s"
    )
    if clip.get("selected_range"):
        st.caption(f"📐 Range: {clip['selected_range']}")
    if clip.get("reason_for_duration"):
        st.caption(f"⏳ {clip['reason_for_duration']}")
    if clip.get("reason"):
        st.markdown(f"_{clip['reason']}_")
    if clip.get("caption"):
        st.info(f"📲 {clip['caption']}")
    fp = clip.get("file_path") or ""
    if fp and Path(fp).exists():
        st.video(fp)
        with open(fp, "rb") as fh:
            st.download_button(
                "⬇️ Download",
                data=fh,
                file_name=Path(fp).name,
                mime="video/mp4",
                use_container_width=True,
                key=f"{key_prefix}_dl",
            )
    else:
        st.caption("_(file not found on disk)_")


def _hc_render_project_history() -> None:
    # ── Filters ──────────────────────────────────────────────────
    f_col1, f_col2 = st.columns([2, 3])
    with f_col1:
        date_filter = st.radio(
            "Period",
            ["Today", "Last 7 Days", "All"],
            horizontal=True,
            key="hc_hist_date",
            label_visibility="collapsed",
        )
    with f_col2:
        search_q = st.text_input(
            "Search",
            placeholder="Project name or URL…",
            key="hc_hist_search",
            label_visibility="collapsed",
        )

    days_map = {"Today": 1, "Last 7 Days": 7, "All": None}
    projects = _db.list_projects(days=days_map[date_filter], search=search_q)

    if not projects:
        st.info("No projects yet. Process a video to get started.")
        return

    _info_col, _folder_col = st.columns([3, 1])
    with _info_col:
        st.caption(f"{len(projects)} project(s) found")
    with _folder_col:
        if st.button("📂 Output Folder", key="hc_hist_open_folder", use_container_width=True):
            _host_out2 = os.environ.get("HOST_OUTPUT_PATH", "")
            _out2_display = _host_out2 if _host_out2 else str(Path("output").resolve())
            st.info(f"📁 **Output 文件夹路径：**\n\n`{_out2_display}`\n\n→ Finder 按 **Cmd+Shift+G** 粘贴路径即可跳转")

    for proj in projects:
        pid = proj["id"]
        n_clips_proj = proj.get("clip_count", 0)
        created = proj["created_at"][:16].replace("T", " ")
        source_url = proj.get("source_url") or ""
        source_path = proj.get("source_path") or ""

        # Friendly display name: custom name > filename > video ID from URL > URL
        raw_name = proj.get("name", "")
        if source_url and raw_name == source_url:
            vid_match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,})", source_url)
            display_name = vid_match.group(1) if vid_match else source_url[-30:]
        elif source_path and raw_name == source_path:
            display_name = Path(source_path).name
        else:
            display_name = raw_name

        source_label = source_url or Path(source_path).name or "local file"

        with st.expander(
            f"{_hc_status_badge(proj['status'])}  **{display_name}**  ·  "
            f"{n_clips_proj} clip(s)  ·  {created}",
            expanded=False,
        ):
            st.caption(f"Source: {source_label[:80]}")

            # ── Actions ──────────────────────────────────────────
            a1, a2, a3 = st.columns([2, 2, 1])
            with a1:
                new_name = st.text_input(
                    "Rename",
                    value=proj["name"],
                    key=f"hc_rename_{pid}",
                    label_visibility="collapsed",
                )
                if st.button(
                    "✏️ Save Name", key=f"hc_save_rename_{pid}", use_container_width=True
                ):
                    if new_name.strip():
                        _db.rename_project(pid, new_name.strip())
                        st.rerun()
            with a3:
                if st.button(
                    "🗑️ Delete",
                    key=f"hc_del_{pid}",
                    use_container_width=True,
                    type="secondary",
                ):
                    st.session_state[f"hc_confirm_del_{pid}"] = True

            # Confirm delete
            if st.session_state.get(f"hc_confirm_del_{pid}"):
                st.warning("Delete this project and all its clip files?")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button(
                        "Yes, delete",
                        key=f"hc_yes_del_{pid}",
                        type="primary",
                        use_container_width=True,
                    ):
                        file_paths = _db.delete_project(pid)
                        for fp in file_paths:
                            try:
                                Path(fp).unlink(missing_ok=True)
                            except OSError:
                                pass
                        proj_dir = Path("data/projects") / pid
                        if proj_dir.exists():
                            shutil.rmtree(proj_dir, ignore_errors=True)
                        st.session_state.pop(f"hc_confirm_del_{pid}", None)
                        st.rerun()
                with c2:
                    if st.button(
                        "Cancel", key=f"hc_cancel_del_{pid}", use_container_width=True
                    ):
                        st.session_state.pop(f"hc_confirm_del_{pid}", None)
                        st.rerun()

            # ── Clips ────────────────────────────────────────────
            clips = _db.get_clips(pid)
            if not clips:
                st.caption("No clips saved yet.")
            else:
                clips = sorted(clips, key=lambda c: float(c.get("viral_score", 0)), reverse=True)
                cols_per_row = 2
                for ci in range(0, len(clips), cols_per_row):
                    row_clips = clips[ci : ci + cols_per_row]
                    cols = st.columns(cols_per_row)
                    for col, clip in zip(cols, row_clips):
                        with col:
                            _hc_render_clip_card(clip, key_prefix=f"{pid}_{clip['id']}")
                            st.divider()


@st.cache_resource(show_spinner="Loading Whisper model…")
def _hc_get_engine(
    provider_: str, api_key_: str, llm_model_: str, whisper_model_: str, base_url_: str
):
    from hypecutter.core_engine import AutoHighlightEngine

    return AutoHighlightEngine(
        provider=provider_.lower(),
        api_key=api_key_,
        llm_model=llm_model_.strip(),
        whisper_model=whisper_model_,
        base_url=base_url_.strip(),
        downloads_dir="downloads",
        output_dir="output",
    )


# ─────────────────────────────────────────────────────────────────
# Main render() entry point
# ─────────────────────────────────────────────────────────────────

def render():
    # Initialise DB once per process (no-op if tables already exist)
    _db.init_db()

    st.markdown(
        """
<style>
    [data-testid="stVerticalBlock"] .clip-card {
        background: #1e1e2e;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
        border: 1px solid #313244;
    }
    .stage-label { font-size: 0.85rem; color: #888; }
</style>
""",
        unsafe_allow_html=True,
    )

    # ── Session state defaults ────────────────────────────────────
    _hc_init_state()

    # ─────────────────────────────────────────────────────────────
    # Sidebar — settings
    # ─────────────────────────────────────────────────────────────

    with st.sidebar:
        st.title("⚙️ Settings")

        # ── API ──────────────────────────────────────────────────
        st.subheader("🔑 API")

        _PROFILE_KEYS = {
            "OpenAI":    ("hc_cfg_openai_key",    "hc_cfg_openai_base_url",    "hc_cfg_openai_model"),
            "Gemini":    ("hc_cfg_gemini_key",    "hc_cfg_gemini_base_url",    "hc_cfg_gemini_model"),
            "Anthropic": ("hc_cfg_anthropic_key", "hc_cfg_anthropic_base_url", "hc_cfg_anthropic_model"),
        }
        _PROFILE_DEFAULTS = {
            "hc_cfg_openai_key": "", "hc_cfg_openai_base_url": "", "hc_cfg_openai_model": "",
            "hc_cfg_gemini_key": "", "hc_cfg_gemini_base_url": "", "hc_cfg_gemini_model": "",
            "hc_cfg_anthropic_key": "", "hc_cfg_anthropic_base_url": "", "hc_cfg_anthropic_model": "",
        }
        for _k, _v in _PROFILE_DEFAULTS.items():
            if _k not in st.session_state:
                st.session_state[_k] = _v

        _PROVIDERS = ["OpenAI", "Gemini", "Anthropic"]
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

        def _on_provider_change():
            """Switching provider: push that provider's saved values into its scoped widget keys."""
            prov = st.session_state["hc_sb_provider"]
            _kk, _kb, _km = _PROFILE_KEYS[prov]
            _p2 = prov.lower()
            st.session_state[f"hc_sb_api_key_{_p2}"]   = st.session_state.get(_kk) or ""
            st.session_state[f"hc_sb_base_url_{_p2}"]  = st.session_state.get(_kb) or ""
            st.session_state[f"hc_sb_llm_model_{_p2}"] = st.session_state.get(_km) or ""

        provider = st.selectbox(
            "LLM Provider",
            _PROVIDERS,
            index=_PROVIDERS.index(st.session_state.hc_cfg_provider)
            if st.session_state.hc_cfg_provider in _PROVIDERS
            else 0,
            key="hc_sb_provider",
            on_change=_on_provider_change,
        )

        _k_key, _k_base, _k_model = _PROFILE_KEYS[provider]
        _p = provider.lower()

        # Seed scoped widget keys from saved profile on first appearance
        if f"hc_sb_api_key_{_p}" not in st.session_state:
            st.session_state[f"hc_sb_api_key_{_p}"]   = st.session_state.get(_k_key) or st.session_state.hc_cfg_api_key
            st.session_state[f"hc_sb_base_url_{_p}"]  = st.session_state.get(_k_base) or ""
            st.session_state[f"hc_sb_llm_model_{_p}"] = st.session_state.get(_k_model) or ""

        api_key = st.text_input(
            "API Key",
            type="password",
            key=f"hc_sb_api_key_{_p}",
        )
        base_url = st.text_input(
            "Base URL",
            placeholder=_BASE_URL_PLACEHOLDERS.get(provider, ""),
            help="OpenAI/Gemini: any OpenAI-compatible endpoint. Anthropic: leave blank.",
            key=f"hc_sb_base_url_{_p}",
        )
        llm_model = st.text_input(
            "LLM Model (blank = default)",
            placeholder=_MODEL_PLACEHOLDERS.get(provider, ""),
            key=f"hc_sb_llm_model_{_p}",
        )

        if st.button("💾 Save API Profile", key="hc_save_profile", use_container_width=True,
                     help=f"Save current API Key / Base URL / Model for {provider}"):
            st.session_state[_k_key]   = api_key
            st.session_state[_k_base]  = base_url
            st.session_state[_k_model] = llm_model
            saved_cfg = _hc_load_config()
            saved_cfg.update({_k_key: api_key, _k_base: base_url, _k_model: llm_model})
            _hc_save_config(saved_cfg)
            st.success(f"✅ {provider} profile saved.")

        st.divider()

        # ── Clip settings ────────────────────────────────────────
        st.subheader("🎬 Clip Settings")

        duration_mode = st.radio(
            "Duration Mode",
            ["Fixed Duration", "Range-Based (AI Optimized)"],
            index=["Fixed Duration", "Range-Based (AI Optimized)"].index(
                st.session_state.hc_cfg_duration_mode
            ),
            key="hc_sb_duration_mode",
            horizontal=True,
            help="Fixed: strict target ±5s. Range-Based: AI picks the natural semantic endpoint within the range.",
        )

        range_lo, range_hi = 30, 60  # defaults, overwritten below
        target_duration = st.session_state.hc_cfg_target_duration  # used in Fixed mode

        if duration_mode == "Fixed Duration":
            dur_col1, dur_col2 = st.columns([3, 1])
            with dur_col1:
                target_duration = st.slider(
                    "Target duration (s)",
                    15,
                    180,
                    value=st.session_state.hc_cfg_target_duration,
                    step=5,
                    key="hc_sb_dur_slider",
                )
            with dur_col2:
                target_duration_num = st.number_input(
                    "s",
                    min_value=15,
                    max_value=180,
                    value=target_duration,
                    step=1,
                    key="hc_sb_dur_num",
                    label_visibility="visible",
                )
            if target_duration_num != target_duration:
                target_duration = target_duration_num
            duration_range = st.session_state.hc_cfg_duration_range
        else:
            duration_range = st.radio(
                "Duration Range",
                list(_RANGE_PRESETS.keys()),
                index=list(_RANGE_PRESETS.keys()).index(
                    st.session_state.hc_cfg_duration_range
                ),
                key="hc_sb_duration_range",
            )
            range_lo, range_hi = _RANGE_PRESETS[duration_range]
            st.caption(
                f"🎯 AI will find the natural semantic endpoint within **{range_lo}s – {range_hi}s**. "
                f"Quality over length — no padding."
            )

        smart_mode = st.toggle(
            "🧠 Smart Count — AI auto-detects clip count per video",
            value=st.session_state.hc_cfg_smart_mode,
            key="hc_sb_smart_mode",
            help="Each video gets its own clip count based on its length and content density. The slider below becomes a max-clips cap.",
        )
        n_clips = st.slider(
            "Max clips per video" if smart_mode else "Number of clips",
            1,
            20,
            value=st.session_state.hc_cfg_n_clips,
            key="hc_sb_n_clips",
        )
        if smart_mode:
            st.caption(
                "🔢 Smart Count: AI 根据每个视频时长自动计算片段数，上方滑块为上限。"
            )

        condense_mode = st.toggle(
            "🧩 Condense Mode — 智能内容浓缩",
            value=st.session_state.hc_cfg_condense_mode,
            key="hc_sb_condense_mode",
            help="Each clip is assembled from multiple jump-cut segments for maximum information density. Can be combined with Smart Count.",
        )
        if condense_mode:
            st.caption(
                "✂️ 跳剪：AI 剔除填充词，散落精华合为一条。100ms 交叉淡化 + 1.05x 推拉镜头。适合知识博主/访谈。"
            )

        vertical = st.toggle(
            "Vertical 9:16 output", value=st.session_state.hc_cfg_vertical, key="hc_sb_vertical"
        )
        burn_subtitles = st.checkbox(
            "🔤 Burn-in Subtitles",
            value=st.session_state.hc_cfg_burn_subtitles,
            key="hc_sb_burn_subtitles",
        )
        remove_silence = st.checkbox(
            "🔇 Auto-remove Silence",
            value=st.session_state.hc_cfg_remove_silence,
            key="hc_sb_remove_silence",
            help="Detect and ripple-cut audio gaps > 1s to improve pacing.",
        )

        st.divider()

        # ── Download settings ────────────────────────────────────
        st.subheader("⬇️ Download Settings")
        resolution_options = ["1080p", "720p", "480p"]
        max_resolution = st.selectbox(
            "Max download resolution",
            resolution_options,
            index=resolution_options.index(st.session_state.hc_cfg_max_resolution),
            key="hc_sb_max_resolution",
            help="Lower = faster download, less disk usage. 720p is sufficient for 9:16 clips.",
        )
        auto_delete_source = st.checkbox(
            "🗑️ Auto-delete source after processing",
            value=st.session_state.hc_cfg_auto_delete_source,
            key="hc_sb_auto_delete_source",
            help="Delete the downloaded source video after all clips are rendered. Local uploads are never deleted.",
        )

        st.divider()

        # ── Whisper ──────────────────────────────────────────────
        st.subheader("🎙️ Whisper Model")
        whisper_options = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
        whisper_model = st.selectbox(
            "Model size",
            whisper_options,
            index=whisper_options.index(st.session_state.hc_cfg_whisper_model),
            key="hc_sb_whisper_model",
            help="tiny/base = fast; large-v3 = most accurate",
        )
        language = st.text_input(
            "Language code (optional)",
            value=st.session_state.hc_cfg_language,
            placeholder="en / zh / ja …",
            key="hc_sb_language",
        )

        st.divider()

        # ── Font (Docker only) ────────────────────────────────────
        _in_docker = os.path.exists("/.dockerenv")
        if _in_docker:
            st.subheader("🔤 CJK Font (Docker)")
            font_path_input = st.text_input(
                "Font file path",
                value=st.session_state.hc_cfg_font_path,
                key="hc_sb_font_path",
                help="Docker container path. Clear to use default system font.",
            )
        else:
            font_path_input = st.session_state.hc_cfg_font_path

        st.divider()

        # ── Save config ──────────────────────────────────────────
        if st.button("💾 Save Configuration", key="hc_save_configuration", use_container_width=True):
            cfg = {
                "hc_cfg_provider": provider,
                "hc_cfg_api_key": api_key,
                "hc_cfg_base_url": base_url,
                "hc_cfg_llm_model": llm_model,
                "hc_cfg_duration_mode": duration_mode,
                "hc_cfg_target_duration": target_duration,
                "hc_cfg_duration_range": duration_range,
                "hc_cfg_n_clips": n_clips,
                "hc_cfg_vertical": vertical,
                "hc_cfg_smart_mode": smart_mode,
                "hc_cfg_condense_mode": condense_mode,
                "hc_cfg_burn_subtitles": burn_subtitles,
                "hc_cfg_remove_silence": remove_silence,
                "hc_cfg_max_resolution": max_resolution,
                "hc_cfg_auto_delete_source": auto_delete_source,
                "hc_cfg_whisper_model": whisper_model,
                "hc_cfg_language": language,
                "hc_cfg_font_path": font_path_input,
            }
            for k, v in cfg.items():
                st.session_state[k] = v
            _hc_save_config(cfg)
            st.success("✅ Saved — settings will persist after refresh.")

    # ─────────────────────────────────────────────────────────────
    # Main area — input
    # ─────────────────────────────────────────────────────────────

    st.title("✂️ AutoHighlight Pro Max")
    st.caption(
        "Automatically extract ranked viral clips from long-form videos — powered by AI."
    )

    tab_url, tab_file, tab_history = st.tabs(
        ["🔗 URL Input", "📂 Local File Upload", "📋 Project History"]
    )

    with tab_url:
        url_text = st.text_area(
            "Enter video URL(s) — one per line",
            height=110,
            placeholder="https://www.youtube.com/watch?v=...\nhttps://...",
            key="hc_url_textarea",
        )
        st.session_state.hc_url_sources = (
            [u.strip() for u in url_text.splitlines() if u.strip()]
            if url_text.strip()
            else []
        )

    with tab_file:
        uploaded = st.file_uploader(
            "Upload video file(s)",
            type=["mp4", "mov", "avi", "mkv", "webm"],
            accept_multiple_files=True,
            key="hc_file_uploader",
        )
        if uploaded:
            upload_dir = Path("downloads")
            upload_dir.mkdir(exist_ok=True)
            saved_files = []
            for f in uploaded:
                dest = upload_dir / f.name
                if not dest.exists():
                    dest.write_bytes(f.read())
                saved_files.append(str(dest))
            st.session_state.hc_file_sources = saved_files
            st.success(f"Ready: {len(saved_files)} file(s)")
        else:
            st.session_state.hc_file_sources = []

    with tab_history:
        _hc_render_project_history()

    all_sources = st.session_state.hc_url_sources + st.session_state.hc_file_sources

    st.divider()

    col_run, col_clear = st.columns([5, 1])
    with col_run:
        run_btn = st.button(
            "🚀 Start Processing",
            type="primary",
            use_container_width=True,
            disabled=(not all_sources or st.session_state.hc_processing),
        )
    with col_clear:
        if st.button("🗑️ Clear", key="hc_clear_btn", use_container_width=True):
            st.session_state.hc_results = []
            st.session_state.hc_log_lines = []
            st.rerun()

    # ─────────────────────────────────────────────────────────────
    # Processing
    # ─────────────────────────────────────────────────────────────

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

        # Snapshot current settings for project record
        _settings_snapshot = {
            "duration_mode": duration_mode,
            "target_duration": target_duration,
            "duration_range": duration_range,
            "range_lo": range_lo,
            "range_hi": range_hi,
            "n_clips": n_clips,
            "smart_mode": smart_mode,
            "condense_mode": condense_mode,
            "whisper_model": whisper_model,
            "vertical": vertical,
            "max_resolution": max_resolution,
        }

        all_results = []
        for idx, src in enumerate(all_sources):
            label = Path(src).name if not src.startswith("http") else src[:70]
            st.markdown(f"#### 📹 Source {idx + 1}: `{label}`")

            # Create project record (status=processing)
            is_url = src.startswith(("http://", "https://"))
            proj_id = _db.create_project(
                name=label,
                source_url=src if is_url else "",
                source_path="" if is_url else src,
                settings=_settings_snapshot,
            )

            def _clip_saved(clip: dict, _pid: str = proj_id) -> None:
                _db.save_clip(_pid, clip)

            try:
                res = engine.process(
                    source=src,
                    target_duration=target_duration,
                    n_clips=n_clips,
                    vertical=vertical,
                    language=language.strip() or None,
                    font_path=font_path_input.strip() or None,
                    burn_subtitles=burn_subtitles,
                    remove_silence=remove_silence,
                    smart_mode=smart_mode,
                    condense_mode=condense_mode,
                    range_mode=(duration_mode == "Range-Based (AI Optimized)"),
                    range_label=duration_range,
                    range_lo=range_lo,
                    range_hi=range_hi,
                    max_resolution=int(max_resolution.replace("p", "")),
                    auto_delete_source=auto_delete_source,
                    status_callback=status_cb,
                    clip_saved_callback=_clip_saved,
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

    # ─────────────────────────────────────────────────────────────
    # Results gallery
    # ─────────────────────────────────────────────────────────────

    if st.session_state.hc_results:
        st.divider()
        _hdr_col, _btn_col = st.columns([4, 1])
        with _hdr_col:
            st.subheader("🏆 Generated Clips")
        with _btn_col:
            _host_out = os.environ.get("HOST_OUTPUT_PATH", "")
            _out_display = _host_out if _host_out else str(Path("output").resolve())
            if st.button("📂 Open Folder", key="hc_open_folder_btn", use_container_width=True):
                st.info(f"📁 **Output 文件夹路径：**\n\n`{_out_display}`\n\n→ Finder 按 **Cmd+Shift+G** 粘贴路径即可跳转")

        results = st.session_state.hc_results
        cols_per_row = 2

        for i in range(0, len(results), cols_per_row):
            row = results[i : i + cols_per_row]
            cols = st.columns(cols_per_row)
            for col, res in zip(cols, row):
                with col:
                    score = float(res.get("score", 0))
                    hook = float(res.get("hook_strength", 0))
                    badge = "🟢" if score >= 8 else ("🟡" if score >= 6 else "🔴")

                    st.markdown(f"**{res['title']}**")
                    clip_type = (
                        f"🔀 Condensed ({res['segment_count']} segments)"
                        if res.get("condensed")
                        else "▶ Continuous"
                    )
                    st.markdown(
                        f"{badge} Viral Score: **{score:.1f}**  |  🪝 Hook: **{hook:.1f}** / 10  |  {clip_type}"
                    )
                    dur = res.get("duration") or (res["end"] - res["start"])
                    st.caption(f"⏱️ {res['start']:.1f}s → {res['end']:.1f}s  ({dur:.0f}s)")
                    if res.get("selected_range"):
                        st.caption(f"📐 Range: {res['selected_range']}")
                    if res.get("duration_warning"):
                        st.warning(f"⚠️ {res['duration_warning']}")

                    if res.get("reason_for_duration"):
                        st.markdown(f"⏳ _{res['reason_for_duration']}_")
                    elif res.get("reason"):
                        st.markdown(f"_{res['reason']}_")
                    if res.get("caption"):
                        st.info(f"📲 {res['caption']}")

                    out_path = res.get("output_path")
                    if out_path and Path(out_path).exists():
                        st.video(out_path)
                        with open(out_path, "rb") as fh:
                            st.download_button(
                                label="⬇️ Download",
                                data=fh,
                                file_name=Path(out_path).name,
                                mime="video/mp4",
                                use_container_width=True,
                                key=f"hc_dl_{out_path}",
                            )
                    elif res.get("error"):
                        st.error(f"Render failed: {res['error']}")
                    else:
                        st.warning("Output file not found.")

                    st.divider()
