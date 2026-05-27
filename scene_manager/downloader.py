"""
yt-dlp wrapper — uses the bundled Python yt_dlp package.
Works in PyInstaller frozen bundles without requiring a separate yt-dlp binary.
Falls back to the system yt-dlp binary if the Python module is unavailable.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

# Prefer the Python module (always present in our bundle); fall back to the CLI binary.
try:
    import yt_dlp as _yt_dlp_mod  # type: ignore
    _HAS_PY_MODULE = True
except Exception:
    _yt_dlp_mod = None
    _HAS_PY_MODULE = False

YTDLP_BIN = shutil.which("yt-dlp")


def _ffmpeg_dir() -> str | None:
    """Return the bundled ffmpeg directory if available (set by run_app.setup_ffmpeg)."""
    d = os.environ.get("STUDIOKIT_FFMPEG_DIR")
    return d if d and Path(d).exists() else None


# ── Availability ──────────────────────────────────────────────────────────────

def check_ytdlp() -> tuple[bool, str]:
    """Return (available, version_or_error)."""
    if _HAS_PY_MODULE:
        try:
            return True, _yt_dlp_mod.version.__version__  # type: ignore[attr-defined]
        except Exception:
            return True, "bundled"
    if YTDLP_BIN and Path(YTDLP_BIN).exists():
        try:
            result = subprocess.run(
                [YTDLP_BIN, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            return True, result.stdout.strip()
        except Exception as e:
            return False, str(e)
    return False, "yt-dlp not available"


# ── Video info (no download) ──────────────────────────────────────────────────

def get_video_info(url: str) -> dict:
    """
    Fetch title, duration, uploader without downloading.
    Returns dict or raises RuntimeError on failure.
    """
    if _HAS_PY_MODULE:
        ydl_opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
        try:
            with _yt_dlp_mod.YoutubeDL(ydl_opts) as ydl:  # type: ignore[attr-defined]
                data = ydl.extract_info(url, download=False)
        except Exception as e:
            raise RuntimeError(str(e))
        duration_sec = data.get("duration", 0) or 0
        return {
            "title": data.get("title", "Unknown"),
            "uploader": data.get("uploader", ""),
            "duration": _fmt_duration(duration_sec),
            "duration_sec": duration_sec,
            "thumbnail": data.get("thumbnail", ""),
            "url": url,
        }

    # CLI fallback
    if not YTDLP_BIN:
        raise RuntimeError("yt-dlp not available")
    import json
    cmd = [YTDLP_BIN, "--dump-json", "--no-playlist", "--quiet", url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            err = result.stderr.strip().splitlines()
            raise RuntimeError(err[-1] if err else "yt-dlp failed")
        data = json.loads(result.stdout)
        duration_sec = data.get("duration", 0) or 0
        return {
            "title": data.get("title", "Unknown"),
            "uploader": data.get("uploader", ""),
            "duration": _fmt_duration(duration_sec),
            "duration_sec": duration_sec,
            "thumbnail": data.get("thumbnail", ""),
            "url": url,
        }
    except json.JSONDecodeError:
        raise RuntimeError("Could not parse video info")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Timed out fetching video info")


# ── Download ──────────────────────────────────────────────────────────────────

def download_video(
    url: str,
    output_dir: str,
    quality: str = "1080",
    progress_callback=None,
) -> str:
    """
    Download a single video to output_dir.
    quality: "720", "1080", "best", "audio_only"
    progress_callback(percent: float, speed: str, eta: str)
    Returns the absolute path of the downloaded file.
    Raises RuntimeError on failure.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    fmt = _quality_to_format(quality)
    output_template = str(Path(output_dir) / "%(title).100B.%(ext)s")

    if _HAS_PY_MODULE:
        last_pct = [0.0]
        final_path = [None]  # type: ignore[var-annotated]

        def _hook(d: dict) -> None:
            status = d.get("status")
            if status == "downloading" and progress_callback:
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                if total > 0:
                    pct = (downloaded / total) * 100.0
                    if abs(pct - last_pct[0]) >= 0.5:
                        speed_bps = d.get("speed") or 0
                        speed = _fmt_speed(speed_bps) if speed_bps else ""
                        eta_s = d.get("eta") or 0
                        eta = _fmt_eta(eta_s) if eta_s else ""
                        try:
                            progress_callback(pct, speed, eta)
                        except Exception:
                            pass
                        last_pct[0] = pct
            elif status == "finished":
                fn = d.get("filename")
                if fn:
                    final_path[0] = fn

        ydl_opts = {
            "format": fmt,
            "outtmpl": output_template,
            "noplaylist": True,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "continuedl": True,
            "progress_hooks": [_hook],
        }
        ff = _ffmpeg_dir()
        if ff:
            ydl_opts["ffmpeg_location"] = ff

        try:
            with _yt_dlp_mod.YoutubeDL(ydl_opts) as ydl:  # type: ignore[attr-defined]
                info = ydl.extract_info(url, download=True)
        except Exception as e:
            raise RuntimeError(str(e))

        # Prefer the explicit final path from info (post-merge filepath)
        candidate = None
        if isinstance(info, dict):
            candidate = info.get("filepath") or info.get("_filename")
        if not candidate or not Path(candidate).exists():
            candidate = final_path[0]
        if not candidate or not Path(candidate).exists():
            # Last resort: find newest mp4 in output_dir
            mp4s = sorted(Path(output_dir).glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
            if not mp4s:
                raise RuntimeError("Download completed but output file not found")
            candidate = str(mp4s[0])
        # Replace .webm / .mkv merge fallback with the actual file on disk
        if not Path(candidate).exists():
            # Try replacing extension with .mp4
            stem = Path(candidate).with_suffix(".mp4")
            if stem.exists():
                candidate = str(stem)
        return str(Path(candidate).resolve())

    # CLI fallback
    if not YTDLP_BIN:
        raise RuntimeError("yt-dlp not available")
    cmd = [
        YTDLP_BIN,
        "--no-playlist",
        "--format", fmt,
        "--merge-output-format", "mp4",
        "--output", output_template,
        "--newline",
        "--progress",
        "--no-warnings",
        "--continue",
        url,
    ]
    ff = _ffmpeg_dir()
    if ff:
        cmd[1:1] = ["--ffmpeg-location", ff]

    import threading
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
    )

    downloaded_file = None
    last_pct = 0.0
    all_lines: list[str] = []
    stderr_lines: list[str] = []

    def _drain_stderr():
        for l in process.stderr:
            stderr_lines.append(l.rstrip())

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    for line in process.stdout:
        line = line.rstrip()
        all_lines.append(line)
        if line.startswith("[download]"):
            pct_m = re.search(r"([\d.]+)%", line)
            speed_m = re.search(r"at\s+([\d.]+\w+/s)", line)
            eta_m = re.search(r"ETA\s+([\d:]+)", line)
            if pct_m:
                pct = float(pct_m.group(1))
                speed = speed_m.group(1) if speed_m else ""
                eta = eta_m.group(1) if eta_m else ""
                if progress_callback and abs(pct - last_pct) >= 0.5:
                    progress_callback(pct, speed, eta)
                    last_pct = pct
        merge_m = re.search(r'Merging formats into "(.+?)"', line)
        if merge_m:
            downloaded_file = merge_m.group(1)
        dest_m = re.search(r'\[download\] Destination: (.+)', line)
        if dest_m:
            downloaded_file = dest_m.group(1).strip()

    stderr_thread.join()
    process.wait()

    if process.returncode != 0:
        error_detail = "\n".join(stderr_lines[-10:]) or "\n".join(all_lines[-5:])
        raise RuntimeError(f"yt-dlp exited with code {process.returncode}:\n{error_detail}")

    if not downloaded_file or not Path(downloaded_file).exists():
        mp4s = sorted(Path(output_dir).glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not mp4s:
            raise RuntimeError("Download completed but output file not found")
        downloaded_file = str(mp4s[0])

    return str(Path(downloaded_file).resolve())


# ── Disk space check ──────────────────────────────────────────────────────────

def check_disk_space(output_dir: str, required_bytes: int) -> tuple[bool, str]:
    """Check if output_dir has enough free space."""
    try:
        stat = shutil.disk_usage(output_dir)
        free_gb = stat.free / (1024 ** 3)
        req_gb = required_bytes / (1024 ** 3)
        if stat.free < required_bytes:
            return False, f"Need ~{req_gb:.1f} GB, only {free_gb:.1f} GB free"
        return True, f"{free_gb:.1f} GB free"
    except Exception:
        return True, ""


# ── URL validation ────────────────────────────────────────────────────────────

def is_valid_url(url: str) -> bool:
    """Accept any http/https URL — yt-dlp handles site-specific validation."""
    return bool(re.match(r"https?://\S+", url.strip()))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _quality_to_format(quality: str) -> str:
    return {
        "720":  (
            "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]"
            "/bestvideo[height<=720]+bestaudio"
            "/best[height<=720]"
            "/best"
        ),
        "1080": (
            "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
            "/bestvideo[height<=1080]+bestaudio"
            "/best[height<=1080]"
            "/best"
        ),
        "best": (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]"
            "/bestvideo+bestaudio"
            "/best"
        ),
    }.get(quality, "bestvideo+bestaudio/best")


def _fmt_duration(seconds) -> str:
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_speed(bps: float) -> str:
    if bps >= 1024 * 1024:
        return f"{bps / (1024 * 1024):.2f}MiB/s"
    if bps >= 1024:
        return f"{bps / 1024:.2f}KiB/s"
    return f"{bps:.0f}B/s"


def _fmt_eta(seconds: float) -> str:
    seconds = int(seconds)
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"
