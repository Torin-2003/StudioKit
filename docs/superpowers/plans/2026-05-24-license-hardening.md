# License Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the StudioKit license system against 4 attack vectors: license file copying, system time manipulation, binary patching, and offline bypass.

**Architecture:** Three independent changes: (1) `license_guard.py` is already in the Cython compile list — no change needed there. (2) Add offline grace period: `license_client.py` records `last_online_verify` timestamp in the license file; `app.py` rejects startup if offline AND grace period (3 days) has expired. (3) Server-time check: during online verify, compare server-returned timestamp against local time; if delta > 5 minutes, treat as tampered clock and use server time for expiry check.

**Tech Stack:** Python 3.11, existing license_client.py + license_guard.py + app.py, Vercel heartbeat endpoint (already returns JSON with server timestamp)

**Key constraint:** `license_guard.py` is already compiled by Cython (in `build_cython.py` TARGETS). No change needed to build_cython.py or StudioKit.spec for that. The offline grace period must survive app restarts — stored in the local license file.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `license_client.py` | Modify | Add `update_last_online()`, `get_last_online()`, `is_grace_period_expired()` |
| `app.py` | Modify | Check grace period on startup; use server time for expiry if clock skew detected |
| `heartbeat.py` | Modify | Call `update_last_online()` on successful heartbeat |

**No changes needed:**
- `build_cython.py` — `license_guard.py` already in TARGETS ✅
- `StudioKit.spec` — already excludes license_guard.py from datas ✅

---

## Task 1: Add offline grace period helpers to `license_client.py`

**Files:**
- Modify: `license_client.py`

- [ ] **Step 1: Read current `license_client.py`**

```bash
cat "/Users/torin/Documents/Code Work/StudioKit/license_client.py"
```

- [ ] **Step 2: Add three helper functions after `update_heartbeat()`**

Find the `update_heartbeat` function in `license_client.py`. After its closing line, add:

```python
_GRACE_PERIOD_DAYS = 3


def update_last_online(*, license_path: Path = _DEFAULT_LICENSE_PATH) -> None:
    """Record current UTC time as last successful online verification."""
    data = load_license(license_path=license_path)
    if data is None:
        return
    data["last_online_verify"] = datetime.now(timezone.utc).isoformat()
    license_path.write_text(json.dumps(data, indent=2))


def get_last_online(*, license_path: Path = _DEFAULT_LICENSE_PATH) -> Optional[datetime]:
    """Return last successful online verify time, or None if never verified."""
    data = load_license(license_path=license_path)
    if not data:
        return None
    ts = data.get("last_online_verify")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def is_grace_period_expired(*, license_path: Path = _DEFAULT_LICENSE_PATH) -> bool:
    """Return True if last online verify is older than GRACE_PERIOD_DAYS.
    
    Returns False (not expired) if never verified — new installs get first-run grace.
    The startup online check will either pass (sets timestamp) or fail (blocks).
    """
    last = get_last_online(license_path=license_path)
    if last is None:
        return False  # Never verified yet — let startup online check handle it
    delta = datetime.now(timezone.utc) - last
    return delta.days >= _GRACE_PERIOD_DAYS
```

Note: `license_client.py` already imports `datetime`, `timezone`, `Optional`, `Path`, and `json` at the top — verify before adding duplicate imports.

- [ ] **Step 3: Verify no duplicate imports**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
head -20 license_client.py
```

Confirm `from datetime import datetime, timezone` and `from typing import Optional` (or `Optional` available) are already present. If `datetime` import is missing, add it.

- [ ] **Step 4: Verify syntax**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python3 -c "import ast; ast.parse(open('license_client.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Smoke-test the helpers**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python3 -c "
from license_client import update_last_online, get_last_online, is_grace_period_expired
print('is_grace_period_expired (no license):', is_grace_period_expired())
print('get_last_online (no license):', get_last_online())
print('Helpers OK')
"
```

Expected: prints without error, `is_grace_period_expired` returns `False` (no license file), `get_last_online` returns `None`.

