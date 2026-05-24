"""StudioKit — unified entry point."""

import os
import streamlit as st
from i18n import t, detect_lang

# ── Language bootstrap (runs before any st.* call that renders) ───────────────
if "lang" not in st.session_state:
    st.session_state.lang = detect_lang()
_lang = st.session_state.lang

# ── CSS: language switcher pinned top-right + hide Streamlit chrome ───────────
st.markdown(
    """
    <style>
    #MainMenu, footer {visibility: hidden;}
    footer {display: none;}

    /* Language switcher container */
    div[data-testid="stMainBlockContainer"] > div:first-child {
        position: relative;
    }
    .sk-lang-switcher {
        position: fixed;
        top: 14px;
        right: 80px;
        z-index: 9999;
        display: flex;
        gap: 4px;
        background: rgba(255,255,255,0.0);
    }
    .sk-lang-btn {
        font-size: 12px;
        padding: 2px 8px;
        border-radius: 4px;
        border: 1px solid #ccc;
        background: transparent;
        cursor: pointer;
        color: inherit;
        line-height: 1.6;
    }
    .sk-lang-btn.active {
        background: #ff4b4b;
        border-color: #ff4b4b;
        color: white;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Language switcher widget (query_params-based toggle) ─────────────────────
_qp = st.query_params.get("lang", "")
if _qp in ("en", "zh") and _qp != _lang:
    st.session_state.lang = _qp
    _lang = _qp
    st.query_params.clear()
    st.rerun()

_en_active = "active" if _lang == "en" else ""
_zh_active = "active" if _lang == "zh" else ""
st.markdown(
    f"""
    <div class="sk-lang-switcher">
        <a href="?lang=en" style="text-decoration:none;">
            <button class="sk-lang-btn {_en_active}">EN</button>
        </a>
        <a href="?lang=zh" style="text-decoration:none;">
            <button class="sk-lang-btn {_zh_active}">中文</button>
        </a>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── License gate ──────────────────────────────────────────────────────────────
_DEV_MODE = os.environ.get("STUDIOKIT_DEV") == "1"

if not _DEV_MODE:
    import requests as _requests
    import license_guard as _lg
    import license_client as _lc

    _LICENSE_SERVER_URL = os.environ.get("LICENSE_SERVER_URL", "https://hype-cutter.vercel.app")

    # ── Revoke signal from background heartbeat ───────────────────────────────
    if st.session_state.pop("license_revoked", False):
        st.rerun()

    # ── Local signature verification ──────────────────────────────────────────
    _status, _payload = _lg.verify_local_license()

    # ── Startup online verification (once per process, not per rerun) ─────────
    if _status == "active" and not st.session_state.get("_license_online_verified"):
        _lic_data = _lc.load_license()
        _token = _lic_data.get("token", "") if _lic_data else ""
        if _token:
            try:
                _hb_resp = _requests.post(
                    f"{_LICENSE_SERVER_URL}/heartbeat",
                    json={"token": _token, "machine_id": _lc.get_machine_id()},
                    timeout=5,
                )
                if _hb_resp.status_code in (403, 404):
                    _lc._DEFAULT_LICENSE_PATH.unlink(missing_ok=True)
                    _status = "none"
                else:
                    # ── Server-time clock skew check ──────────────────────────
                    try:
                        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
                        _server_ts = _hb_resp.json().get("server_time")
                        if _server_ts:
                            _server_now = _dt.fromisoformat(_server_ts)
                            _local_now = _dt.now(_tz.utc)
                            _skew = abs((_server_now - _local_now).total_seconds())
                            if _skew > 300:  # > 5 minutes clock skew
                                # Re-check expiry using server time instead of local time
                                _exp = (_lic_data or {}).get("expires_at")
                                if _exp:
                                    try:
                                        if _server_now > _dt.fromisoformat(_exp):
                                            _lc._DEFAULT_LICENSE_PATH.unlink(missing_ok=True)
                                            _status = "expired"
                                    except Exception:
                                        pass
                    except Exception:
                        pass
                    if _status == "active":
                        _lc.update_last_online()
                        st.session_state["_license_online_verified"] = True
            except Exception:
                # Network error — check grace period before allowing offline use
                if _lc.is_grace_period_expired():
                    _status = "none"  # Grace period over, must go online to verify
                else:
                    st.session_state["_license_online_verified"] = True
        else:
            st.session_state["_license_online_verified"] = True

    if _status != "active":
        st.set_page_config(
            page_title=t("page_title_activate", _lang),
            page_icon="🔑",
        )
        st.title(t("activate_title", _lang))
        _STATUS_KEYS = {
            "none":     "license_none",
            "expired":  "license_expired",
            "mismatch": "license_mismatch",
            "tampered": "license_tampered",
            "invalid":  "license_invalid",
        }
        st.warning(t(_STATUS_KEYS.get(_status, "license_required"), _lang))
        _token_input = st.text_input(
            t("license_key_label", _lang),
            type="password",
            placeholder=t("license_key_placeholder", _lang),
        )
        if st.button(t("activate_btn", _lang), type="primary", use_container_width=True):
            if not _token_input.strip():
                st.error(t("activate_empty_err", _lang))
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
                        st.success(t("activate_success", _lang))
                        st.rerun()
                    else:
                        st.error(f"❌ {_resp.json().get('detail', t('activate_fail', _lang))}")
                except Exception as _e:
                    st.error(f"❌ {t('network_error', _lang)}: {_e}")
        st.stop()

    from heartbeat import start_heartbeat_scheduler as _start_hb
    _start_hb()
# ── End license gate ──────────────────────────────────────────────────────────

st.set_page_config(
    page_title=t("app_title", _lang),
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar: tool switcher + license status ───────────────────────────────────
with st.sidebar:
    st.title(f"🎬 {t('app_title', _lang)}")
    st.divider()
    _tool_labels = [t("tool_hypecutter", _lang), t("tool_scene_manager", _lang)]
    _tool_idx = st.radio(
        "Tool",
        range(len(_tool_labels)),
        format_func=lambda i: _tool_labels[i],
        label_visibility="collapsed",
        key="active_tool",
    )
    st.divider()
    if _DEV_MODE:
        st.caption(t("dev_mode_caption", _lang))
    else:
        import license_client as _lc2
        _lic = _lc2.load_license()
        if _lic:
            _plan = _lic.get("plan", "lifetime").capitalize()
            _exp = _lic.get("expires_at")
            if _exp:
                from datetime import datetime as _dt, timezone as _tz
                _days = (_dt.fromisoformat(_exp) - _dt.now(_tz.utc)).days
                _exp_label = t("licensed_expires", _lang, days=str(_days))
            else:
                _exp_label = t("licensed_lifetime", _lang)
            st.success(t("licensed_ok", _lang, exp_label=_exp_label))
            st.caption(t("plan_caption", _lang, plan=_plan))
        else:
            st.warning(t("no_license", _lang))

# ── Render selected tool ──────────────────────────────────────────────────────
if _tool_idx == 0:
    from hypecutter.ui import render as _render_hc
    _render_hc()
else:
    from scene_manager.ui import render as _render_sm
    _render_sm()
