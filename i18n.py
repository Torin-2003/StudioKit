"""
i18n.py — Minimal bilingual string table for StudioKit.
Supports: "en" (English), "zh" (Chinese Simplified).
"""
import locale

STRINGS: dict[str, dict[str, str]] = {
    # ── App chrome ────────────────────────────────────────────────
    "app_title":            {"en": "StudioKit",             "zh": "StudioKit"},
    "page_title_activate":  {"en": "StudioKit — Activate",  "zh": "StudioKit — 激活"},
    # ── Tool names ────────────────────────────────────────────────
    "tool_hypecutter":      {"en": "✂️ HypeCutter",         "zh": "✂️ 剪辑助手"},
    "tool_scene_manager":   {"en": "🎬 Scene Manager",      "zh": "🎬 场景管理器"},
    # ── License gate ─────────────────────────────────────────────
    "activate_title":       {"en": "🔑 Activate StudioKit", "zh": "🔑 激活 StudioKit"},
    "license_none":         {"en": "No license found. Enter your license key to activate.",
                             "zh": "未找到许可证，请输入许可证密钥以激活。"},
    "license_expired":      {"en": "Your license has expired. Please renew.",
                             "zh": "许可证已过期，请续费。"},
    "license_mismatch":     {"en": "This license is bound to another machine.",
                             "zh": "此许可证已绑定其他设备。"},
    "license_tampered":     {"en": "License file is corrupted. Please re-activate.",
                             "zh": "许可证文件已损坏，请重新激活。"},
    "license_invalid":      {"en": "Invalid license. Please re-activate.",
                             "zh": "许可证无效，请重新激活。"},
    "license_required":     {"en": "License required.",     "zh": "需要许可证。"},
    "license_key_label":    {"en": "License Key",           "zh": "许可证密钥"},
    "license_key_placeholder": {"en": "Paste your license key here",
                                "zh": "在此粘贴许可证密钥"},
    "activate_btn":         {"en": "Activate",              "zh": "激活"},
    "activate_empty_err":   {"en": "Please enter a license key.",
                             "zh": "请输入许可证密钥。"},
    "activate_success":     {"en": "✅ Activated! Reloading…", "zh": "✅ 激活成功！正在重载…"},
    "activate_fail":        {"en": "Activation failed.",    "zh": "激活失败。"},
    "network_error":        {"en": "Network error",         "zh": "网络错误"},
    # ── Sidebar license status ────────────────────────────────────
    "dev_mode_caption":     {"en": "🛠️ Dev Mode — license bypass active",
                             "zh": "🛠️ 开发模式 — 已绕过许可证验证"},
    "licensed_lifetime":    {"en": "· Lifetime",            "zh": "· 终身授权"},
    "licensed_expires":     {"en": "· Expires in {days}d",  "zh": "· 剩余 {days} 天"},
    "licensed_ok":          {"en": "✅ Licensed {exp_label}","zh": "✅ 已授权 {exp_label}"},
    "plan_caption":         {"en": "Plan: **{plan}**  |  Machine bound",
                             "zh": "套餐：**{plan}**  |  设备绑定"},
    "no_license":           {"en": "⚠️ No license",         "zh": "⚠️ 未授权"},
    # ── Language switcher ─────────────────────────────────────────
    "lang_en":              {"en": "EN",                    "zh": "EN"},
    "lang_zh":              {"en": "中文",                  "zh": "中文"},
    # ── HypeCutter sidebar ────────────────────────────────────────
    "hc_settings_title":        {"en": "⚙️ Settings",               "zh": "⚙️ 设置"},
    "hc_api_section":           {"en": "🔑 API",                    "zh": "🔑 API"},
    "hc_clip_settings":         {"en": "🎬 Clip Settings",          "zh": "🎬 剪辑设置"},
    "hc_download_settings":     {"en": "⬇️ Download Settings",      "zh": "⬇️ 下载设置"},
    "hc_whisper_section":       {"en": "🎙️ Whisper Model",          "zh": "🎙️ Whisper 模型"},
    "hc_save_api_profile":      {"en": "💾 Save API Profile",       "zh": "💾 保存 API 配置"},
    "hc_save_configuration":    {"en": "💾 Save Configuration",     "zh": "💾 保存设置"},
    "hc_api_saved":             {"en": "✅ {provider} profile saved.", "zh": "✅ {provider} 配置已保存。"},
    "hc_config_saved":          {"en": "✅ Saved — settings will persist after refresh.", "zh": "✅ 已保存 — 刷新后设置保持不变。"},
    "hc_vertical_crop":         {"en": "Vertical 9:16 output",      "zh": "竖屏 9:16 输出"},
    "hc_burn_subtitles":        {"en": "Burn-in subtitles",         "zh": "烧录字幕"},
    "hc_remove_silence":        {"en": "Remove silence",            "zh": "去除静默段"},
    "hc_auto_delete":           {"en": "Auto-delete source after processing", "zh": "处理后自动删除源文件"},
    "hc_max_resolution":        {"en": "Max download resolution",   "zh": "最大下载分辨率"},
    # ── HypeCutter main area ──────────────────────────────────────
    "hc_main_title":            {"en": "✂️ AutoHighlight Pro Max",  "zh": "✂️ 自动高光剪辑"},
    "hc_tab_url":               {"en": "🌐 URL",                    "zh": "🌐 链接"},
    "hc_tab_file":              {"en": "📁 File",                   "zh": "📁 文件"},
    "hc_tab_history":           {"en": "🕘 History",                "zh": "🕘 历史记录"},
    "hc_run_btn":               {"en": "🚀 Run",                    "zh": "🚀 运行"},
    "hc_clear_btn":             {"en": "🗑️ Clear",                  "zh": "🗑️ 清除"},
    "hc_open_folder":           {"en": "📂 Open Folder",            "zh": "📂 打开文件夹"},
    "hc_output_folder":         {"en": "📂 Output Folder",          "zh": "📂 输出文件夹"},
    "hc_generated_clips":       {"en": "🏆 Generated Clips",        "zh": "🏆 生成的片段"},
    "hc_no_api_key":            {"en": "Enter your API key in the sidebar first.", "zh": "请先在侧边栏输入 API 密钥。"},
    "hc_no_projects":           {"en": "No projects yet. Process a video to get started.", "zh": "暂无项目，处理视频后即可在这里查看。"},
    "hc_file_not_found":        {"en": "_(file not found on disk)_", "zh": "_(文件在磁盘上未找到)_"},
    "hc_no_clips":              {"en": "No clips saved yet.",        "zh": "暂无保存的片段。"},
    "hc_delete_confirm":        {"en": "Delete this project and all its clip files?", "zh": "确定删除此项目及所有片段文件？"},
    "hc_delete_btn":            {"en": "🗑️ Delete",                 "zh": "🗑️ 删除"},
    "hc_rename_btn":            {"en": "✏️ Rename",                 "zh": "✏️ 重命名"},
    "hc_cancel_btn":            {"en": "Cancel",                    "zh": "取消"},
    "hc_output_file_not_found": {"en": "Output file not found.",    "zh": "输出文件未找到。"},
    "hc_render_failed":         {"en": "Render failed",             "zh": "渲染失败"},
    "hc_projects_found":        {"en": "{n} project(s) found",      "zh": "找到 {n} 个项目"},
    "hc_date_filter":           {"en": "Filter by date",            "zh": "按日期筛选"},
    "hc_search":                {"en": "Search projects",           "zh": "搜索项目"},
    "hc_all_time":              {"en": "All time",                  "zh": "全部"},
    "hc_today":                 {"en": "Today",                     "zh": "今天"},
    "hc_this_week":             {"en": "This week",                 "zh": "本周"},
    "hc_this_month":            {"en": "This month",                "zh": "本月"},
    # ── Scene Manager sidebar ─────────────────────────────────────
    "sm_library_profile":       {"en": "📁 Library Profile",        "zh": "📁 媒体库配置"},
    "sm_api_settings":          {"en": "⚙️ API Settings",           "zh": "⚙️ API 设置"},
    "sm_scene_detection":       {"en": "Scene Detection",           "zh": "场景检测"},
    "sm_gpt_analysis":          {"en": "GPT Analysis",              "zh": "GPT 分析"},
    "sm_save_api":              {"en": "💾 Save API Settings",       "zh": "💾 保存 API 设置"},
    "sm_saved":                 {"en": "Saved!",                    "zh": "已保存！"},
    "sm_no_profiles":           {"en": "No profiles yet. Create one below.", "zh": "暂无配置，请在下方创建。"},
    "sm_save_profile":          {"en": "💾 Save Profile",           "zh": "💾 保存配置"},
    "sm_delete_profile":        {"en": "🗑",                        "zh": "🗑"},
    "sm_delete_confirm":        {"en": "Delete **{name}**? This only removes the profile, not the files on disk.", "zh": "删除 **{name}**？仅删除配置，不删除磁盘文件。"},
    "sm_yes_delete":            {"en": "Yes, delete",               "zh": "确认删除"},
    "sm_cancel":                {"en": "Cancel",                    "zh": "取消"},
    "sm_new_profile":           {"en": "➕ New Profile",            "zh": "➕ 新建配置"},
    "sm_create_btn":            {"en": "Create",                    "zh": "创建"},
    "sm_profile_created":       {"en": "Profile '{name}' created!", "zh": "配置 '{name}' 已创建！"},
    "sm_path_must_start":       {"en": "Path must start with /",    "zh": "路径必须以 / 开头"},
    "sm_name_required":         {"en": "Name required.",            "zh": "名称不能为空。"},
    "sm_already_exists":        {"en": "'{name}' already exists.",  "zh": "'{name}' 已存在。"},
    "sm_profile_saved":         {"en": "Saved!",                    "zh": "已保存！"},
    "sm_sensitivity_high":      {"en": "⚠️ Very sensitive — may produce many small clips.", "zh": "⚠️ 非常灵敏 — 可能产生很多小片段。"},
    "sm_sensitivity_low":       {"en": "ℹ️ Low sensitivity — only large scene changes detected.", "zh": "ℹ️ 低灵敏度 — 只检测明显的场景变化。"},
    "sm_granularity_guide":     {"en": "**Granularity guide**",     "zh": "**细粒度说明**"},
    # ── Scene Manager main area ───────────────────────────────────
    "sm_main_title":            {"en": "🎬 Video Scene Manager",    "zh": "🎬 视频场景管理器"},
    "sm_no_profile_warning":    {"en": "No profile selected. Create one in the sidebar to get started.", "zh": "未选择配置，请在侧边栏创建一个配置。"},
    "sm_tab_process":           {"en": "Process Videos",            "zh": "处理视频"},
    "sm_tab_library":           {"en": "Browse Library",            "zh": "浏览媒体库"},
    "sm_tab_upload":            {"en": "📤 Upload Files",           "zh": "📤 上传文件"},
    "sm_tab_local":             {"en": "📂 Local File Paths",       "zh": "📂 本地文件路径"},
    "sm_tab_youtube":           {"en": "🌐 URL Download",           "zh": "🌐 链接下载"},
    "sm_start_processing":      {"en": "🚀 Start Processing",       "zh": "🚀 开始处理"},
    "sm_detect_scenes":         {"en": "🔍 Detect Scenes (Preview)","zh": "🔍 检测场景（预览）"},
    "sm_process_selected":      {"en": "🚀 Process Selected Scenes","zh": "🚀 处理所选场景"},
    "sm_session_summary":       {"en": "Session Summary",           "zh": "本次处理摘要"},
    "sm_upload_caption":        {"en": "Suitable for files under ~200 MB. For larger files use Local File Paths.", "zh": "适合 200MB 以下的文件，更大的文件请使用本地路径。"},
    "sm_local_caption":         {"en": "Enter absolute paths to video files. No size limit.", "zh": "输入视频文件的绝对路径，不限文件大小。"},
    "sm_clips_saved":           {"en": "✅ {n} clip(s) saved across {f} folder(s): {folders}", "zh": "✅ 已将 {n} 个片段保存至 {f} 个文件夹：{folders}"},
    "sm_no_clips_processed":    {"en": "No clips were successfully processed.", "zh": "没有成功处理的片段。"},
    "sm_clips_saved_short":     {"en": "✅ {n} clip(s) saved.",     "zh": "✅ 已保存 {n} 个片段。"},
    "sm_no_thumbnail":          {"en": "_(no thumbnail)_",          "zh": "_(无缩略图)_"},
    "sm_no_output_dir":         {"en": "No output directory set for this profile. Edit the profile in the sidebar.", "zh": "此配置未设置输出目录，请在侧边栏编辑。"},
    "sm_topic_label":           {"en": "Topic: *{topic}*  ·  Output: `{output}`", "zh": "主题：*{topic}*  ·  输出：`{output}`"},
    "sm_ytdlp_unavail":         {"en": "yt-dlp not available",      "zh": "yt-dlp 不可用"},
    "sm_ytdlp_caption":         {"en": "yt-dlp {ver} · Supports YouTube, Twitter/X, Instagram, TikTok, Bilibili, Vimeo, and 1000+ sites.", "zh": "yt-dlp {ver} · 支持 YouTube、Twitter/X、Instagram、TikTok、Bilibili、Vimeo 等 1000+ 网站。"},
}


def detect_lang() -> str:
    """Return 'zh' if system locale is Chinese, else 'en'."""
    try:
        lang_code = locale.getdefaultlocale()[0] or ""
        if lang_code.startswith("zh"):
            return "zh"
    except Exception:
        pass
    return "en"


def t(key: str, lang: str, **kwargs: str) -> str:
    """Look up translated string; falls back to English if key/lang missing."""
    row = STRINGS.get(key, {})
    text = row.get(lang) or row.get("en") or key
    if kwargs:
        text = text.format(**kwargs)
    return text
