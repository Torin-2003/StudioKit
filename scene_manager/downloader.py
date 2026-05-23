"""
yt-dlp wrapper — calls the locally installed yt-dlp binary.
No Python yt-dlp package required.
"""

import subprocess
import re
import shutil
import os
import json
import tempfile
from pathlib import Path

YTDLP_BIN = shutil.which("yt-dlp") or "/opt/homebrew/bin/yt-dlp"

# ── Availability ──────────────────────────────────────────────────────────────

def check_ytdlp() -> tuple[bool, str]:
    """Return (available, version_or_error)."""
    if not YTDLP_BIN or not Path(YTDLP_BIN).exists():
        return False, "yt-dlp not found. Install with: brew install yt-dlp"
    try:
        result = subprocess.run(
            [YTDLP_BIN, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        return True, result.stdout.strip()
    except Exception as e:
        return False, str(e)


# ── Video info (no download) ──────────────────────────────────────────────────

def get_video_info(url: str) -> dict:
    """
    Fetch title, duration, uploader without downloading.
    Returns dict or raises RuntimeError on failure.
    """
    cmd = [
        YTDLP_BIN,
        "--dump-json",
        "--no-playlist",
        "--quiet",
        url,
    ]
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

    cmd = [
        YTDLP_BIN,
        "--no-playlist",
        "--format", fmt,
        "--merge-output-format", "mp4",
        "--output", output_template,
        "--newline",          # one progress line per update, parseable
        "--progress",
        "--no-warnings",
        "--continue",         # resume partial downloads
        url,
    ]

    import threading

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    downloaded_file = None
    last_pct = 0.0
    all_lines = []
    stderr_lines = []

    def _drain_stderr():
        for l in process.stderr:
            stderr_lines.append(l.rstrip())

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    for line in process.stdout:
        line = line.rstrip()
        all_lines.append(line)

        # Parse progress lines: [download]  45.3% of  123.45MiB at  2.34MiB/s ETA 00:12
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

        # Detect final filename after merge
        # [Merger] Merging formats into "path/file.mp4"
        merge_m = re.search(r'Merging formats into "(.+?)"', line)
        if merge_m:
            downloaded_file = merge_m.group(1)

        # Fallback: [download] Destination: path/file.mp4
        dest_m = re.search(r'\[download\] Destination: (.+)', line)
        if dest_m:
            downloaded_file = dest_m.group(1).strip()

    stderr_thread.join()
    process.wait()

    if process.returncode != 0:
        error_detail = "\n".join(stderr_lines[-10:]) or "\n".join(all_lines[-5:])
        raise RuntimeError(f"yt-dlp exited with code {process.returncode}:\n{error_detail}")

    # If we never caught the filename, find the newest mp4 in output_dir
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
        return True, ""  # can't check, proceed anyway


# ── URL validation ────────────────────────────────────────────────────────────

def is_valid_url(url: str) -> bool:
    """Accept any http/https URL — yt-dlp handles site-specific validation."""
    return bool(re.match(r"https?://\S+", url.strip()))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _quality_to_format(quality: str) -> str:
    # Multi-level fallback: strict mp4 → any container at height → best available
    # Needed for platforms (Instagram, TikTok) that don't have separate mp4+m4a tracks
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
