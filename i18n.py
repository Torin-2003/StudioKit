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
