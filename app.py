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

st.markdown(
    "<style>#MainMenu, footer, header {visibility: hidden;}</style>",
    unsafe_allow_html=True,
)

# ── Sidebar: tool switcher + license status ───────────────────────────────────
with st.sidebar:
    st.title("🎬 StudioKit")
    st.divider()
    _tool = st.radio(
        "Tool",
        ["✂️ HypeCutter", "🎬 Scene Manager"],
        label_visibility="collapsed",
        key="active_tool",
    )
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

# ── Render selected tool ──────────────────────────────────────────────────────
if _tool == "✂️ HypeCutter":
    from hypecutter.ui import render as _render_hc
    _render_hc()
else:
    from scene_manager.ui import render as _render_sm
    _render_sm()
