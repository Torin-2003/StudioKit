import streamlit as st
import os
import json
import base64
import tempfile
import shutil
import csv
import io
from pathlib import Path
from openai import OpenAI

from scene_manager.metadata import (
    compute_file_hash,
    is_already_processed,
    register_processed_video,
    list_existing_folders,
    load_folder_metadata,
    save_folder_metadata,
    remove_clip_from_metadata,
    update_clip_in_metadata,
)
from scene_manager.splitter import detect_scenes, split_video, extract_frames
from scene_manager.analyzer import analyze_clip_frames, cleanup_frames
from scene_manager.classifier import resolve_target_folder, place_clip
from scene_manager.downloader import (
    check_ytdlp, get_video_info, download_video,
    is_valid_url, check_disk_space,
)
from i18n import t as _t

# ── Config ────────────────────────────────────────────────────────────────────
from paths import sm_config_path as _sm_config_path
CONFIG_PATH = _sm_config_path()


def _sm_load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text())
            cfg["api_key"] = base64.b64decode(cfg["api_key_b64"]).decode() if cfg.get("api_key_b64") else ""
            # migrate old format that had no profiles
            if "profiles" not in cfg:
                cfg["profiles"] = {"Default": {"output_dir": cfg.get("output_dir", ""), "topic": ""}}
                cfg["active_profile"] = "Default"
            return cfg
        except Exception:
            pass
    return {
        "api_key": "", "api_key_b64": "", "base_url": "", "model_name": "gpt-4o",
        "threshold": 27.0, "num_frames": 3, "granularity": "medium",
        "active_profile": "",
        "profiles": {},
    }


def _sm_save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    to_save = {k: v for k, v in cfg.items() if k != "api_key"}
    if cfg.get("api_key"):
        to_save["api_key_b64"] = base64.b64encode(cfg["api_key"].encode()).decode()
    CONFIG_PATH.write_text(json.dumps(to_save, indent=2))


def _sm_init_state():
    if "sm_config_loaded" not in st.session_state:
        saved = _sm_load_config()
        st.session_state.sm_cfg              = saved
        st.session_state.sm_cfg_api_key      = saved.get("api_key", "")
        st.session_state.sm_cfg_base_url     = saved.get("base_url", "")
        st.session_state.sm_cfg_model        = saved.get("model_name", "gpt-4o")
        st.session_state.sm_cfg_threshold    = float(saved.get("threshold", 27.0))
        st.session_state.sm_cfg_num_frames   = int(saved.get("num_frames", 3))
        st.session_state.sm_cfg_granularity  = saved.get("granularity", "medium")
        st.session_state.sm_cfg_min_clip_enabled = bool(saved.get("min_clip_enabled", True))
        st.session_state.sm_cfg_min_clip_sec = float(saved.get("min_clip_sec", 3.0))
        st.session_state.sm_cfg_black_filter   = bool(saved.get("black_filter", True))
        st.session_state.sm_cfg_brightness_thr = float(saved.get("brightness_threshold", 15.0))
        st.session_state.sm_active_profile   = saved.get("active_profile", "")
        st.session_state.sm_profiles         = saved.get("profiles", {})
        st.session_state.sm_config_loaded    = True


def _sm_active_output_dir() -> str:
    p = st.session_state.sm_active_profile
    return st.session_state.sm_profiles.get(p, {}).get("output_dir", "")


def _sm_active_topic() -> str:
    p = st.session_state.sm_active_profile
    return st.session_state.sm_profiles.get(p, {}).get("topic", "")


def _sm_persist_config():
    cfg = st.session_state.sm_cfg
    cfg["api_key"]       = st.session_state.sm_cfg_api_key
    cfg["base_url"]      = st.session_state.sm_cfg_base_url
    cfg["model_name"]    = st.session_state.sm_cfg_model
    cfg["threshold"]        = st.session_state.sm_cfg_threshold
    cfg["num_frames"]       = st.session_state.sm_cfg_num_frames
    cfg["granularity"]      = st.session_state.sm_cfg_granularity
    cfg["min_clip_enabled"]    = st.session_state.sm_cfg_min_clip_enabled
    cfg["min_clip_sec"]        = st.session_state.sm_cfg_min_clip_sec
    cfg["black_filter"]        = st.session_state.sm_cfg_black_filter
    cfg["brightness_threshold"] = st.session_state.sm_cfg_brightness_thr
    cfg["active_profile"] = st.session_state.sm_active_profile
    cfg["profiles"]      = st.session_state.sm_profiles
    _sm_save_config(cfg)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _sm_validate_output_dir(path: str) -> tuple[bool, str]:
    if not path:
        return False, "No output directory set for this profile. Edit the profile in the sidebar."
    if not Path(path).is_absolute():
        return False, f"Output directory must start with `/`. Got: `{path}`"
    if not Path(path).exists():
        try:
            Path(path).mkdir(parents=True)
        except Exception as e:
            return False, f"Cannot create output directory: {e}"
    return True, ""


def _sm_validate_api_key(key: str) -> tuple[bool, str]:
    if not key:
        return False, "Please enter your API key in the sidebar."
    return True, ""


def _sm_make_openai_client(api_key: str, base_url: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=base_url.strip() or None)