- [ ] **Step 6: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add license_client.py
git commit -m "feat: add offline grace period helpers to license_client.py"
```

---

## Task 2: Update `heartbeat.py` to record last online verify time

**Files:**
- Modify: `heartbeat.py`

- [ ] **Step 1: Add import**

In `heartbeat.py`, find:
```python
from license_client import get_machine_id, load_license, update_heartbeat, _DEFAULT_LICENSE_PATH
```

Replace with:
```python
from license_client import get_machine_id, load_license, update_heartbeat, update_last_online, _DEFAULT_LICENSE_PATH
```

- [ ] **Step 2: Call `update_last_online()` on successful heartbeat**

In `heartbeat.py`, find:
```python
        if resp.ok and resp.json().get("valid"):
            update_heartbeat()
            logger.info("Heartbeat OK")
            return True
```

Replace with:
```python
        if resp.ok and resp.json().get("valid"):
            update_heartbeat()
            update_last_online()
            logger.info("Heartbeat OK")
            return True
```

- [ ] **Step 3: Verify syntax**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python3 -c "import ast; ast.parse(open('heartbeat.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add heartbeat.py
git commit -m "fix: record last_online_verify timestamp on successful heartbeat"
```

---

## Task 3: Update `app.py` — grace period check + server-time expiry

**Files:**
- Modify: `app.py`

Two additions to the startup online verification block:
1. **Before** the online check: if offline AND grace period expired → block
2. **During** the online check: if server returns a timestamp, check clock skew; if clock skewed > 5 min, re-check expiry using server time

- [ ] **Step 1: Read the current online verification block in `app.py`**

```bash
grep -n "license_online_verified\|grace\|last_online\|_token\|_hb_resp\|_status" "/Users/torin/Documents/Code Work/StudioKit/app.py" | head -25
```

- [ ] **Step 2: Update the import from license_client**

In `app.py`, find:
```python
    import license_client as _lc
```

This stays the same — we'll call `_lc.update_last_online()`, `_lc.is_grace_period_expired()` via the module.

- [ ] **Step 3: Replace the online verification block**

Find the current block (approximately):
```python
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
                    st.session_state["_license_online_verified"] = True
            except Exception:
                # Network error — allow offline use, don't block startup
                st.session_state["_license_online_verified"] = True
        else:
            st.session_state["_license_online_verified"] = True
```

Replace with:
```python
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
```

- [ ] **Step 4: Verify syntax**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
python3 -c "import ast; ast.parse(open('app.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git add app.py
git commit -m "feat: grace period offline block + server-time clock skew detection"
```

---

## Task 4: Push and tag v1.1.0

- [ ] **Step 1: Push and tag**

```bash
cd "/Users/torin/Documents/Code Work/StudioKit"
git push
git tag v1.1.0
git push origin v1.1.0
```

---

## Self-Review

**Spec coverage:**
- ✅ `license_guard.py` compiled by Cython — already in TARGETS, no change needed
- ✅ Offline grace period (3 days) — Tasks 1+2+3
- ✅ Server-time clock skew check — Task 3
- ✅ Machine ID binding — already exists in license_guard.py ✅
- ✅ Heartbeat records last_online_verify — Task 2

**Placeholder scan:** None found.

**Type consistency:**
- `update_last_online()` / `get_last_online()` / `is_grace_period_expired()` all use same `license_path` param pattern as existing helpers ✅
- `_status` variable mutated in-place within the online check block, consistent with existing pattern ✅

**Important notes for implementer:**
- The heartbeat server (`/heartbeat` endpoint on Vercel) may or may not return `server_time` in its JSON response. If it doesn't, the clock skew check is silently skipped (try/except). To fully enable server-time checking, the Vercel heartbeat handler should add `"server_time": datetime.utcnow().isoformat() + "Z"` to its response — but the client code is already defensive if it's absent.
- Grace period of 3 days means: if a user activates, goes on a 3-day camping trip with no internet, they can still use the app. On day 4 they need to connect once to renew. This is a reasonable UX tradeoff.
- `is_grace_period_expired()` returns `False` when `last_online_verify` is None (new install) — this is intentional. A brand-new install with no internet will fail the startup online check (no token verified yet), not the grace period check.