# ── Core processing ───────────────────────────────────────────────────────────
def _sm_process_video_file(
    src_path: str, display_name: str, client: OpenAI, use_gpt: bool,
    threshold: float, num_frames: int, granularity: str,
    model_name: str,
) -> dict:
    _lang = st.session_state.get("lang", "en")
    output_dir = _sm_active_output_dir()
    topic = _sm_active_topic()

    progress_bar = st.progress(0, text="Computing file hash...")
    status_box = st.empty()

    file_hash = compute_file_hash(src_path)
    existing_entry = is_already_processed(output_dir, file_hash)
    if existing_entry:
        progress_bar.empty()
        st.warning(
            f"⚠️ **{display_name}** was already processed on "
            f"`{existing_entry['processed_at'][:10]}` — "
            f"{existing_entry['clips_generated']} clip(s) in: "
            f"{', '.join(existing_entry['folders_affected'])}. Skipping."
        )
        return {"clips": 0, "folders": []}

    base_name = Path(display_name).stem

    progress_bar.progress(5, text="Detecting scenes...")
    _min_sec = st.session_state.sm_cfg_min_clip_sec if st.session_state.sm_cfg_min_clip_enabled else 0.5
    try:
        scenes = detect_scenes(src_path, threshold=threshold, min_clip_sec=_min_sec)
    except Exception as e:
        st.error(f"Scene detection failed: {e}")
        return {"clips": 0, "folders": []}

    status_box.info(f"Found **{len(scenes)}** scene(s).")

    progress_bar.progress(10, text="Splitting video...")
    raw_clips_dir = os.path.join(tempfile.mkdtemp(), "raw_clips")

    def split_cb(i, total, name):
        progress_bar.progress(10 + int(30 * i / total), text=f"Splitting {i}/{total}: {name}")

    try:
        clips = split_video(src_path, scenes, raw_clips_dir, base_name, progress_callback=split_cb, min_clip_sec=_min_sec,
                            black_filter=st.session_state.sm_cfg_black_filter, brightness_threshold=st.session_state.sm_cfg_brightness_thr)
    except Exception as e:
        shutil.rmtree(raw_clips_dir, ignore_errors=True)
        st.error(f"Splitting failed: {e}")
        return {"clips": 0, "folders": []}

    folders_used = set()
    results_table = []

    if not use_gpt:
        folder_name = f"{base_name}_clips"
        for ci, clip in enumerate(clips):
            progress_bar.progress(40 + int(55 * ci / max(len(clips), 1)), text=f"Saving clip {ci+1}/{len(clips)}...")
            try:
                final_path = place_clip(
                    output_dir=output_dir, clip_info=clip,
                    analysis={"description": f"Clip {ci+1} from {display_name}", "tags": [],
                               "category_description": f"Unsorted clips from {display_name}"},
                    folder_name=folder_name, source_video_name=display_name,
                )
                folders_used.add(folder_name)
                results_table.append({
                    "Clip": Path(final_path).name, "Folder": folder_name,
                    "Duration": clip["duration"], "Timestamp": clip["timestamp_in_source"],
                    "Description": f"Clip {ci+1}", "Tags": "",
                })
            except Exception as e:
                st.warning(f"Could not save clip {ci+1}: {e}")
    else:
        for ci, clip in enumerate(clips):
            progress_bar.progress(40 + int(55 * ci / max(len(clips), 1)), text=f"Analyzing clip {ci+1}/{len(clips)}...")

            try:
                frames = extract_frames(clip["path"], num_frames=num_frames)
            except Exception as e:
                st.warning(f"Frame extraction failed for clip {ci+1}: {e}")
                continue

            if not frames:
                st.warning(f"No frames for clip {ci+1}, skipping.")
                continue

            try:
                analysis = analyze_clip_frames(
                    client=client, frame_paths=frames,
                    source_video_name=display_name,
                    timestamp=clip["timestamp_in_source"],
                    granularity=granularity, model=model_name,
                    topic=topic,
                )
            except Exception as e:
                st.warning(f"GPT analysis failed for clip {ci+1}: {e}")
                cleanup_frames(frames)
                continue

            cleanup_frames(frames)

            try:
                folder_name = resolve_target_folder(
                    client=client, output_dir=output_dir,
                    suggested_category=analysis.get("suggested_category", "uncategorized"),
                    category_description=analysis.get("category_description", ""),
                    granularity=granularity, model=model_name,
                    topic=topic,
                    analysis_content_type=analysis.get("content_type", ""),
                )
            except Exception:
                folder_name = analysis.get("suggested_category", "uncategorized")

            try:
                final_path = place_clip(
                    output_dir=output_dir, clip_info=clip,
                    analysis=analysis, folder_name=folder_name,
                    source_video_name=display_name,
                )
            except Exception as e:
                st.warning(f"Could not place clip {ci+1}: {e}")
                continue

            folders_used.add(folder_name)
            results_table.append({
                "Clip": Path(final_path).name, "Folder": folder_name,
                "Duration": clip["duration"], "Timestamp": clip["timestamp_in_source"],
                "Description": analysis.get("description", ""),
                "Tags": ", ".join(analysis.get("tags", [])),
            })

    shutil.rmtree(raw_clips_dir, ignore_errors=True)
    register_processed_video(
        output_dir=output_dir, filename=display_name,
        file_hash=file_hash, clips_generated=len(results_table),
        folders_affected=sorted(folders_used),
    )

    progress_bar.progress(100, text="Done!")
    status_box.empty()

    if results_table:
        st.success(_t("sm_clips_saved", _lang, n=str(len(results_table)), f=str(len(folders_used)), folders=', '.join(sorted(folders_used))))
        st.dataframe(results_table, use_container_width=True)
    else:
        st.warning(_t("sm_no_clips_processed", _lang))

    return {"clips": len(results_table), "folders": sorted(folders_used)}


# ── Main render entry point ───────────────────────────────────────────────────
def render():
    _lang = st.session_state.get("lang", "en")
    _sm_init_state()

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:

        # ── Profile selector ─────────────────────────────────────────────────
        st.header(_t("sm_library_profile", _lang))

        profiles = st.session_state.sm_profiles
        profile_names = list(profiles.keys())

        if not profile_names:
            st.warning(_t("sm_no_profiles", _lang))
            current_profile = ""
        else:
            current_idx = profile_names.index(st.session_state.sm_active_profile) if st.session_state.sm_active_profile in profile_names else 0
            selected_profile = st.selectbox(
                "Active library",
                profile_names,
                index=current_idx,
                key="sm_profile_selector",
            )
            if selected_profile != st.session_state.sm_active_profile:
                st.session_state.sm_active_profile = selected_profile
                # sync Browse Library dir
                st.session_state.sm_browse_dir = _sm_active_output_dir()
                _sm_persist_config()
                st.rerun()

            current_profile = st.session_state.sm_active_profile
            prof = profiles.get(current_profile, {})

            # key includes profile name so widgets fully rebuild on profile switch
            new_out = st.text_input(
                "Output directory",
                value=prof.get("output_dir", ""),
                key=f"sm_prof_output_{current_profile}",
                placeholder="/Users/yourname/Videos/NFL",
            )
            new_topic = st.text_input(
                "Topic hint for GPT",
                value=prof.get("topic", ""),
                key=f"sm_prof_topic_{current_profile}",
                placeholder="e.g. NFL American Football highlights",
                help="GPT uses this to name folders with topic-specific terminology.",
            )

            col_save, col_del = st.columns([3, 1])
            with col_save:
                if st.button(_t("sm_save_profile", _lang), use_container_width=True, key="sm_btn_save_profile"):
                    if new_out and not Path(new_out).is_absolute():
                        st.error(_t("sm_path_must_start", _lang))
                    else:
                        profiles[current_profile]["output_dir"] = new_out
                        profiles[current_profile]["topic"] = new_topic
                        st.session_state.sm_profiles = profiles
                        st.session_state.sm_browse_dir = new_out
                        _sm_persist_config()
                        st.success(_t("sm_saved", _lang))
            with col_del:
                if st.button("🗑", help=f"Delete profile '{current_profile}'", use_container_width=True, key="sm_btn_del_profile"):
                    st.session_state[f"sm_confirm_del_profile_{current_profile}"] = True

            if st.session_state.get(f"sm_confirm_del_profile_{current_profile}"):
                st.warning(_t("sm_delete_confirm", _lang, name=current_profile))
                c1, c2 = st.columns(2)
                with c1:
                    if st.button(_t("sm_yes_delete", _lang), key="sm_confirm_del_yes"):
                        del profiles[current_profile]
                        st.session_state.sm_profiles = profiles
                        st.session_state.sm_active_profile = list(profiles.keys())[0] if profiles else ""
                        st.session_state[f"sm_confirm_del_profile_{current_profile}"] = False
                        _sm_persist_config()
                        st.rerun()
                with c2:
                    if st.button(_t("sm_cancel", _lang), key="sm_confirm_del_no"):
                        st.session_state[f"sm_confirm_del_profile_{current_profile}"] = False
                        st.rerun()

        # New profile
        st.divider()
        with st.expander(_t("sm_new_profile", _lang)):
            new_name = st.text_input("Profile name", placeholder="NFL", key="sm_new_profile_name")
            new_dir  = st.text_input("Output directory", placeholder="/Users/yourname/Videos/NFL", key="sm_new_profile_dir")
            new_top  = st.text_input("Topic hint", placeholder="NFL American Football games", key="sm_new_profile_topic")
            if st.button(_t("sm_create_btn", _lang), key="sm_btn_create_profile"):
                if not new_name.strip():
                    st.error(_t("sm_name_required", _lang))
                elif new_name in profiles:
                    st.error(f"'{new_name}' already exists.")
                elif new_dir and not Path(new_dir).is_absolute():
                    st.error(_t("sm_path_must_start", _lang))
                else:
                    profiles[new_name] = {"output_dir": new_dir, "topic": new_top}
                    st.session_state.sm_profiles = profiles
                    st.session_state.sm_active_profile = new_name
                    st.session_state.sm_browse_dir = new_dir
                    _sm_persist_config()
                    st.success(f"Profile '{new_name}' created!")
                    st.rerun()

        st.divider()

        # ── API settings ─────────────────────────────────────────────────────
        st.header(_t("sm_api_settings", _lang))

        api_key = st.text_input(
            "API Key", type="password",
            value=st.session_state.sm_cfg_api_key,
            placeholder="sk-...",
            key="sm_api_key_input",
        )
        base_url = st.text_input(
            "API Base URL (optional)",
            value=st.session_state.sm_cfg_base_url,
            placeholder="https://api.openai.com/v1",
            key="sm_base_url_input",
        )
        model_name = st.text_input(
            "Model name", value=st.session_state.sm_cfg_model,
            help="e.g. gpt-4o, deepseek-chat",
            key="sm_model_name_input",
        )

        st.divider()
        st.subheader(_t("sm_scene_detection", _lang))
        threshold = st.slider(
            "Sensitivity (lower = more cuts)",
            min_value=5.0, max_value=80.0,
            value=st.session_state.sm_cfg_threshold, step=1.0,
            help="Recommended: 40–55 for sports, 27 for fast-cut edits.",
            key="sm_threshold_slider",
        )
        if threshold < 30:
            st.caption(_t("sm_sensitivity_high", _lang))
        elif threshold > 55:
            st.caption(_t("sm_sensitivity_low", _lang))

        min_clip_enabled = st.toggle(
            "Filter short clips",
            value=st.session_state.sm_cfg_min_clip_enabled,
            help="Discard clips shorter than the minimum duration.",
            key="sm_min_clip_enabled_toggle",
        )
        if min_clip_enabled:
            min_clip_sec = st.slider(
                "Min clip duration (seconds)",
                min_value=1.0, max_value=15.0,
                value=st.session_state.sm_cfg_min_clip_sec, step=0.5,
                key="sm_min_clip_sec_slider",
            )
        else:
            min_clip_sec = st.session_state.sm_cfg_min_clip_sec

        black_filter = st.toggle(
            "Filter black/dark clips",
            value=st.session_state.sm_cfg_black_filter,
            help="Discard clips that are predominantly black (transition screens, ad breaks).",
            key="sm_black_filter_toggle",
        )
        if black_filter:
            brightness_thr = st.slider(
                "Brightness threshold (0–255)",
                min_value=5.0, max_value=50.0,
                value=st.session_state.sm_cfg_brightness_thr, step=1.0,
                help="Clips with average brightness below this value are discarded.",
                key="sm_brightness_thr_slider",
            )
        else:
            brightness_thr = st.session_state.sm_cfg_brightness_thr

        st.subheader(_t("sm_gpt_analysis", _lang))
        num_frames = st.slider(
            "Frames per clip sent to GPT",
            min_value=1, max_value=8,
            value=st.session_state.sm_cfg_num_frames,
            key="sm_num_frames_slider",
        )
        granularity = st.select_slider(
            "Folder granularity",
            options=["coarse", "medium", "fine"],
            value=st.session_state.sm_cfg_granularity,
            key="sm_granularity_slider",
        )

        st.divider()
        if st.button(_t("sm_save_api", _lang), use_container_width=True, type="primary", key="sm_btn_save_api"):
            st.session_state.sm_cfg_api_key    = api_key
            st.session_state.sm_cfg_base_url   = base_url
            st.session_state.sm_cfg_model      = model_name
            st.session_state.sm_cfg_threshold      = threshold
            st.session_state.sm_cfg_num_frames     = num_frames
            st.session_state.sm_cfg_granularity    = granularity
            st.session_state.sm_cfg_min_clip_enabled = min_clip_enabled
            st.session_state.sm_cfg_min_clip_sec   = min_clip_sec
            st.session_state.sm_cfg_black_filter   = black_filter
            st.session_state.sm_cfg_brightness_thr = brightness_thr
            _sm_persist_config()
            st.success(_t("sm_saved", _lang))

        st.divider()
        st.caption(_t("sm_granularity_guide", _lang))
        st.caption("• coarse — broad (e.g. `touchdown`)")
        st.caption("• medium — balanced (e.g. `nfl_touchdown`)")
        st.caption("• fine — specific (e.g. `nfl_qb_scramble_td`)")

    # ── Header: show active profile ───────────────────────────────────────────
    ap = st.session_state.sm_active_profile
    if ap:
        prof_info = st.session_state.sm_profiles.get(ap, {})
        col_title, col_badge = st.columns([5, 2])
        with col_title:
            st.title(_t("sm_main_title", _lang))
        with col_badge:
            st.markdown(f"<br><span style='background:#1f77b4;color:white;padding:4px 12px;border-radius:20px;font-size:14px'>📁 {ap}</span>", unsafe_allow_html=True)
        if prof_info.get("topic"):
            st.caption(f"Topic: *{prof_info['topic']}*  ·  Output: `{prof_info.get('output_dir','—')}`")
    else:
        st.title(_t("sm_main_title", _lang))
        st.warning(_t("sm_no_profile_warning", _lang))
        return

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_process, tab_library = st.tabs([_t("sm_tab_process", _lang), _t("sm_tab_library", _lang)])

    # ════════════════════════════════════════════════════════════════════════
    # TAB 1 — Process Videos
    # ════════════════════════════════════════════════════════════════════════
    with tab_process:

        output_dir = _sm_active_output_dir()
        ok_dir, err_dir = _sm_validate_output_dir(output_dir)
        if not ok_dir:
            st.error(err_dir)
            return

        use_gpt = st.toggle("AI analyze & auto-categorize (GPT)", value=True,
            help="Off = pure split only, no GPT. Much faster and free.",
            key="sm_use_gpt_toggle")
        if not use_gpt:
            st.info(f"Pure split mode — clips saved to `{output_dir}/<video_name>_clips/`")

        st.divider()
        input_upload, input_local, input_youtube = st.tabs([_t("sm_tab_upload", _lang), _t("sm_tab_local", _lang), _t("sm_tab_youtube", _lang)])

        # ── Upload mode ───────────────────────────────────────────────────────
        with input_upload:
            st.caption(_t("sm_upload_caption", _lang))
            uploaded_files = st.file_uploader(
                "Select one or more videos",
                type=["mp4", "mov", "avi", "mkv", "m4v"],
                accept_multiple_files=True, key="sm_uploader",
            )

            if uploaded_files:
                ok_key, err_key = _sm_validate_api_key(api_key) if use_gpt else (True, "")
                if not ok_key:
                    st.warning(err_key)
                else:
                    st.write(f"**{len(uploaded_files)} file(s) ready.**")
                    if st.button(_t("sm_start_processing", _lang), type="primary", key="sm_btn_upload"):
                        client = _sm_make_openai_client(api_key, base_url) if use_gpt else None
                        overall_log = []
                        for uf in uploaded_files:
                            st.subheader(f"📹 {uf.name}")
                            with tempfile.TemporaryDirectory() as tmp_dir:
                                src_path = os.path.join(tmp_dir, uf.name)
                                with open(src_path, "wb") as f:
                                    f.write(uf.getbuffer())
                                result = _sm_process_video_file(src_path, uf.name, client, use_gpt,
                                                                threshold, num_frames, granularity, model_name)
                                overall_log.append({"file": uf.name, **result})

                        st.divider()
                        st.subheader(_t("sm_session_summary", _lang))
                        for item in overall_log:
                            st.write(f"• **{item['file']}** → {item['clips']} clip(s) in: {', '.join(item['folders']) or '—'}")

        # ── Local path mode ───────────────────────────────────────────────────
        with input_local:
            st.caption(_t("sm_local_caption", _lang))

            if "sm_local_paths_text" not in st.session_state:
                st.session_state.sm_local_paths_text = ""

            local_paths_raw = st.text_area(
                "Video file paths (one per line)",
                value=st.session_state.sm_local_paths_text,
                height=150,
                placeholder="/Users/yourname/Videos/match1.mp4\n/Users/yourname/Videos/match2.mp4",
                key="sm_local_paths_area",
            )

            enable_preview = st.toggle("Scene preview before processing", value=False,
                help="Detect scenes first, show thumbnails, let you deselect before GPT.", key="sm_enable_preview")

            local_paths = [p.strip() for p in local_paths_raw.splitlines() if p.strip()]

            if local_paths:
                missing = [p for p in local_paths if not Path(p).exists()]
                valid_paths = [p for p in local_paths if Path(p).exists()]

                for m in missing:
                    st.error(f"File not found: `{m}`")

                if valid_paths:
                    ok_key, err_key = _sm_validate_api_key(api_key) if use_gpt else (True, "")
                    if not ok_key:
                        st.warning(err_key)
                    else:
                        st.write(f"**{len(valid_paths)} valid file(s) ready.**")

                        # ── Preview mode ──────────────────────────────────────
                        if enable_preview and use_gpt:
                            if "sm_preview_data" not in st.session_state:
                                st.session_state.sm_preview_data = {}

                            if st.button(_t("sm_detect_scenes", _lang), key="sm_btn_preview"):
                                st.session_state.sm_preview_data = {}
                                for src_path in valid_paths:
                                    display_name = Path(src_path).name
                                    with st.spinner(f"Detecting scenes in {display_name}..."):
                                        try:
                                            _min_sec = st.session_state.sm_cfg_min_clip_sec if st.session_state.sm_cfg_min_clip_enabled else 0.5
                                            scenes = detect_scenes(src_path, threshold=threshold, min_clip_sec=_min_sec)
                                        except Exception as e:
                                            st.error(f"Scene detection failed: {e}")
                                            continue
                                    raw_dir = tempfile.mkdtemp()
                                    try:
                                        clips = split_video(src_path, scenes, raw_dir, Path(src_path).stem, min_clip_sec=_min_sec,
                                                            black_filter=st.session_state.sm_cfg_black_filter, brightness_threshold=st.session_state.sm_cfg_brightness_thr)
                                    except Exception as e:
                                        st.error(f"Splitting failed: {e}")
                                        shutil.rmtree(raw_dir, ignore_errors=True)
                                        continue
                                    thumbnails = []
                                    thumb_frame_sets = []
                                    for clip in clips:
                                        frames = extract_frames(clip["path"], num_frames=1)
                                        thumbnails.append(frames[0] if frames else None)
                                        thumb_frame_sets.append(frames)
                                    st.session_state.sm_preview_data[src_path] = {
                                        "display_name": display_name, "clips": clips,
                                        "thumbnails": thumbnails, "raw_dir": raw_dir,
                                        "thumb_frames": thumb_frame_sets,
                                        "selected": [True] * len(clips),
                                    }

                            if st.session_state.sm_preview_data:
                                any_selected = False
                                for src_path, pdata in st.session_state.sm_preview_data.items():
                                    st.subheader(f"📹 {pdata['display_name']} — {len(pdata['clips'])} scenes")
                                    cols_per_row = 4
                                    for row_start in range(0, len(pdata["clips"]), cols_per_row):
                                        cols = st.columns(cols_per_row)
                                        for ci in range(row_start, min(row_start + cols_per_row, len(pdata["clips"]))):
                                            clip = pdata["clips"][ci]
                                            thumb = pdata["thumbnails"][ci]
                                            with cols[ci % cols_per_row]:
                                                if thumb and Path(thumb).exists():
                                                    st.image(thumb, use_container_width=True)
                                                else:
                                                    st.markdown(_t("sm_no_thumbnail", _lang))
                                                checked = st.checkbox(
                                                    f"Scene {ci+1} · {clip['duration']}",
                                                    value=pdata["selected"][ci],
                                                    key=f"sm_chk_{src_path}_{ci}",
                                                )
                                                pdata["selected"][ci] = checked
                                                if checked:
                                                    any_selected = True

                                if any_selected and st.button(_t("sm_process_selected", _lang), type="primary", key="sm_btn_preview_go"):
                                    client = _sm_make_openai_client(api_key, base_url)
                                    overall_log = []
                                    for src_path, pdata in st.session_state.sm_preview_data.items():
                                        display_name = pdata["display_name"]
                                        st.subheader(f"📹 {display_name}")
                                        selected_clips = [c for i, c in enumerate(pdata["clips"]) if pdata["selected"][i]]
                                        file_hash = compute_file_hash(src_path)
                                        folders_used = set()
                                        results_table = []

                                        for ci, clip in enumerate(selected_clips):
                                            prog = st.progress(int(100 * ci / max(len(selected_clips), 1)),
                                                               text=f"Analyzing {ci+1}/{len(selected_clips)}...")
                                            frames = extract_frames(clip["path"], num_frames=num_frames)
                                            if not frames:
                                                continue
                                            try:
                                                analysis = analyze_clip_frames(
                                                    client=client, frame_paths=frames,
                                                    source_video_name=display_name,
                                                    timestamp=clip["timestamp_in_source"],
                                                    granularity=granularity, model=model_name,
                                                    topic=_sm_active_topic(),
                                                )
                                            except Exception as e:
                                                st.warning(f"GPT failed for scene {ci+1}: {e}")
                                                cleanup_frames(frames)
                                                continue
                                            cleanup_frames(frames)

                                            try:
                                                folder_name = resolve_target_folder(
                                                    client=client, output_dir=output_dir,
                                                    suggested_category=analysis.get("suggested_category", "uncategorized"),
                                                    category_description=analysis.get("category_description", ""),
                                                    granularity=granularity, model=model_name,
                                                    topic=_sm_active_topic(),
                                                    analysis_content_type=analysis.get("content_type", ""),
                                                )
                                            except Exception:
                                                folder_name = analysis.get("suggested_category", "uncategorized")

                                            try:
                                                final_path = place_clip(
                                                    output_dir=output_dir, clip_info=clip,
                                                    analysis=analysis, folder_name=folder_name,
                                                    source_video_name=display_name,
                                                )
                                            except Exception as e:
                                                st.warning(f"Could not place scene {ci+1}: {e}")
                                                continue

                                            folders_used.add(folder_name)
                                            results_table.append({
                                                "Clip": Path(final_path).name, "Folder": folder_name,
                                                "Duration": clip["duration"], "Timestamp": clip["timestamp_in_source"],
                                                "Description": analysis.get("description", ""),
                                                "Tags": ", ".join(analysis.get("tags", [])),
                                            })
                                            prog.progress(100)

                                        register_processed_video(
                                            output_dir=output_dir, filename=display_name,
                                            file_hash=file_hash, clips_generated=len(results_table),
                                            folders_affected=sorted(folders_used),
                                        )
                                        shutil.rmtree(pdata["raw_dir"], ignore_errors=True)
                                        if results_table:
                                            st.success(_t("sm_clips_saved_short", _lang, n=str(len(results_table))))
                                            st.dataframe(results_table, use_container_width=True)
                                        overall_log.append({"file": display_name, "clips": len(results_table), "folders": sorted(folders_used)})

                                    for pdata in st.session_state.sm_preview_data.values():
                                        for frames in pdata.get("thumb_frames", []):
                                            cleanup_frames(frames)
                                    st.session_state.sm_preview_data = {}
                                    st.divider()
                                    st.subheader(_t("sm_session_summary", _lang))
                                    for item in overall_log:
                                        st.write(f"• **{item['file']}** → {item['clips']} clip(s) in: {', '.join(item['folders'])}")

                        # ── Normal mode ───────────────────────────────────────
                        else:
                            if st.button(_t("sm_start_processing", _lang), type="primary", key="sm_btn_local"):
                                client = _sm_make_openai_client(api_key, base_url) if use_gpt else None
                                overall_log = []
                                for src_path in valid_paths:
                                    display_name = Path(src_path).name
                                    st.subheader(f"📹 {display_name}")
                                    result = _sm_process_video_file(src_path, display_name, client, use_gpt,
                                                                    threshold, num_frames, granularity, model_name)
                                    overall_log.append({"file": display_name, **result})

                                st.divider()
                                st.subheader(_t("sm_session_summary", _lang))
                                for item in overall_log:
                                    st.write(f"• **{item['file']}** → {item['clips']} clip(s) in: {', '.join(item['folders']) or '—'}")

        # ── yt-dlp tab ────────────────────────────────────────────────────────
        with input_youtube:
            ytdlp_ok, ytdlp_ver = check_ytdlp()
            if not ytdlp_ok:
                st.error(f"yt-dlp not available: {ytdlp_ver}")
                st.code("brew install yt-dlp", language="bash")
                return

            st.caption(_t("sm_ytdlp_caption", _lang, ver=ytdlp_ver))

            yt_urls_raw = st.text_area(
                "Video URLs (one per line)",
                height=130,
                placeholder="https://www.youtube.com/watch?v=...\nhttps://www.instagram.com/reel/...\nhttps://www.tiktok.com/@user/video/...",
                key="sm_yt_urls",
            )

            col_q, col_gpt = st.columns(2)
            with col_q:
                yt_quality = st.selectbox(
                    "Download quality",
                    ["1080", "720", "best"],
                    index=0,
                    key="sm_yt_quality",
                )
            with col_gpt:
                yt_use_gpt = st.toggle("AI analyze & categorize", value=True, key="sm_yt_use_gpt",
                    help="Off = pure split, no GPT.")

            yt_urls = [u.strip() for u in yt_urls_raw.splitlines() if u.strip()]

            if yt_urls:
                invalid = [u for u in yt_urls if not is_valid_url(u)]
                valid_yt_urls = [u for u in yt_urls if is_valid_url(u)]

                for u in invalid:
                    st.warning(f"Not a valid URL (must start with http/https): `{u}`")

                if valid_yt_urls:
                    ok_key, err_key = _sm_validate_api_key(api_key) if yt_use_gpt else (True, "")
                    if not ok_key:
                        st.warning(err_key)
                    else:
                        # Preview video info
                        if st.button("🔎 Preview Videos", key="sm_btn_yt_preview"):
                            st.session_state.sm_yt_infos = []
                            for url in valid_yt_urls:
                                with st.spinner(f"Fetching info for {url[:60]}..."):
                                    try:
                                        info = get_video_info(url)
                                        st.session_state.sm_yt_infos.append(info)
                                    except RuntimeError as e:
                                        st.error(f"❌ {url[:60]}: {e}")

                        if st.session_state.get("sm_yt_infos"):
                            st.divider()
                            st.subheader("Videos to download")
                            for info in st.session_state.sm_yt_infos:
                                col_thumb, col_meta = st.columns([1, 3])
                                with col_thumb:
                                    if info.get("thumbnail"):
                                        st.image(info["thumbnail"], use_container_width=True)
                                with col_meta:
                                    st.markdown(f"**{info['title']}**")
                                    st.caption(f"{info.get('uploader','')} · {info['duration']}")
                                    st.caption(info["url"])

                            st.divider()

                            # Disk space check (rough estimate: 500 MB per video)
                            est_bytes = len(st.session_state.sm_yt_infos) * 500 * 1024 * 1024
                            tmp_check_dir = tempfile.gettempdir()
                            space_ok, space_msg = check_disk_space(tmp_check_dir, est_bytes)
                            if not space_ok:
                                st.error(f"Disk space warning: {space_msg}")
                            else:
                                st.caption(f"Disk: {space_msg}")

                            if st.button("⬇️ Download & Process", type="primary", key="sm_btn_yt_go"):
                                client = _sm_make_openai_client(api_key, base_url) if yt_use_gpt else None
                                overall_log = []

                                for info in st.session_state.sm_yt_infos:
                                    url = info["url"]
                                    title = info["title"]
                                    st.subheader(f"▶️ {title}")

                                    # Download phase
                                    dl_progress = st.progress(0, text="Starting download...")
                                    dl_status = st.empty()

                                    def on_dl_progress(pct, speed, eta, _bar=dl_progress):
                                        _bar.progress(
                                            min(int(pct), 99),
                                            text=f"Downloading {pct:.1f}% · {speed} · ETA {eta}"
                                            if speed else f"Downloading {pct:.1f}%",
                                        )

                                    tmp_dl_dir = tempfile.mkdtemp(prefix="ytdl_")
                                    try:
                                        video_path = download_video(
                                            url=url,
                                            output_dir=tmp_dl_dir,
                                            quality=yt_quality,
                                            progress_callback=on_dl_progress,
                                        )
                                        dl_progress.progress(100, text="Download complete.")
                                        dl_status.success(f"Downloaded: `{Path(video_path).name}`")
                                    except RuntimeError as e:
                                        dl_progress.empty()
                                        st.error(f"Download failed: {e}")
                                        shutil.rmtree(tmp_dl_dir, ignore_errors=True)
                                        continue

                                    # Process phase — reuse existing pipeline
                                    display_name = Path(video_path).name
                                    result = _sm_process_video_file(video_path, display_name, client, yt_use_gpt,
                                                                    threshold, num_frames, granularity, model_name)
                                    overall_log.append({"file": title, **result})

                                    # Clean up download temp dir
                                    shutil.rmtree(tmp_dl_dir, ignore_errors=True)

                                st.session_state.sm_yt_infos = []
                                st.divider()
                                st.subheader(_t("sm_session_summary", _lang))
                                for item in overall_log:
                                    folders_str = ", ".join(item["folders"]) if item["folders"] else "—"
                                    st.write(f"• **{item['file']}** → {item['clips']} clip(s) in: {folders_str}")

    # ════════════════════════════════════════════════════════════════════════
    # TAB 2 — Browse Library
    # ════════════════════════════════════════════════════════════════════════
    with tab_library:

        if "sm_browse_dir" not in st.session_state:
            st.session_state.sm_browse_dir = _sm_active_output_dir()

        browse_dir = st.text_input(
            "Library directory",
            value=st.session_state.sm_browse_dir,
            key="sm_browse_dir_input",
            placeholder="/Users/yourname/clips",
        )
        st.session_state.sm_browse_dir = browse_dir

        if not browse_dir:
            st.info("No output directory set for this profile.")
            return
        if not Path(browse_dir).exists():
            st.warning("Directory does not exist yet — process some videos first.")
            return

        folders = list_existing_folders(browse_dir)
        if not folders:
            st.info("No categorized folders found yet. Process some videos first.")
            return

        # Search
        search_query = st.text_input("🔍 Search by tag or keyword", placeholder="e.g. touchdown, scramble", key="sm_search_query")

        # Export CSV
        def build_csv(browse_path: str, folder_list: list) -> str:
            rows = []
            for fi in folder_list:
                fp = Path(browse_path) / fi["folder_name"]
                meta = load_folder_metadata(str(fp))
                for c in meta.get("clips", []):
                    rows.append({
                        "folder": fi["folder_name"], "filename": c["filename"],
                        "source_video": c["source_video"], "duration": c["duration"],
                        "timestamp": c["timestamp_in_source"], "description": c["description"],
                        "tags": ", ".join(c.get("tags", [])), "analyzed_at": c.get("analyzed_at", "")[:10],
                    })
            buf = io.StringIO()
            if rows:
                writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            return buf.getvalue()

        col_stats, col_export = st.columns([3, 1])
        with col_stats:
            total_clips = sum(
                len(load_folder_metadata(str(Path(browse_dir) / f["folder_name"])).get("clips", []))
                for f in folders
            )
            st.write(f"**{len(folders)} folder(s)** · **{total_clips} clip(s)** total")
        with col_export:
            st.download_button("⬇️ Export CSV", data=build_csv(browse_dir, folders),
                file_name=f"{ap}_library.csv", mime="text/csv", use_container_width=True,
                key="sm_export_csv")

        st.divider()

        # Management tools
        with st.expander("🛠 Folder Management Tools"):
            mgmt_merge, mgmt_rename, mgmt_delete = st.tabs(["Merge Folders", "Rename Folder", "Delete Folder"])
            folder_names = [f["folder_name"] for f in sorted(folders, key=lambda x: x["folder_name"])]

            with mgmt_merge:
                st.caption("Move all clips from source into destination, then delete source.")
                c1, c2 = st.columns(2)
                with c1:
                    merge_src = st.selectbox("Source (deleted after)", folder_names, key="sm_merge_src")
                with c2:
                    merge_dst_opts = [f for f in folder_names if f != merge_src]
                    merge_dst = st.selectbox("Destination", merge_dst_opts, key="sm_merge_dst") if merge_dst_opts else None
                if merge_dst and st.button("Merge", key="sm_btn_merge"):
                    from scene_manager.metadata import next_clip_index as _nci
                    src_p = Path(browse_dir) / merge_src
                    dst_p = Path(browse_dir) / merge_dst
                    src_m = load_folder_metadata(str(src_p))
                    for clip in src_m.get("clips", []):
                        old_f = src_p / clip["filename"]
                        if not old_f.exists():
                            continue
                        # Re-load dst metadata each iteration so index is always fresh
                        dst_m = load_folder_metadata(str(dst_p))
                        new_fn = f"{merge_dst}_{_nci(str(dst_p)):03d}.mp4"
                        shutil.move(str(old_f), str(dst_p / new_fn))
                        dst_m["clips"].append({**clip, "filename": new_fn})
                        save_folder_metadata(str(dst_p), dst_m)
                    shutil.rmtree(str(src_p))
                    st.success(f"Merged **{merge_src}** → **{merge_dst}**.")
                    st.rerun()

            with mgmt_rename:
                st.caption("Rename folder and all clip files inside.")
                rename_src = st.selectbox("Folder to rename", folder_names, key="sm_rename_src")
                rename_new = st.text_input("New name (snake_case)", key="sm_rename_new")
                if rename_new and st.button("Rename", key="sm_btn_rename"):
                    rename_new = rename_new.strip().lower().replace(" ", "_")
                    src_p = Path(browse_dir) / rename_src
                    dst_p = Path(browse_dir) / rename_new
                    if dst_p.exists():
                        st.error(f"`{rename_new}` already exists.")
                    else:
                        meta = load_folder_metadata(str(src_p))
                        new_clips = []
                        for i, clip in enumerate(meta.get("clips", []), start=1):
                            old_f = src_p / clip["filename"]
                            new_fn = f"{rename_new}_{i:03d}.mp4"
                            if old_f.exists():
                                shutil.move(str(old_f), str(src_p / new_fn))
                            new_clips.append({**clip, "filename": new_fn})
                        meta["folder_name"] = rename_new
                        meta["clips"] = new_clips
                        src_p.rename(dst_p)
                        save_folder_metadata(str(dst_p), meta)
                        st.success(f"Renamed **{rename_src}** → **{rename_new}**.")
                        st.rerun()

            with mgmt_delete:
                st.caption("Permanently delete a folder and all its clips.")
                del_target = st.selectbox("Folder to delete", folder_names, key="sm_del_target")
                confirm_del = st.checkbox(f"Confirm permanent deletion of `{del_target}`", key="sm_confirm_del_folder")
                if confirm_del and st.button("🗑 Delete", type="primary", key="sm_btn_delete_folder"):
                    shutil.rmtree(str(Path(browse_dir) / del_target))
                    st.success(f"Deleted **{del_target}**.")
                    st.rerun()

        st.divider()

        # ── Batch delete state ────────────────────────────────────────────────
        if "sm_batch_delete_set" not in st.session_state:
            st.session_state.sm_batch_delete_set = set()

        batch_mode = st.toggle("Select clips for batch delete", value=False, key="sm_batch_mode")
        if batch_mode and st.session_state.sm_batch_delete_set:
            n = len(st.session_state.sm_batch_delete_set)
            confirm_batch = st.checkbox(f"Confirm permanent deletion of {n} clip(s)", key="sm_confirm_batch_del")
            if confirm_batch and st.button(f"🗑 Delete {n} selected clip(s)", type="primary", key="sm_btn_batch_del"):
                for key in list(st.session_state.sm_batch_delete_set):
                    folder_name, filename = key.split("||", 1)
                    fp = Path(browse_dir) / folder_name
                    clip_file = fp / filename
                    try:
                        clip_file.unlink(missing_ok=True)
                    except OSError:
                        pass
                    remove_clip_from_metadata(str(fp), filename)
                    # Remove empty folders
                    remaining = load_folder_metadata(str(fp)).get("clips", [])
                    if not remaining:
                        shutil.rmtree(str(fp), ignore_errors=True)
                st.session_state.sm_batch_delete_set = set()
                st.success("Deleted selected clips.")
                st.rerun()

        st.divider()

        # ── Folder list ───────────────────────────────────────────────────────
        for folder_info in sorted(folders, key=lambda x: x["folder_name"]):
            folder_path = Path(browse_dir) / folder_info["folder_name"]
            meta = load_folder_metadata(str(folder_path))
            clips = meta.get("clips", [])

            if search_query:
                q = search_query.lower()
                clips = [c for c in clips if
                         q in c.get("description", "").lower() or
                         q in " ".join(c.get("tags", [])).lower() or
                         q in c.get("filename", "").lower() or
                         q in folder_info["folder_name"].lower()]
                if not clips:
                    continue

            with st.expander(f"📁 {folder_info['folder_name']} ({len(clips)} clips) — {folder_info['category_description']}"):
                for c in clips:
                    clip_file = folder_path / c["filename"]
                    batch_key = f"{folder_info['folder_name']}||{c['filename']}"

                    # ── Header row: checkbox (batch) + filename + actions ─────
                    col_chk, col_info, col_actions = st.columns([0.5, 5, 2])

                    with col_chk:
                        if batch_mode:
                            checked = st.checkbox(
                                "", value=batch_key in st.session_state.sm_batch_delete_set,
                                key=f"sm_chkdel_{batch_key}",
                                label_visibility="collapsed",
                            )
                            if checked:
                                st.session_state.sm_batch_delete_set.add(batch_key)
                            else:
                                st.session_state.sm_batch_delete_set.discard(batch_key)

                    with col_info:
                        st.markdown(
                            f"**{c['filename']}** · {c['duration']} · `{c['timestamp_in_source']}`  \n"
                            f"{c['description']}  \n"
                            f"Tags: `{'`, `'.join(c.get('tags', []) or ['—'])}`"
                        )

                    with col_actions:
                        # Move
                        move_target = st.selectbox(
                            "Move to",
                            ["—"] + [f["folder_name"] for f in folders if f["folder_name"] != folder_info["folder_name"]],
                            key=f"sm_move_{batch_key}",
                            label_visibility="collapsed",
                        )
                        if move_target != "—":
                            confirmed = st.checkbox("Confirm move", key=f"sm_confirm_move_{batch_key}")
                            if confirmed and st.button("Move", key=f"sm_btn_move_{batch_key}"):
                                from scene_manager.metadata import next_clip_index as _nci
                                dst_folder = Path(browse_dir) / move_target
                                dst_folder.mkdir(parents=True, exist_ok=True)
                                new_idx = _nci(str(dst_folder))
                                new_fn = f"{move_target}_{new_idx:03d}.mp4"
                                shutil.move(str(clip_file), str(dst_folder / new_fn))
                                remove_clip_from_metadata(str(folder_path), c["filename"])
                                dst_meta = load_folder_metadata(str(dst_folder))
                                dst_meta["clips"].append({**c, "filename": new_fn})
                                save_folder_metadata(str(dst_folder), dst_meta)
                                st.success(f"Moved to **{move_target}**.")
                                st.rerun()

                        # Re-analyze
                        if clip_file.exists() and st.button("🔄 Re-analyze", key=f"sm_btn_reanalyze_{batch_key}"):
                            if not api_key:
                                st.warning("API key not set.")
                            else:
                                with st.spinner(f"Re-analyzing {c['filename']}..."):
                                    try:
                                        frames = extract_frames(str(clip_file), num_frames=num_frames)
                                        if frames:
                                            _client = _sm_make_openai_client(api_key, base_url)
                                            new_analysis = analyze_clip_frames(
                                                client=_client, frame_paths=frames,
                                                source_video_name=c.get("source_video", ""),
                                                timestamp=c.get("timestamp_in_source", ""),
                                                granularity=granularity, model=model_name,
                                                topic=_sm_active_topic(),
                                            )
                                            cleanup_frames(frames)
                                            new_folder = resolve_target_folder(
                                                client=_client, output_dir=browse_dir,
                                                suggested_category=new_analysis.get("suggested_category", "uncategorized"),
                                                category_description=new_analysis.get("category_description", ""),
                                                granularity=granularity, model=model_name,
                                                topic=_sm_active_topic(),
                                                analysis_content_type=new_analysis.get("content_type", ""),
                                            )
                                            if new_folder != folder_info["folder_name"]:
                                                # Move to new folder
                                                dst_folder = Path(browse_dir) / new_folder
                                                dst_folder.mkdir(parents=True, exist_ok=True)
                                                if not (dst_folder / "metadata.json").exists():
                                                    save_folder_metadata(str(dst_folder), {
                                                        "folder_name": new_folder,
                                                        "category_description": new_analysis.get("category_description", ""),
                                                        "content_type": new_analysis.get("content_type", ""),
                                                        "clips": [],
                                                    })
                                                from scene_manager.metadata import next_clip_index as _nci
                                                new_idx = _nci(str(dst_folder))
                                                new_fn = f"{new_folder}_{new_idx:03d}.mp4"
                                                dst_meta = load_folder_metadata(str(dst_folder))
                                                shutil.move(str(clip_file), str(dst_folder / new_fn))
                                                remove_clip_from_metadata(str(folder_path), c["filename"])
                                                dst_meta["clips"].append({
                                                    **c, "filename": new_fn,
                                                    "description": new_analysis.get("description", ""),
                                                    "tags": new_analysis.get("tags", []),
                                                })
                                                save_folder_metadata(str(dst_folder), dst_meta)
                                                st.success(f"Re-categorized → **{new_folder}**")
                                            else:
                                                update_clip_in_metadata(
                                                    str(folder_path), c["filename"],
                                                    description=new_analysis.get("description", ""),
                                                    tags=new_analysis.get("tags", []),
                                                )
                                                st.success("Updated description & tags.")
                                            st.rerun()
                                    except Exception as e:
                                        st.warning(f"Re-analyze failed: {e}")

                    # ── Video player (lazy) ───────────────────────────────────
                    if clip_file.exists():
                        play_key = f"sm_play_{batch_key}"
                        if st.button("▶ Play", key=play_key):
                            st.session_state[play_key] = not st.session_state.get(play_key, False)
                        if st.session_state.get(play_key):
                            st.video(str(clip_file))
                    else:
                        st.caption(_t("hc_file_not_found", _lang))

                    st.divider()
            st.divider()
