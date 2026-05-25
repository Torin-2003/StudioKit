"""
AutoHighlight Pro Max — core_engine.py
Classes: Downloader, Transcriber, SilenceRemover, AIAnalyzer, VideoEditor, AutoHighlightEngine
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

import yt_dlp
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


def _get_ffmpeg_dir() -> str | None:
    """Return bundled ffmpeg_bin path.

    Streamlit re-launches itself as an unfrozen child process, so we can't rely on
    sys.frozen here. Instead, run_app.py exports STUDIOKIT_FFMPEG_DIR before launching
    Streamlit, and we read that env var.
    """
    env_dir = os.environ.get("STUDIOKIT_FFMPEG_DIR")
    if env_dir and Path(env_dir).exists():
        # Ensure subprocess calls (ffmpeg, ffprobe by bare name) also find it
        if env_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = env_dir + os.pathsep + os.environ.get("PATH", "")
        return env_dir
    # Fallback to sys.frozen detection (for one-file bundles where frozen IS True)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates = [
            Path(sys._MEIPASS) / "ffmpeg_bin",
            exe_dir / "ffmpeg_bin",
            exe_dir / "_internal" / "ffmpeg_bin",
            exe_dir.parent / "Resources" / "ffmpeg_bin",
            exe_dir.parent / "Frameworks" / "ffmpeg_bin",
        ]
        for ffmpeg_dir in candidates:
            if ffmpeg_dir.exists():
                os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")
                return str(ffmpeg_dir)
    return None


# Run once at import time so PATH is set before any subprocess is spawned
_get_ffmpeg_dir()


class WordToken(TypedDict):
    word: str
    start: float
    end: float


# ─────────────────────────────────────────────────────────────────
# Downloader
# ─────────────────────────────────────────────────────────────────


class Downloader:
    def __init__(self, output_dir: str = "downloads") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _cached_path(self, url: str) -> Path | None:
        """Return existing cached file for this URL if present, else None."""
        # Extract video ID via yt-dlp without downloading
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                info = ydl.extract_info(url, download=False)
                video_id = info.get("id", "")
            if not video_id:
                return None
            candidate = self.output_dir / f"{video_id}.mp4"
            return candidate if candidate.exists() else None
        except Exception:
            return None

    def download(
        self,
        url: str,
        progress_callback: Callable[[str], None] | None = None,
        max_height: int = 720,
    ) -> str:
        """Return local mp4 path. Uses cache if the file was downloaded before."""
        cached = self._cached_path(url)
        if cached is not None:
            logger.info(f"Cache hit — reusing {cached}")
            if progress_callback:
                progress_callback(f"✅ Using cached file: {cached.name}")
            return str(cached)

        ydl_opts: dict = {
            "format": (
                f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]"
                f"/best[height<={max_height}][ext=mp4]/best"
            ),
            "outtmpl": str(self.output_dir / "%(id)s.%(ext)s"),
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "retries": 5,
            "fragment_retries": 5,
            "nocheckcertificate": True,
        }
        _ffmpeg_dir = _get_ffmpeg_dir()
        if _ffmpeg_dir:
            ydl_opts["ffmpeg_location"] = _ffmpeg_dir
        if progress_callback:

            def hook(d: dict) -> None:
                if d["status"] == "downloading":
                    pct = d.get("_percent_str", "?%").strip()
                    progress_callback(f"⬇️ Downloading: {pct}")

            ydl_opts["progress_hooks"] = [hook]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            mp4_path = Path(filename).with_suffix(".mp4")
            if mp4_path.exists():
                filename = str(mp4_path)
            elif not Path(filename).exists():
                raise FileNotFoundError(f"Downloaded file not found: {filename}")
        return filename


# ─────────────────────────────────────────────────────────────────
# Transcriber
# ─────────────────────────────────────────────────────────────────


class Transcriber:
    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "default",
    ) -> None:
        logger.info(f"Loading Whisper model '{model_size}' ...")
        if device == "auto":
            device = "cuda" if self._cuda_available() else "cpu"
        if compute_type == "default":
            compute_type = "float16" if device == "cuda" else "int8"
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        logger.info(f"Whisper ready on {device} ({compute_type})")

    @staticmethod
    def _cuda_available() -> bool:
        try:
            import torch

            return torch.cuda.is_available()
        except ImportError:
            return False

    def transcribe(
        self, video_path: str, language: str | None = None
    ) -> list[WordToken]:
        """Run word-level transcription. Returns list of WordToken dicts."""
        logger.info(f"Transcribing: {video_path}")
        segments_gen, info = self.model.transcribe(
            video_path,
            language=language or None,
            word_timestamps=True,
            beam_size=5,
            # vad_filter disabled: ONNX Runtime silero VAD causes segfault on Windows
            # frozen bundles when combined with word_timestamps=True. Transcription
            # quality is unaffected; silence handling is done by SilenceRemover instead.
            vad_filter=False,
        )

        words: list[WordToken] = []
        for seg in segments_gen:
            if not seg.words:
                continue
            for w in seg.words:
                words.append(
                    {
                        "word": w.word,
                        "start": round(float(w.start), 3),
                        "end": round(float(w.end), 3),
                    }
                )

        logger.info(
            f"Transcription done: {len(words)} words, duration ~{info.duration:.0f}s"
        )
        return words


# ─────────────────────────────────────────────────────────────────
# Silence Remover
# ─────────────────────────────────────────────────────────────────


class SilenceRemover:
    """Detects and removes silence gaps > min_silence_duration seconds using FFmpeg."""

    DEFAULT_MIN_SILENCE: float = 1.0
    DEFAULT_NOISE_THRESHOLD: float = -35.0

    def __init__(
        self,
        min_silence_duration: float = DEFAULT_MIN_SILENCE,
        noise_threshold: float = DEFAULT_NOISE_THRESHOLD,
    ) -> None:
        self.min_silence_duration = min_silence_duration
        self.noise_threshold = noise_threshold

    def remove_silence(
        self,
        input_path: str,
        output_path: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> str:
        """Strip silence gaps from video. Returns path to processed file."""
        if progress_callback:
            progress_callback("🔇 Detecting silence gaps…")

        silent_ranges = self._detect_silence(input_path)
        if not silent_ranges:
            logger.info("No significant silence detected, skipping removal.")
            return input_path

        duration = self._get_duration(input_path)
        keep_ranges = self._invert_ranges(silent_ranges, duration)

        if not keep_ranges:
            logger.warning("Silence removal would eliminate entire video, skipping.")
            return input_path

        if progress_callback:
            progress_callback(f"✂️ Removing {len(silent_ranges)} silence gap(s)…")

        self._concat_segments(input_path, keep_ranges, output_path)
        logger.info(f"Silence removed: {len(silent_ranges)} gaps cut → {output_path}")
        return output_path

    def _detect_silence(self, path: str) -> list[tuple[float, float]]:
        cmd = [
            "ffmpeg",
            "-i",
            path,
            "-af",
            f"silencedetect=noise={self.noise_threshold}dB:d={self.min_silence_duration}",
            "-f",
            "null",
            "-",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        output = result.stderr

        starts = [float(m) for m in re.findall(r"silence_start: ([0-9.]+)", output)]
        ends = [float(m) for m in re.findall(r"silence_end: ([0-9.]+)", output)]

        return [
            (s, e) for s, e in zip(starts, ends) if e - s >= self.min_silence_duration
        ]

    @staticmethod
    def _get_duration(path: str) -> float:
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])

    @staticmethod
    def _invert_ranges(
        silent: list[tuple[float, float]],
        total: float,
    ) -> list[tuple[float, float]]:
        keep: list[tuple[float, float]] = []
        cursor = 0.0
        for s, e in sorted(silent):
            if cursor < s:
                keep.append((cursor, s))
            cursor = e
        if cursor < total:
            keep.append((cursor, total))
        return keep

    def _concat_segments(
        self,
        src: str,
        segments: list[tuple[float, float]],
        dst: str,
    ) -> None:
        n = len(segments)
        filter_parts: list[str] = []
        for i, (s, e) in enumerate(segments):
            filter_parts.append(
                f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}];"
                f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]"
            )

        interleaved = "".join(f"[v{i}][a{i}]" for i in range(n))
        filter_parts.append(f"{interleaved}concat=n={n}:v=1:a=1[outv][outa]")

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            src,
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            dst,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            tail = "\n".join(result.stderr.splitlines()[-40:])
            raise RuntimeError(f"Silence removal FFmpeg failed:\n{tail}")


# ─────────────────────────────────────────────────────────────────
# AI Analyzer
# ─────────────────────────────────────────────────────────────────


class AIAnalyzer:
    DEFAULT_LLM_OPENAI: str = "gpt-4o"
    DEFAULT_LLM_ANTHROPIC: str = "claude-3-5-sonnet-20241022"
    DEFAULT_LLM_GEMINI: str = "gemini-2.0-flash"

    # Boundary buffers applied before word-gap snapping
    START_BUF: float = 0.2  # seconds pulled back from raw start
    END_BUF: float = 0.3  # seconds pushed forward from raw end
    WORD_GAP_PAD: float = 0.01  # 10ms pad inside inter-word gap

    # Minimum sub-segment duration kept in condense mode
    MIN_SEG_DUR: float = 3.0

    def __init__(
        self,
        provider: str = "openai",
        api_key: str = "",
        model: str = "",
        base_url: str = "",
        workflow_config: dict | None = None,
    ) -> None:
        self.provider = provider.lower()
        self.api_key = api_key
        self.base_url = base_url.strip() or None
        self._workflow_config: dict = workflow_config or {}
        if model.strip():
            self.model = model.strip()
        elif self.provider == "anthropic":
            self.model = self.DEFAULT_LLM_ANTHROPIC
        elif self.provider == "gemini":
            self.model = self.DEFAULT_LLM_GEMINI
        else:
            self.model = self.DEFAULT_LLM_OPENAI

    # ── prompt ──────────────────────────────────────────────────────

    @staticmethod
    def _words_to_text(words: list[WordToken]) -> str:
        return " ".join(w["word"] for w in words).strip()

    @staticmethod
    def _words_to_timed_transcript(words: list[WordToken]) -> str:
        """
        Group words into sentences and format each line as:
            [start_s - end_s] sentence text
        This gives the LLM accurate timestamps per sentence so it can return
        precise start/end values instead of guessing from plain text.
        Sentence boundaries are detected by terminal punctuation (. ! ?) and
        natural pauses (gap > 1.5s between consecutive words).
        """
        if not words:
            return ""

        lines: list[str] = []
        current: list[WordToken] = []

        for i, w in enumerate(words):
            current.append(w)
            text = w["word"].rstrip()
            is_sentence_end = text.endswith((".", "!", "?", "...", "…"))
            # Also break on long pause between this word and the next
            long_pause = (
                i + 1 < len(words)
                and words[i + 1]["start"] - w["end"] > 1.5
            )
            if is_sentence_end or long_pause or i == len(words) - 1:
                sentence = " ".join(ww["word"] for ww in current).strip()
                t0 = current[0]["start"]
                t1 = current[-1]["end"]
                lines.append(f"[{t0:.3f}-{t1:.3f}] {sentence}")
                current = []

        return "\n".join(lines)

    # ── promo / filler keyword blacklist (Python-level filter) ──────
    # All phrases are matched as whole-word substrings (word-boundary aware).
    # Keep phrases specific enough that they CANNOT appear in normal sermon content.
    _PROMO_PHRASES: frozenset[str] = frozenset(
        [
            # Social platforms — only match when used as destination/reference
            "my instagram",
            "my twitter",
            "my tiktok",
            "my youtube",
            "my facebook",
            "on instagram",
            "on twitter",
            "on tiktok",
            "instagram story",
            "instagram page",
            # Explicit subscribe/follow calls
            "subscribe",
            "follow me",
            "hit the bell",
            "like and share",
            "comment below",
            "leave a comment",
            "let me know in the comments",
            # Merch / commerce
            "merch",
            "merchandise",
            "t-shirt",
            "tshirt",
            "hoodie",
            "promo code",
            "discount code",
            "coupon code",
            "buy now",
            "pre-order",
            "early access",
            "link in bio",
            "link in the description",
            # Monetisation platforms
            "patreon",
            "buy me a coffee",
            # Explicit ad/sponsor language
            "this video is sponsored",
            "sponsored by",
            "advertisement",
            "this episode is brought",
            "brought to you by",
            # Podcast/episode logistics
            "podcast episode uploads",
            "next week's episode",
            "last week's episode",
            "last week's podcast",
            "next week's podcast",
            "be on the lookout for that",
            "monday after next",
            # Outro sign-offs
            "love you guys",
            "god bless you guys",
            "thanks for watching",
            "thanks for listening",
            "that's all for today",
            "see you next week",
            "see you next time",
            "if you liked this video",
            # Self-referential posting
            "i'm going to post a link",
            "i'm going to share",
            "i will post",
            "posting tomorrow",
        ]
    )

    def _build_system_prompt(self) -> str:
        base_prompt = (
            "You are a world-class short-form video editor and content quality auditor "
            "specializing in TikTok/Reels for faith, motivational, and educational content. "
            "Your PRIMARY responsibility is CONTENT PURITY: you must identify and REJECT "
            "any segment that contains promotional, self-referential, or meta content — "
            "regardless of how emotionally warm it sounds. "
            "REJECTED content types (score = 0, do NOT include in output): "
            "(a) Self-promotion: merch announcements, social media plugs, subscriber asks, "
            "    links, discount codes, Patreon, early access offers; "
            "(b) Outro/Goodbye: 'love you guys', 'God bless you guys', 'see you next week', "
            "    'thanks for watching/listening', 'that's all for today'; "
            "(c) Logistics: scheduling, episode references ('next week's podcast'), "
            "    platform mentions ('on my Instagram story'); "
            "(d) Generic sign-off: any segment whose primary purpose is ending the video "
            "    rather than delivering theological or motivational value. "
            "You master the Hook-Body-Punchline structure: "
            "(1) Hook — first 3s create immediate curiosity or emotional resonance; "
            "(2) Body — remove filler but keep theological/philosophical depth; "
            "(3) Punchline — final 2s must be a powerful, memorable resolution line. "
            "You understand the Conflict-to-Clarity arc: start with struggle, end with "
            "spiritual revelation or Gold Nugget. "
            "You NEVER cut mid-thought. Every clip is a Closed Loop — "
            "if printed on a T-shirt it must make complete sense standalone. "
            "You always respond with valid JSON only — no markdown fences, no prose."
        )
        extra = self._workflow_config.get("system_prompt_extra", "")
        if extra:
            base_prompt = base_prompt + "\n\n" + extra
        return base_prompt

    def _build_user_prompt(
        self,
        transcript: str,
        target_duration: int,
        n_clips: int,
        smart_mode: bool = False,
        tolerance: int = 5,
        video_duration: float = 0,
        max_clips: int = 0,
        condense_mode: bool = False,
        range_mode: bool = False,
        range_label: str = "",
        range_lo: int = 30,
        range_hi: int = 60,
    ) -> str:
        if smart_mode:
            min_clips = max(3, (max_clips * 2) // 3)  # ask for at least 2/3 of max
            clip_instruction = (
                f"The video is {video_duration:.0f} seconds long. "
                f"You MUST identify AT LEAST {min_clips} highlight segments, up to {max_clips}. "
                f"THIS IS A HARD MINIMUM — returning fewer than {min_clips} clips is an error. "
                f"Scan the ENTIRE video from start to finish. "
                f"Do NOT cluster clips at the start — spread them across the full timeline. "
                f"Every section of the video deserves equal consideration. "
                f"Only skip a segment if it fails the PF1 content purity filter."
            )
        else:
            clip_instruction = f"Identify exactly {n_clips} highlight segments."

        if range_mode:
            duration_rule = (
                f"1. DURATION STRATEGY — Range-Based (AI Optimized):\n"
                f"   Selected range: {range_label} ({range_lo}s – {range_hi}s).\n"
                f"   Your PRIMARY goal is SEMANTIC INTEGRITY, not filling the range.\n"
                f"   • Find the NATURAL end of the thought within {range_lo}s – {range_hi}s.\n"
                f"   • Quality over length: if 45s is perfect and self-contained, use 45s — do NOT pad to fill.\n"
                f"   • You are authorized to choose ANY duration within [{range_lo}s, {range_hi}s].\n"
                f"   • The clip MUST strictly start ≥ {range_lo}s and end ≤ {range_hi}s total duration.\n"
                f"   • Return 'selected_range': '{range_label}' and 'reason_for_duration' explaining\n"
                f"     exactly why you chose that specific length."
            )
        else:
            duration_rule = (
                f"1. DURATION STRATEGY — Fixed Target:\n"
                f"   Target: {target_duration}s (±{tolerance}s tolerance = "
                f"[{target_duration - tolerance}s, {target_duration + tolerance}s]).\n"
                f"   CRITICAL: {target_duration - tolerance}s is the FLOOR, NOT the goal.\n"
                f"   Do NOT anchor to the minimum. The ideal clip ends at a powerful, "
                f"memorable sentence — even if that means {target_duration + tolerance}s.\n"
                f"   If the Gold Nugget lands at {target_duration + tolerance - 2}s, use that. "
                f"If a thought is still unfolding at {target_duration - tolerance}s, keep going.\n"
                f"   Seek the PEAK IMPACT point within the window, not the shortest exit."
            )

        if condense_mode and range_mode:
            condense_range_note = (
                f"\nCONDENSE + RANGE MODE:\n"
                f"First identify Gold Nuggets. Stitch them together until reaching a Logical\n"
                f"Satisfaction Point within {range_lo}s – {range_hi}s. Stop when semantically\n"
                f"complete — do NOT pad to reach the upper bound.\n"
                f"The SUM of all sub-segment durations MUST be between {range_lo}s and {range_hi}s."
            )
        elif condense_mode:
            condense_range_note = (
                f"\nThe SUM of all sub-segment durations MUST be between "
                f"{target_duration - tolerance}s and {target_duration + tolerance}s."
            )
        else:
            condense_range_note = ""

        selected_range_value = range_label if range_mode else ""
        if condense_mode:
            seg_duration_rule = (
                f"{range_lo}s and {range_hi}s"
                if range_mode
                else f"{target_duration - tolerance}s and {target_duration + tolerance}s"
            )
            mode_rules = f"""
CONDENSE MODE — INTELLIGENT JUMP-CUT EDITING:
You are now a high-precision video editor. Your goal is MAXIMUM INFORMATION DENSITY.
Instead of one continuous segment, each highlight is built from 2-4 non-contiguous sub-segments
that are later concatenated by the editor with a 100ms crossfade.

HOW TO FIND A CONDENSE HIGHLIGHT (follow this process strictly):
STEP 1 — Find a continuous region of the video where ONE core idea is developed.
         This region is typically {range_lo if range_mode else target_duration - tolerance}s–{int((range_hi if range_mode else target_duration + tolerance) * 1.5)}s long in the original transcript.
STEP 2 — Inside that region, identify the FILLER to remove: repetitions, "um/uh/you know",
         re-statements of a point already made, tangential asides.
STEP 3 — What remains after removing filler = your sub-segments.
         The sub-segments span only this one region — they are NOT picked from different
         parts of the video.

CONDENSE RULES:
C1. Identify the SINGLE core idea or theological insight of this highlight first.
    ALL sub-segments must serve and advance that ONE idea — do NOT mix unrelated topics.
C2. SEMANTIC CONTINUITY — This is the most important rule:
    Each sub-segment must flow naturally into the next after the jump-cut.
    Ask yourself: "If a viewer hears Segment A end and Segment B start, does it feel
    like a natural continuation of the same thought?"
    FORBIDDEN: Jumping from Topic A mid-sentence → Topic B mid-sentence.
    FORBIDDEN: Sub-segments that introduce a brand new idea (those become separate clips).
    ALLOWED: Skipping repetition, filler ("um", "like", "you know"), re-statements of
    a point already made, and tangential asides — as long as the core thread continues.
C3. TRANSITION TEST — Before finalizing, read the last sentence of segment N and the
    first sentence of segment N+1 aloud together. If it sounds jarring or disconnected
    → either find a better cut point OR split into two separate highlights.
C4. Each sub-segment MUST start and end on a complete sentence boundary.
C5. Sub-segments MUST be in chronological order and MUST NOT overlap.
C6. The SUM of all sub-segment durations MUST be between {seg_duration_rule}.
    Each INDIVIDUAL sub-segment must be ≤ {(range_hi if range_mode else target_duration + tolerance) // 2 + 5}s.
    If a sub-segment is longer than that, it is not a condensed part — it is a full clip on its own.
C7. Each individual sub-segment must be at least 3 seconds long.
C8. The FIRST sub-segment must open with a strong hook (provocative/high-energy/curiosity).
C9. The LAST sub-segment must end with a powerful punchline or Gold Nugget — not mid-thought.
C10. MANDATORY: Every highlight MUST have at least 2 sub-segments. A single continuous
     block is NOT condense mode — if you cannot find a second meaningful sub-segment
     to skip filler between, choose a different highlight that does have skippable filler.
     Returning "segments": [one_item] is an error.
C11. SPAN LIMIT — The total timespan from the FIRST segment's start to the LAST segment's
     end in the original video must be ≤ {int((range_hi if range_mode else target_duration + tolerance) * 1.8)}s.
     Example: if seg1 starts at 120s and seg3 ends at 210s, the span is 90s.
     If your sub-segments span more than {int((range_hi if range_mode else target_duration + tolerance) * 1.8)}s apart in the original video,
     they are from different topics — split them into separate highlights instead.
{condense_range_note}
Return format uses "segments" array instead of start/end:
{{
  "highlights": [
    {{
      "title": "Viral Hook Title",
      "segments": [
        {{"start": 120.0, "end": 138.5}},
        {{"start": 145.2, "end": 158.0}},
        {{"start": 163.0, "end": 178.4}}
      ],
      "total_duration": 46.7,
      "hook_strength": 9.5,
      "score": 9.2,
      "selected_range": "{selected_range_value}",
      "reason_for_duration": "Why this specific length was chosen.",
      "reason": "One region 120-178s; removed 6s repetition + 5s tangent for density.",
      "caption": "Caption text #motivation #mindset"
    }}
  ]
}}"""
        else:
            mode_rules = f"""
Return ONLY a JSON object — no explanation, no markdown:
{{
  "highlights": [
    {{
      "title": "Viral Hook Title",
      "start": 0.0,
      "end": 48.5,
      "duration": 48.5,
      "hook_strength": 9.5,
      "score": 9.2,
      "selected_range": "{selected_range_value}",
      "reason_for_duration": "Why this specific length was chosen.",
      "reason": "Opens with a high-impact question about wealth; complete insight arc.",
      "caption": "Caption text #motivation #mindset"
    }}
  ]
}}"""

        return f"""Analyze the transcript below and apply TikTok viral engineering principles.

TRANSCRIPT FORMAT: Each line is "[start_seconds - end_seconds] sentence text".
These timestamps are word-level accurate (from Whisper). Use them DIRECTLY as your
start/end values — do NOT guess or round to whole numbers.

{clip_instruction}

STRICT RULES:
{duration_rule}
2. Clips MUST NOT overlap each other. Distribute across the full video timeline.
3. Your start/end values MUST come from the timestamps in the transcript lines above.
   NEVER invent timestamps. NEVER round to whole seconds. Copy the exact decimal values.

### CONTENT PURITY FILTER (run this FIRST before scoring anything)
PF1. HARD REJECT — Immediately discard any segment that contains ANY of the following.
     These are NEVER viral-worthy regardless of emotional tone:
     • Merch / product announcements: "merch", "t-shirt", "hoodie", "shop", "link",
       "promo code", "discount", "early access", "pre-order", "Patreon"
     • Social media self-promotion: "Instagram", "Twitter", "TikTok", "YouTube",
       "subscribe", "follow me", "hit the bell", "like and share", "comment below",
       "DM me", "check out my", "my Instagram story", "I'm going to post"
     • Outro / sign-off language: "love you guys", "God bless you guys",
       "see you next week", "thanks for watching", "thanks for listening",
       "that's all for today", "if you liked this video"
     • Logistics / scheduling: "next week's episode", "last week's episode",
       "Monday after", "podcast episode uploads", "be on the lookout for that"
     If ANY of the above appears anywhere in the segment → DISCARD ENTIRELY.
     Do NOT assign a score. Do NOT include in output.
PF2. SELF-CHECK — After selecting candidates, ask yourself:
     "Is this segment's primary value theological/motivational insight?"
     If the answer is NO (it's an announcement, a plug, an outro) → remove it.
PF3. PURE CONTENT ONLY — Every included segment must deliver standalone spiritual
     or emotional value. A viewer who has never heard of the speaker must find it
     immediately compelling WITHOUT needing any context about the channel/show.

### SEMANTIC CLOSURE (apply to every clip, always)
SC1. LOGICAL CLOSURE — Every clip is a Closed Loop / standalone story.
     NEVER end on a preposition, conjunction, or introductory phrase:
     "and", "but", "so", "because", "if", "when", "he said", "they say",
     "In the book of…", "And then he said…", or any setup clause.
     TWO options when you detect such an ending:
       (a) Move `end` FORWARD to the next terminal punctuation (. ? !) that
           completes the thought, even if it extends the clip duration.
       (b) Move `end` BACKWARD to just before that setup phrase began,
           if option (a) would violate the duration window.
     Choose whichever keeps the clip within range AND semantically complete.
SC2. DO NOT stop at the minimum duration just because you reached it.
     If the core message or Gold Nugget is still unfolding at {range_lo if range_mode else target_duration - tolerance}s,
     EXTEND the clip to the next natural pause that completes the thought.
     Semantic completeness (weight 9.0) > proximity to duration target (weight 1.0).
SC3. SELF-CORRECTION — Before outputting JSON, verify the last sentence of each clip:
     "If this were printed on a T-shirt, is it a complete, self-contained thought?"
     If NO → move `end` forward until the answer is YES.

### VIRAL STRUCTURE (Hook-Body-Punchline)
VS1. HOOK (first 3s): Must be a Question, a Bold Statement, or a Pain Point.
     Creates immediate curiosity or emotional resonance.
VS2. BODY: Remove filler words ("um", "uh", "you know", "like", "so basically").
     Keep theological, philosophical, and emotional depth.
VS3. PUNCHLINE (last 5s): Must be a conclusion, Gold Nugget, or Call to Action.
     It must feel like a resolution — the payoff the viewer was waiting for.
     The final line must be Powerful and Memorable.

### FAITH & MOTIVATION FOCUS
FM1. Prioritize the Conflict-to-Clarity arc: start with the struggle, end with
     the spiritual revelation or insight. Avoid purely scene-setting segments.
FM2. For "Standard (30–60s)" or any range: do not default to ~30s.
     Seek the "Peak Impact" point. If 32s is mid-sentence but 48s is a
     mic-drop moment, choose 48s.

4. hook_strength 1–10: how irresistible are the opening 3 seconds?
5. score 1–10: overall virality (emotional impact × theological depth × standalone value).
   IMPORTANT: score = 0 for ANY segment containing promotional or outro content.
6. Title: punchy, click-bait, max 12 words.
7. Caption: max 150 chars with hashtags.
{mode_rules}

TRANSCRIPT:
{transcript}"""

    # ── promo filter ────────────────────────────────────────────────

    def _extract_segment_text(self, highlight: dict, words: list[WordToken]) -> str:
        """Return the transcript text covered by this highlight."""
        if "segments" in highlight:
            parts = []
            for seg in highlight["segments"]:
                parts += [
                    w["word"]
                    for w in words
                    if w["start"] >= seg.get("start", 0)
                    and w["end"] <= seg.get("end", 999999)
                ]
            return " ".join(parts).lower()
        start = float(highlight.get("start", 0))
        end = float(highlight.get("end", 999999))
        return " ".join(
            w["word"] for w in words if w["start"] >= start and w["end"] <= end
        ).lower()

    @staticmethod
    def _phrase_in_text(phrase: str, text: str) -> bool:
        """Word-boundary aware phrase match — 'ad' won't match inside 'read' or 'bad'."""
        pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
        return bool(re.search(pattern, text))

    def _filter_promo_clips(
        self, highlights: list[dict], words: list[WordToken]
    ) -> list[dict]:
        """Remove highlights whose transcript text contains promotional phrases."""
        clean: list[dict] = []
        for h in highlights:
            text = self._extract_segment_text(h, words)
            hit = next(
                (
                    phrase
                    for phrase in self._PROMO_PHRASES
                    if self._phrase_in_text(phrase, text)
                ),
                None,
            )
            if hit:
                logger.info(
                    f"[PromoFilter] Dropped clip '{h.get('title', '')}' — "
                    f"matched blacklist phrase: '{hit}'"
                )
            else:
                clean.append(h)
        if len(clean) < len(highlights):
            logger.info(
                f"[PromoFilter] Removed {len(highlights) - len(clean)} promo/outro clip(s). "
                f"{len(clean)} clean clip(s) remain."
            )
        return clean

    @staticmethod
    def _get_highlight_span(h: dict) -> tuple[float, float]:
        """Return (start, end) of the highlight's full time span in the source video."""
        if "segments" in h and h["segments"]:
            return float(h["segments"][0]["start"]), float(h["segments"][-1]["end"])
        return float(h.get("start", 0)), float(h.get("end", 0))

    @classmethod
    def _dedup_overlapping(cls, highlights: list[dict]) -> list[dict]:
        """
        Remove highlights that substantially overlap a higher-scored highlight.
        Assumes highlights are already sorted by score descending.
        Overlap threshold: >50% of the shorter clip's duration.
        """
        kept: list[dict] = []
        for h in highlights:
            h_s, h_e = cls._get_highlight_span(h)
            h_dur = h_e - h_s
            is_dup = False
            for k in kept:
                k_s, k_e = cls._get_highlight_span(k)
                overlap = max(0.0, min(h_e, k_e) - max(h_s, k_s))
                shorter = min(h_dur, k_e - k_s)
                if shorter > 0 and overlap / shorter > 0.5:
                    logger.info(
                        f"[Dedup] Dropped '{h.get('title', '')[:40]}' — "
                        f"{overlap:.1f}s overlap with '{k.get('title', '')[:40]}'"
                    )
                    is_dup = True
                    break
            if not is_dup:
                kept.append(h)
        return kept

    # ── main entry ───────────────────────────────────────────────────

    def analyze_highlights(
        self,
        words: list[WordToken],
        target_duration: int = 60,
        n_clips: int = 5,
        smart_mode: bool = False,
        tolerance: int = 5,
        condense_mode: bool = False,
        range_mode: bool = False,
        range_label: str = "",
        range_lo: int = 30,
        range_hi: int = 60,
    ) -> list[dict]:
        print(f"[DIAG-AIA] analyze_highlights entered, words={len(words)}", flush=True)
        print(f"[DIAG-AIA] words[0]={words[0] if words else None}", flush=True)
        print(f"[DIAG-AIA] calling _words_to_timed_transcript...", flush=True)
        transcript = self._words_to_timed_transcript(words)
        print(f"[DIAG-AIA] transcript built, len={len(transcript)}", flush=True)
        if not transcript.strip():
            raise ValueError("Transcript is empty — nothing to analyze.")

        video_duration = words[-1]["end"] if words else 0
        # For smart mode clip-count calc, use midpoint of range when in range mode
        effective_target = (range_lo + range_hi) // 2 if range_mode else target_duration
        max_clips = max(1, int(video_duration // effective_target))

        # In range mode the "tolerance" is the full range window
        lo = range_lo if range_mode else (target_duration - tolerance)
        hi = range_hi if range_mode else (target_duration + tolerance)

        system = self._build_system_prompt()
        user = self._build_user_prompt(
            transcript,
            target_duration,
            n_clips,
            smart_mode,
            tolerance,
            video_duration=video_duration,
            max_clips=max_clips,
            condense_mode=condense_mode,
            range_mode=range_mode,
            range_label=range_label,
            range_lo=range_lo,
            range_hi=range_hi,
        )

        print(f"[DIAG-AIA] prompts built: sys_len={len(system)}, user_len={len(user)}", flush=True)

        last_err: Exception | None = None
        for attempt in range(3):
            try:
                print(f"[DIAG-AIA] attempt {attempt+1}: calling _call_llm provider={self.provider}", flush=True)
                raw = self._call_llm(system, user)
                print(f"[DIAG-AIA] attempt {attempt+1}: _call_llm returned len={len(raw)}", flush=True)
                logger.info(f"[LLM raw response attempt {attempt+1}]:\n{raw[:1000]}")
                highlights = self._parse_json(raw)

                if condense_mode:
                    seg_counts = [len(h.get("segments", [])) for h in highlights]
                    has_start = sum(
                        1 for h in highlights if "start" in h and "segments" not in h
                    )
                    logger.info(
                        f"[Condense] AI returned {len(highlights)} highlights — "
                        f"seg counts: {seg_counts}, continuous fallbacks: {has_start}"
                    )
                    highlights = [
                        self._snap_segments_to_words(h, words) for h in highlights
                    ]
                    highlights = self._apply_boundary_fixes(
                        highlights, words, lo=lo, hi=hi
                    )
                    highlights = self._validate_condense_segments(
                        highlights,
                        effective_target,
                        tolerance,
                        words,
                        range_lo=lo,
                        range_hi=hi,
                    )
                else:
                    highlights = [self._snap_to_words(h, words) for h in highlights]
                    highlights = self._apply_boundary_fixes(
                        highlights, words, lo=lo, hi=hi
                    )
                    highlights = self._enforce_tolerance(
                        highlights,
                        effective_target,
                        tolerance,
                        words,
                        range_lo=lo,
                        range_hi=hi,
                    )

                highlights = self._filter_promo_clips(highlights, words)
                highlights.sort(key=lambda x: float(x.get("score", 0)), reverse=True)
                highlights = self._dedup_overlapping(highlights)

                # Smart Mode: enforce minimum clip count with up to 2 retry rounds
                if smart_mode:
                    min_expected = max(3, max_clips // 2)
                    for retry in range(2):
                        if len(highlights) >= min_expected:
                            break
                        ask_for = min_expected + retry  # ask for more each round
                        logger.warning(
                            f"Smart Mode: only {len(highlights)} clip(s) after filter "
                            f"(min={min_expected}), retry {retry + 1}/2 asking for {ask_for}."
                        )
                        fallback_user = self._build_user_prompt(
                            transcript,
                            target_duration,
                            ask_for,
                            smart_mode=False,
                            tolerance=tolerance,
                            video_duration=video_duration,
                            max_clips=max_clips,
                            condense_mode=condense_mode,
                            range_mode=range_mode,
                            range_label=range_label,
                            range_lo=range_lo,
                            range_hi=range_hi,
                        )
                        raw2 = self._call_llm(system, fallback_user)
                        highlights2 = self._parse_json(raw2)
                        if condense_mode:
                            highlights2 = [
                                self._snap_segments_to_words(h, words)
                                for h in highlights2
                            ]
                            highlights2 = self._apply_boundary_fixes(
                                highlights2, words, lo=lo, hi=hi
                            )
                            highlights2 = self._validate_condense_segments(
                                highlights2,
                                effective_target,
                                tolerance,
                                words,
                                range_lo=lo,
                                range_hi=hi,
                            )
                        else:
                            highlights2 = [
                                self._snap_to_words(h, words) for h in highlights2
                            ]
                            highlights2 = self._apply_boundary_fixes(
                                highlights2, words, lo=lo, hi=hi
                            )
                            highlights2 = self._enforce_tolerance(
                                highlights2,
                                effective_target,
                                tolerance,
                                words,
                                range_lo=lo,
                                range_hi=hi,
                            )
                        highlights2 = self._filter_promo_clips(highlights2, words)
                        highlights2.sort(
                            key=lambda x: float(x.get("score", 0)), reverse=True
                        )
                        highlights2 = self._dedup_overlapping(highlights2)
                        # Always take the retry result if it has more clips
                        if len(highlights2) > len(highlights):
                            highlights = highlights2

                return highlights
            except Exception as e:
                last_err = e
                logger.warning(f"LLM attempt {attempt + 1}/3 failed: {e}")
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))

        raise RuntimeError(
            f"AI analysis failed after 3 attempts. Last error: {last_err}"
        )

    def analyze(
        self,
        words: list[WordToken],
        target_duration: int = 60,
        n_clips: int = 5,
    ) -> list[dict]:
        return self.analyze_highlights(words, target_duration, n_clips)

    # ── LLM dispatch ────────────────────────────────────────────────

    def _call_llm(self, system: str, user: str) -> str:
        if self.provider in ("openai", "gemini"):
            return self._call_openai(system, user)
        return self._call_anthropic(system, user)

    def _call_openai(self, system: str, user: str) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        # Gemini supports much larger output; OpenAI gpt-4o caps at 16384
        _max_tokens = 32768 if self.provider == "gemini" else 4096
        kwargs: dict = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=_max_tokens,
        )
        # Gemini 2.5 thinking tokens corrupt JSON — disable thinking
        if self.provider == "gemini":
            kwargs["extra_body"] = {
                "generationConfig": {
                    "thinkingConfig": {"thinkingBudget": 0}
                }
            }
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content.strip()

    def _call_anthropic(self, system: str, user: str) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        msg = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text.strip()

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _repair_json(text: str) -> str:
        """Best-effort repair of common LLM JSON mistakes."""
        text = re.sub(r",\s*([}\]])", r"\1", text)
        text = text.replace("\u2018", "'").replace("\u2019", "'")
        text = text.replace("\u201c", '"').replace("\u201d", '"')
        text = re.sub(r"//[^\n]*", "", text)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        return text

    @staticmethod
    def _truncation_rescue(text: str) -> str:
        """If JSON was truncated mid-stream, salvage complete highlight objects."""
        # Find the highlights array start
        m = re.search(r'"highlights"\s*:\s*\[', text)
        if not m:
            return text
        arr_start = m.end() - 1  # position of '['
        depth = 0
        last_complete = arr_start  # position after last complete object
        i = arr_start
        in_str = False
        escape = False
        obj_start = None
        complete_items = []
        buf = ""
        while i < len(text):
            ch = text[i]
            if escape:
                escape = False
            elif ch == "\\" and in_str:
                escape = True
            elif ch == '"' and not escape:
                in_str = not in_str
            elif not in_str:
                if ch == "{" and depth == 1:
                    obj_start = i
                    buf = ""
                if ch in "{[":
                    depth += 1
                elif ch in "}]":
                    depth -= 1
                    if depth == 1 and obj_start is not None:
                        # Completed one highlight object
                        complete_items.append(text[obj_start: i + 1])
                        obj_start = None
            i += 1

        if not complete_items:
            return text
        # Rebuild clean JSON with only complete items
        rescued = '{"highlights": [' + ",".join(complete_items) + "]}"
        return rescued

    @staticmethod
    def _parse_json(raw: str) -> list[dict]:
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

        def _try(text: str):
            return json.loads(AIAnalyzer._repair_json(text))

        # Try 1: direct
        try:
            parsed = _try(cleaned)
        except json.JSONDecodeError:
            # Try 2: truncation rescue then parse
            rescued = AIAnalyzer._truncation_rescue(cleaned)
            try:
                parsed = _try(rescued)
            except json.JSONDecodeError:
                # Try 3: extract outermost JSON block
                m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
                if m:
                    try:
                        parsed = _try(AIAnalyzer._truncation_rescue(m.group()))
                    except json.JSONDecodeError as e:
                        raise ValueError(
                            f"Could not parse JSON from LLM response:\n{raw[:400]}"
                        ) from e
                else:
                    raise ValueError(
                        f"Could not parse JSON from LLM response:\n{raw[:400]}"
                    )

        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "highlights" in parsed:
            return parsed["highlights"]
        raise ValueError(f"Unexpected JSON structure: {str(parsed)[:200]}")

    # ── BAD-ENDING / BAD-START word sets ────────────────────────────

    _BAD_ENDING_WORDS: frozenset[str] = frozenset(
        {
            # conjunctions / subordinators
            "and",
            "but",
            "so",
            "or",
            "nor",
            "yet",
            "for",
            "because",
            "although",
            "though",
            "even",
            "while",
            "since",
            "if",
            "unless",
            "until",
            "when",
            "whenever",
            "where",
            "whereas",
            "after",
            "before",
            "as",
            "that",
            "than",
            "whether",
            # setup/quote introducers
            "said",
            "say",
            "says",
            "told",
            "tell",
            "tells",
            "asked",
            "replied",
            "answered",
            "continued",
            "added",
            # incomplete aux / linking verbs
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "has",
            "have",
            "had",
            "will",
            "would",
            "could",
            "should",
            "shall",
            "may",
            "might",
            "must",
            "do",
            "does",
            "did",
            # discourse fillers / dangling
            "know",
            "like",
            "just",
            "also",
            "then",
            "now",
            # articles / prepositions that imply continuation
            "the",
            "a",
            "an",
            "to",
            "of",
            "in",
            "on",
            "at",
            "by",
            "for",
            "with",
            "from",
            "into",
            "onto",
            "upon",
            # pronouns that start a new clause
            "he",
            "she",
            "they",
            "it",
            "we",
            "you",
            "i",
            "his",
            "her",
            "their",
            "its",
            "our",
            "your",
            "him",
            "them",
            "us",
        }
    )

    _BAD_START_WORDS: frozenset[str] = frozenset(
        {
            "and",
            "but",
            "so",
            "or",
            "nor",
            "yet",
            "because",
            "although",
            "though",
            "even",
            "while",
            "then",
            "also",
        }
    )

    # ── Sentence-boundary helpers ────────────────────────────────────

    @staticmethod
    def _word_ends_sentence(word_text: str) -> bool:
        """True when a word ends with terminal punctuation (. ? !)."""
        return bool(re.search(r"[.?!][\"')]*$", word_text.strip()))

    @staticmethod
    def _word_ends_clause(word_text: str) -> bool:
        """True when a word ends with a comma (soft pause fallback)."""
        return word_text.strip().endswith(",")

    @staticmethod
    def _silence_after(idx: int, words: list[WordToken], min_gap: float = 0.3) -> bool:
        """True when there is a natural silence ≥ min_gap after words[idx]."""
        if idx + 1 >= len(words):
            return True
        return (words[idx + 1]["start"] - words[idx]["end"]) >= min_gap

    @classmethod
    def _find_word_idx_at(cls, t: float, words: list[WordToken]) -> int:
        """Return index of the word whose span contains t (±300ms tolerance)."""
        best = 0
        best_dist = float("inf")
        for i, w in enumerate(words):
            dist = abs(w["end"] - t)
            if dist < best_dist:
                best_dist = dist
                best = i
        return best

    @classmethod
    def _fix_bad_endings(
        cls,
        end: float,
        start: float,
        words: list[WordToken],
        hi: float,
        max_push: float = 5.0,
    ) -> float:
        """
        If the word at `end` is a bad-ending word, scan forward for the next
        sentence-terminal word. Hard cap: max_push seconds beyond current end.
        Fallback cascade: sentence end → clause comma → natural silence → max_push cap.
        Never exceeds hi (duration window upper bound).
        """
        if not words:
            return end

        idx = cls._find_word_idx_at(end, words)
        raw_word = words[idx]["word"].strip().rstrip(",:;").lower()

        # Already a good ending — nothing to do
        if (
            cls._word_ends_sentence(words[idx]["word"])
            and raw_word not in cls._BAD_ENDING_WORDS
        ):
            return end

        push_limit = min(end + max_push, start + hi)
        sentence_end: float | None = None
        comma_end: float | None = None
        silence_end: float | None = None

        for i in range(idx, len(words)):
            w = words[i]
            if w["end"] > push_limit:
                break
            if cls._word_ends_sentence(w["word"]):
                sentence_end = w["end"]
                break
            if comma_end is None and cls._word_ends_clause(w["word"]):
                comma_end = w["end"]
            if silence_end is None and cls._silence_after(i, words, min_gap=0.3):
                silence_end = w["end"]

        result = sentence_end or comma_end or silence_end or push_limit
        # Clamp to duration window
        return min(result, start + hi)

    @classmethod
    def _fix_bad_starts(
        cls,
        start: float,
        words: list[WordToken],
        lo: float,
        original_start: float,
    ) -> float:
        """
        If the word at `start` is a conjunction/filler, try to pull back to the
        previous sentence boundary. Falls back to skipping past the bad word(s)
        if pulling back would violate the minimum duration (lo).
        """
        if not words:
            return start

        idx = cls._find_word_idx_at(start, words)
        raw_word = words[idx]["word"].strip().lstrip("\"'").lower()

        if raw_word not in cls._BAD_START_WORDS:
            return start

        # Option A: pull back to end of previous sentence
        for i in range(idx - 1, max(0, idx - 20), -1):
            w = words[i]
            if cls._word_ends_sentence(w["word"]):
                candidate = w["end"]
                # Only use if we still have enough duration ahead
                if (original_start - candidate) <= lo * 0.5:
                    return candidate
                break

        # Option B: skip forward past the bad-start word(s)
        for i in range(idx + 1, min(len(words), idx + 5)):
            w = words[i]
            raw = w["word"].strip().lstrip("\"'").lower()
            if raw not in cls._BAD_START_WORDS:
                return w["start"]

        return start

    @classmethod
    def _apply_boundary_fixes(
        cls,
        highlights: list[dict],
        words: list[WordToken],
        lo: float,
        hi: float,
        max_push: float = 5.0,
    ) -> list[dict]:
        """
        Apply _fix_bad_starts + _fix_bad_endings to every continuous highlight.
        Subtitle timestamps are NOT touched here — VideoEditor re-filters words
        from the corrected start/end, so timestamps stay consistent (point 3).
        """
        for h in highlights:
            if "segments" in h:
                # Condense mode: fix each sub-segment independently
                fixed_segs: list[dict] = []
                for seg in h["segments"]:
                    s = float(seg["start"])
                    e = float(seg["end"])
                    seg_hi = e - s + max_push  # per-segment push cap
                    s = cls._fix_bad_starts(s, words, lo=3.0, original_start=s)
                    e = cls._fix_bad_endings(e, s, words, hi=seg_hi, max_push=max_push)
                    # Keep segment if still viable
                    if e - s >= cls.MIN_SEG_DUR:
                        fixed_segs.append({"start": round(s, 3), "end": round(e, 3)})
                h["segments"] = fixed_segs
                h["total_duration"] = round(
                    sum(sg["end"] - sg["start"] for sg in fixed_segs), 2
                )
            else:
                s = float(h.get("start", 0))
                e = float(h.get("end", 0))
                s = cls._fix_bad_starts(s, words, lo=lo, original_start=s)
                e = cls._fix_bad_endings(e, s, words, hi=hi, max_push=max_push)
                h["start"] = round(s, 3)
                h["end"] = round(e, 3)
                h["duration"] = round(e - s, 2)
        return highlights

    @classmethod
    def _find_word_gap_start(
        cls,
        t: float,
        words: list[WordToken],
        buf: float | None = None,
    ) -> float:
        """Apply -buf offset then snap to inter-word gap (prev_word.end + 10ms)."""
        buf = cls.START_BUF if buf is None else buf
        t_buffered = max(0.0, t - buf)
        best_end = 0.0
        for w in words:
            if w["end"] <= t_buffered + 0.05:
                best_end = w["end"]
            else:
                break
        return round(best_end + cls.WORD_GAP_PAD, 3)

    @classmethod
    def _find_word_gap_end(
        cls,
        t: float,
        words: list[WordToken],
        buf: float | None = None,
    ) -> float:
        """Apply +buf offset then snap to inter-word gap (next_word.start - 10ms)."""
        buf = cls.END_BUF if buf is None else buf
        t_buffered = t + buf
        for w in words:
            if w["start"] >= t_buffered - 0.05:
                return round(max(t_buffered, w["start"] - cls.WORD_GAP_PAD), 3)
        return round(words[-1]["end"], 3) if words else round(t_buffered, 3)

    @classmethod
    def _snap_to_words(cls, highlight: dict, words: list[WordToken]) -> dict:
        """Apply boundary buffers then snap to inter-word gaps."""
        if not words:
            return highlight

        raw_s = float(highlight.get("start", 0))
        raw_e = float(highlight.get("end", 0))

        snapped_s = cls._find_word_gap_start(raw_s, words)
        snapped_e = cls._find_word_gap_end(raw_e, words)

        if snapped_s >= snapped_e - 1.0:
            snapped_s = raw_s
            snapped_e = raw_e

        highlight["start"] = snapped_s
        highlight["end"] = snapped_e
        highlight["duration"] = round(snapped_e - snapped_s, 2)
        return highlight

    @classmethod
    def _enforce_tolerance(
        cls,
        highlights: list[dict],
        target: int,
        tolerance: int,
        words: list[WordToken],
        range_lo: int | None = None,
        range_hi: int | None = None,
    ) -> list[dict]:
        """
        Ensure every clip's duration falls within the window.
        Window = [range_lo, range_hi] when provided (range mode),
        otherwise [target-tolerance, target+tolerance] (fixed mode).
        Physical validation: any clip outside the window is snapped to the
        nearest word-end that satisfies it, with word-gap boundary correction.
        """
        lo = range_lo if range_lo is not None else target - tolerance
        hi = range_hi if range_hi is not None else target + tolerance
        ideal_target = (lo + hi) // 2 if range_lo is not None else target
        ends_list = [w["end"] for w in words]

        result: list[dict] = []
        for h in highlights:
            raw_s = float(h.get("start", 0))
            raw_e = float(h.get("end", 0))

            # Apply word-gap boundary correction first
            snapped_s = cls._find_word_gap_start(raw_s, words)
            snapped_e = cls._find_word_gap_end(raw_e, words)
            if snapped_s >= snapped_e - 1.0:
                snapped_s, snapped_e = raw_s, raw_e

            h["start"] = snapped_s
            dur = snapped_e - snapped_s

            if lo <= dur <= hi:
                # End is already good after snapping — keep it
                h["end"] = snapped_e
                h["duration"] = round(dur, 2)
                result.append(h)
                continue

            # Physical enforcement: find the word-end closest to ideal that fits window
            ideal_end = snapped_s + ideal_target
            candidates = sorted(
                [e for e in ends_list if lo <= e - snapped_s <= hi],
                key=lambda e: abs(e - ideal_end),
            )
            if candidates:
                h["end"] = candidates[0]
                h["duration"] = round(h["end"] - snapped_s, 2)
            else:
                h["end"] = snapped_e
                h["duration"] = round(dur, 2)
                h["duration_warning"] = (
                    f"Duration {dur:.1f}s outside {lo}-{hi}s window (could not auto-fix)"
                )
            result.append(h)

        return result

    @classmethod
    def _snap_segments_to_words(
        cls,
        highlight: dict,
        words: list[WordToken],
    ) -> dict:
        """For each sub-segment apply boundary buffers then snap to inter-word gaps."""
        if not words or "segments" not in highlight:
            return highlight

        snapped: list[dict] = []
        for seg in highlight["segments"]:
            raw_s = float(seg.get("start", 0))
            raw_e = float(seg.get("end", 0))

            s = cls._find_word_gap_start(raw_s, words)
            e = cls._find_word_gap_end(raw_e, words)

            if s >= e - 1.0:
                s, e = raw_s, raw_e
            if e - s >= cls.MIN_SEG_DUR:
                snapped.append({"start": s, "end": e})

        highlight["segments"] = snapped
        highlight["total_duration"] = round(
            sum(s["end"] - s["start"] for s in snapped), 2
        )
        return highlight

    @staticmethod
    def _validate_condense_segments(
        highlights: list[dict],
        target: int,
        tolerance: int,
        words: list[WordToken] | None = None,
        range_lo: int | None = None,
        range_hi: int | None = None,
    ) -> list[dict]:
        """
        Per-highlight: drop sub-segments < 3s, sort, dedupe overlaps.
        Cross-highlight: remove segments already claimed by a higher-scored highlight.
        Duration repair: extend/trim last segment to satisfy the window.
        Window = [range_lo, range_hi] in range mode, [target±tolerance] in fixed mode.
        """
        lo = range_lo if range_lo is not None else target - tolerance
        hi = range_hi if range_hi is not None else target + tolerance
        max_span = int(hi * 1.8)  # max allowed span from first-seg start to last-seg end
        ideal = (lo + hi) // 2
        ends_list = [w["end"] for w in words] if words else []

        result: list[dict] = []
        for h in highlights:
            segs = [s for s in h.get("segments", []) if s["end"] - s["start"] >= 3.0]
            if not segs:
                continue

            # Pre-trim any individual sub-segment that alone exceeds half the window.
            # Such a segment is essentially a full clip, not a condensed fragment.
            # Use ends_list for word-boundary-aware trimming when possible.
            seg_max = hi // 2 + 5
            trimmed_segs: list[dict] = []
            for s in segs:
                dur = s["end"] - s["start"]
                if dur > seg_max:
                    ideal_end = s["start"] + seg_max
                    if ends_list:
                        candidates = [
                            e for e in ends_list
                            if s["start"] + 3.0 <= e <= ideal_end + 3.0
                        ]
                        new_end = min(candidates, key=lambda e: abs(e - ideal_end)) if candidates else ideal_end
                    else:
                        new_end = ideal_end
                    trimmed_segs.append({"start": s["start"], "end": new_end})
                else:
                    trimmed_segs.append(s)
            segs = trimmed_segs

            # Intra-highlight dedup only: sort and remove overlapping sub-segments.
            segs.sort(key=lambda s: s["start"])
            available: list[dict] = [segs[0]]
            for s in segs[1:]:
                if s["start"] >= available[-1]["end"]:
                    available.append(s)

            # Span check: if sub-segments span too large a region they are from
            # different topics, not filler-trimmed from one continuous idea.
            # Drop trailing segments until span is acceptable or only 1 remains.
            while len(available) > 1:
                span = available[-1]["end"] - available[0]["start"]
                if span <= max_span:
                    break
                available = available[:-1]

            total = sum(s["end"] - s["start"] for s in available)

            if total < lo and ends_list:
                # Extend last segment forward to reach lo
                deficit = lo - total
                last = available[-1]
                ideal_new_end = last["end"] + deficit + tolerance * 0.5
                candidates = [
                    e for e in ends_list if last["end"] < e <= ideal_new_end + 2.0
                ]
                if candidates:
                    new_end = min(candidates, key=lambda e: abs(e - ideal_new_end))
                    new_total = total + (new_end - last["end"])
                    if lo <= new_total <= hi:
                        available[-1] = {"start": last["start"], "end": new_end}
                        total = new_total

            elif total > hi and ends_list:
                # Trim from the back: first try trimming the last segment, then drop it.
                while total > hi and len(available) > 1:
                    last = available[-1]
                    last_dur = last["end"] - last["start"]
                    rest = total - last_dur

                    if rest >= lo:
                        # Dropping the last segment keeps us in window — drop it
                        available = available[:-1]
                        total = rest
                    else:
                        # Must keep part of last segment — trim it to hit the window
                        need = ideal - rest
                        need = max(3.0, need)
                        ideal_end = last["start"] + need
                        candidates = [
                            e for e in ends_list
                            if last["start"] + 3.0 <= e <= last["end"]
                            and lo <= rest + (e - last["start"]) <= hi
                        ]
                        if candidates:
                            new_end = min(candidates, key=lambda e: abs(rest + (e - last["start"]) - ideal))
                            available[-1] = {"start": last["start"], "end": new_end}
                            total = rest + (new_end - last["start"])
                        break

                # Last resort: single segment still over — trim it
                if total > hi and available and ends_list:
                    last = available[-1]
                    rest = total - (last["end"] - last["start"])
                    candidates = [
                        e for e in ends_list
                        if last["start"] + 3.0 <= e <= last["end"]
                        and lo <= rest + (e - last["start"]) <= hi
                    ]
                    if candidates:
                        new_end = min(candidates, key=lambda e: abs(rest + (e - last["start"]) - ideal))
                        available[-1] = {"start": last["start"], "end": new_end}
                        total = rest + (new_end - last["start"])

            h["segments"] = available
            h["total_duration"] = round(total, 2)
            if not (lo <= total <= hi):
                h["duration_warning"] = (
                    f"Total {total:.1f}s outside {lo}-{hi}s window (could not auto-fix)"
                )
            result.append(h)
        return result


# ─────────────────────────────────────────────────────────────────
# Video Editor
# ─────────────────────────────────────────────────────────────────


class VideoEditor:
    DEFAULT_FONT = "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"

    # Platform fallback fonts for burn-in subtitles when no font_path supplied
    _FONT_CANDIDATES: list[str] = [
        # Linux (Docker / CI)
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        # Windows
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]

    CROSSFADE_DUR: float = 0.10  # 100ms audio crossfade at segment joins
    ZOOM_FACTOR: float = 1.05  # 5% zoom on segments after the first (zoom-cut effect)
    OVERALL_FADE_DUR: float = 1.0  # full in/out fade duration for continuous clips
    CONDENSED_FADE_DUR: float = 0.5  # shorter overall fade for condensed clips

    def __init__(self, output_dir: str = "output") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ── public API ───────────────────────────────────────────────────

    @staticmethod
    def _drawtext_supported() -> bool:
        """Return False in PyInstaller frozen bundles where drawtext causes crashes.

        Bundled ffmpeg builds crash when drawtext filter is used inside a
        PyInstaller-frozen process on both Windows (ACCESS VIOLATION 0xC0000005)
        and macOS (SIGSEGV 11). Disable burn-in subtitles in any frozen bundle
        to prevent the crash.
        """
        if getattr(sys, "frozen", False):
            return False
        # Also check STUDIOKIT_FFMPEG_DIR — set in frozen bundle child processes
        # where sys.frozen may be False (Streamlit re-execs as unfrozen child)
        if os.environ.get("STUDIOKIT_FFMPEG_DIR"):
            return False
        return True

    def process_clip(
        self,
        source_path: str,
        highlight: dict,
        words: list[WordToken],
        clip_index: int,
        vertical: bool = True,
        font_path: str | None = None,
        burn_subtitles: bool = True,
        progress_callback: Callable[[str], None] | None = None,
    ) -> str:
        """Route to condensed or continuous clip renderer based on highlight structure."""
        # drawtext crashes gyan.dev static ffmpeg on Windows frozen bundle — disable safely
        if burn_subtitles and not self._drawtext_supported():
            logger.warning("Burn-in subtitles disabled on Windows bundle (drawtext segfault workaround)")
            burn_subtitles = False

        title = highlight.get("title", f"clip_{clip_index}")
        if progress_callback:
            progress_callback(f"🎬 Rendering clip {clip_index}: {title[:45]}…")

        segs = highlight.get("segments", [])
        if len(segs) == 1:
            if "start" not in highlight:
                highlight["start"] = segs[0]["start"]
                highlight["end"] = segs[0]["end"]
            highlight.pop("segments", None)

        mode = (
            "condensed"
            if ("segments" in highlight and len(highlight.get("segments", [])) > 1)
            else "continuous"
        )
        logger.info(
            f"[Routing] Clip '{highlight.get('title', '')[:40]}' → {mode} ({len(segs)} seg(s) from AI)"
        )

        if "segments" in highlight and len(highlight["segments"]) > 1:
            return self._process_condensed_clip(
                source_path,
                highlight,
                words,
                clip_index,
                vertical,
                font_path,
                burn_subtitles,
                progress_callback,
            )
        return self._process_continuous_clip(
            source_path,
            highlight,
            words,
            clip_index,
            vertical,
            font_path,
            burn_subtitles,
        )

    def _process_continuous_clip(
        self,
        source_path: str,
        highlight: dict,
        words: list[WordToken],
        clip_index: int,
        vertical: bool,
        font_path: str | None,
        burn_subtitles: bool,
    ) -> str:
        start = float(highlight["start"])
        end = float(highlight["end"])
        title = highlight.get("title", f"clip_{clip_index}")
        safe = re.sub(r"[^\w\s\-]", "_", title)[:50].strip()
        out_path = str(self.output_dir / f"{clip_index:02d}_{safe}.mp4")

        probe = self._probe_video(source_path)
        w, h = probe["width"], probe["height"]

        clip_words: list[WordToken] = (
            [
                ww
                for ww in words
                if ww["start"] >= start - 0.05 and ww["end"] <= end + 0.05
            ]
            if burn_subtitles
            else []
        )

        vf = self._build_vf(
            w, h, start, clip_words, vertical, font_path, burn_subtitles
        )
        af = self._build_af(
            end - start, start_fade=0.1, end_fade=0.1, overall_fade=True
        )
        self._run_ffmpeg(source_path, out_path, start, end - start, vf, af)
        return out_path

    def _process_condensed_clip(
        self,
        source_path: str,
        highlight: dict,
        words: list[WordToken],
        clip_index: int,
        vertical: bool,
        font_path: str | None,
        burn_subtitles: bool,
        progress_callback: Callable[[str], None] | None = None,
    ) -> str:
        """
        Multi-segment jump-cut renderer.
        1. Render each sub-segment to a temp file (crop/scale; zoom on seg > 0)
        2. Remap subtitle timestamps to the concatenated timeline
        3. Concat segments with 100ms audio crossfade between joins
        4. Burn remapped subtitles onto the final concat
        """
        import tempfile

        segments = highlight["segments"]
        title = highlight.get("title", f"clip_{clip_index}")
        safe = re.sub(r"[^\w\s\-]", "_", title)[:50].strip()
        out_path = str(self.output_dir / f"{clip_index:02d}_{safe}.mp4")

        probe = self._probe_video(source_path)
        w, h = probe["width"], probe["height"]
        n_segs = len(segments)

        with tempfile.TemporaryDirectory() as tmp:
            seg_paths: list[str] = []
            for si, seg in enumerate(segments):
                if progress_callback:
                    progress_callback(
                        f"🔀 Clip {clip_index} — segment {si + 1}/{n_segs} "
                        f"({seg['start']:.1f}s→{seg['end']:.1f}s)…"
                    )
                seg_start = float(seg["start"])
                seg_end = float(seg["end"])
                seg_dur = seg_end - seg_start
                seg_path = str(Path(tmp) / f"seg_{si:03d}.mp4")

                zoom = self.ZOOM_FACTOR if si > 0 else 1.0
                vf = self._build_segment_vf(w, h, vertical, zoom)
                af = self._build_af(
                    seg_dur, start_fade=0.1, end_fade=0.1, overall_fade=False
                )

                cmd = [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    f"{seg_start:.3f}",
                    "-i",
                    source_path,
                    "-t",
                    f"{seg_dur:.3f}",
                    "-vf",
                    vf,
                    "-af",
                    af,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "23",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                    seg_path,
                ]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=3600
                )
                if result.returncode != 0:
                    tail = "\n".join(result.stderr.splitlines()[-30:])
                    raise RuntimeError(f"Segment {si} render failed:\n{tail}")
                seg_paths.append(seg_path)

            remapped_words = self._remap_words_to_concat_timeline(words, segments)
            concat_path = str(Path(tmp) / "concat_raw.mp4")
            self._concat_with_crossfade(seg_paths, concat_path, self.CROSSFADE_DUR)

            total_dur = sum(float(s["end"]) - float(s["start"]) for s in segments)
            overall_af = self._build_af(
                total_dur,
                start_fade=self.CONDENSED_FADE_DUR,
                end_fade=self.CONDENSED_FADE_DUR,
                overall_fade=False,
            )

            if burn_subtitles and remapped_words:
                sub_filters = self.add_burn_in_subtitles(
                    remapped_words, clip_start=0.0, font_path=font_path
                )
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    concat_path,
                    "-vf",
                    ",".join(sub_filters),
                    "-af",
                    overall_af,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "23",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                    out_path,
                ]
            else:
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    concat_path,
                    "-af",
                    overall_af,
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                    out_path,
                ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                tail = "\n".join(result.stderr.splitlines()[-30:])
                raise RuntimeError(f"Final render failed:\n{tail}")

        return out_path

    @staticmethod
    def _remap_words_to_concat_timeline(
        words: list[WordToken],
        segments: list[dict],
    ) -> list[WordToken]:
        """Map original Whisper timestamps into the new concatenated timeline."""
        remapped: list[WordToken] = []
        cursor = 0.0
        for seg in segments:
            seg_start = float(seg["start"])
            seg_end = float(seg["end"])
            seg_words = [
                w
                for w in words
                if w["start"] >= seg_start - 0.05 and w["end"] <= seg_end + 0.05
            ]
            offset = cursor - seg_start
            for w in seg_words:
                remapped.append(
                    {
                        "word": w["word"],
                        "start": round(w["start"] + offset, 3),
                        "end": round(w["end"] + offset, 3),
                    }
                )
            cursor += seg_end - seg_start
        return remapped

    def _concat_with_crossfade(
        self,
        seg_paths: list[str],
        out_path: str,
        crossfade_dur: float = 0.10,
    ) -> None:
        """Concatenate segments with audio crossfade at each join; video cuts stay sharp."""
        n = len(seg_paths)
        if n == 1:
            import shutil

            shutil.copy2(seg_paths[0], out_path)
            return

        inputs: list[str] = []
        for p in seg_paths:
            inputs += ["-i", p]

        v_inputs = "".join(f"[{i}:v]" for i in range(n))
        filter_parts = [f"{v_inputs}concat=n={n}:v=1:a=0[outv]"]

        prev = "[0:a]"
        for i in range(1, n):
            label = f"[acf{i}]" if i < n - 1 else "[outa]"
            filter_parts.append(
                f"{prev}[{i}:a]acrossfade=d={crossfade_dur}:c1=tri:c2=tri{label}"
            )
            prev = f"[acf{i}]"

        cmd = [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            tail = "\n".join(result.stderr.splitlines()[-30:])
            raise RuntimeError(f"Crossfade concat failed:\n{tail}")

    def crop_to_vertical(self, w: int, h: int) -> tuple[str, int, int]:
        """Return (crop_filter_str, out_w, out_h) for center-weighted 9:16 crop."""
        target_w = int(h * 9 / 16)
        if target_w > w:
            target_w = w
            target_h = min(int(w * 16 / 9), h)  # clamp to actual height
        else:
            target_h = h
        x = max(0, (w - target_w) // 2)
        y = max(0, (h - target_h) // 2)
        return f"crop={target_w}:{target_h}:{x}:{y}", target_w, target_h

    def add_burn_in_subtitles(
        self,
        words: list[WordToken],
        clip_start: float,
        font_path: str | None = None,
        fontsize: int = 54,
    ) -> list[str]:
        """Build FFmpeg drawtext filter strings for burn-in subtitles."""
        if font_path and Path(font_path).exists():
            resolved_font: str | None = font_path
        else:
            resolved_font = next(
                (f for f in self._FONT_CANDIDATES if Path(f).exists()), None
            )
        font_decl = f"fontfile='{resolved_font}':" if resolved_font else ""
        if not resolved_font:
            logger.warning("No font found for burn-in subtitles — text may not render on some ffmpeg builds")

        chunks = self._split_words_by_chars(words, fontsize=fontsize)

        filters: list[str] = []
        for chunk in chunks:
            text = " ".join(w["word"].strip() for w in chunk)
            t0 = round(chunk[0]["start"] - clip_start, 3)
            t1 = round(chunk[-1]["end"] - clip_start, 3)
            if t1 <= t0:
                t1 = t0 + 0.5

            escaped = (
                text.replace("\\", "\\\\\\\\")
                .replace("'", "'")
                .replace(":", "\\:")
                .replace("%", "\\%")
                .replace("[", "\\[")
                .replace("]", "\\]")
            )

            filters.append(
                f"drawtext={font_decl}"
                f"text='{escaped}':"
                f"fontsize={fontsize}:"
                f"fontcolor=white:"
                f"borderw=4:"
                f"bordercolor=black@0.8:"
                f"shadowx=2:shadowy=2:shadowcolor=black@0.6:"
                f"x=(w-text_w)/2:"
                f"y=h-180:"
                f"enable='between(t,{t0},{t1})'"
            )
        return filters

    @staticmethod
    def _split_words_by_chars(
        words: list[WordToken],
        fontsize: int = 54,
        screen_w: int = 1080,
        margin: int = 80,
    ) -> list[list[WordToken]]:
        """
        Group words into subtitle lines that fit within the screen width.
        CJK ≈ fontsize×1.0px, ASCII/Latin ≈ fontsize×0.55px, space ≈ fontsize×0.3px.
        """
        if not words:
            return []

        usable_px = screen_w - margin

        def _is_cjk(c: str) -> bool:
            return (
                "一" <= c <= "鿿"
                or "぀" <= c <= "ヿ"
                or "가" <= c <= "힯"
                or "　" <= c <= "〿"
                or "＀" <= c <= "￯"
            )

        def _char_px(c: str) -> float:
            if c == " ":
                return fontsize * 0.3
            return fontsize * 1.0 if _is_cjk(c) else fontsize * 0.55

        def _word_px(word: str) -> float:
            return sum(_char_px(c) for c in word.strip())

        full_text = " ".join(w["word"] for w in words)
        non_space = [c for c in full_text if not c.isspace()]
        cjk_ratio = (
            sum(1 for c in non_space if _is_cjk(c)) / len(non_space) if non_space else 0
        )
        logger.debug(f"Subtitle CJK ratio: {cjk_ratio:.2f}, usable_px={usable_px}")

        chunks: list[list[WordToken]] = []
        current: list[WordToken] = []
        current_px = 0.0

        for w in words:
            w_px = _word_px(w["word"])
            sep_px = _char_px(" ") if current else 0.0

            if current and current_px + sep_px + w_px > usable_px:
                chunks.append(current)
                current = [w]
                current_px = w_px
            else:
                current.append(w)
                current_px += sep_px + w_px

        if current:
            chunks.append(current)
        return chunks

    # ── internal helpers ────────────────────────────────────────────

    def _build_segment_vf(
        self,
        w: int,
        h: int,
        vertical: bool,
        zoom: float = 1.0,
    ) -> str:
        """Build vf string for a single segment (no subtitles)."""
        if vertical:
            crop_f, cw, ch = self.crop_to_vertical(w, h)
            if zoom > 1.0:
                # scale up then crop back to the pre-zoom crop dimensions
                return (
                    f"{crop_f},"
                    f"scale=iw*{zoom}:ih*{zoom},"
                    f"crop={cw}:{ch}:(iw-{cw})/2:(ih-{ch})/2,"
                    f"scale=1080:1920:force_original_aspect_ratio=decrease,"
                    f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"
                )
            return (
                f"{crop_f},"
                f"scale=1080:1920:force_original_aspect_ratio=decrease,"
                f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"
            )
        if zoom > 1.0:
            return (
                f"scale=iw*{zoom}:ih*{zoom},"
                f"crop={w}:{h}:(iw-{w})/2:(ih-{h})/2,"
                f"scale=1920:1080:force_original_aspect_ratio=decrease,"
                f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black"
            )
        return (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black"
        )

    def _build_vf(
        self,
        w: int,
        h: int,
        clip_start: float,
        clip_words: list[WordToken],
        vertical: bool,
        font_path: str | None,
        burn_subtitles: bool,
    ) -> str:
        parts: list[str] = []
        if vertical:
            crop_f, _, _ = self.crop_to_vertical(w, h)
            parts.append(crop_f)
            parts.append("scale=1080:1920:force_original_aspect_ratio=decrease")
            parts.append("pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black")
        else:
            parts.append("scale=1920:1080:force_original_aspect_ratio=decrease")
            parts.append("pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black")

        if burn_subtitles and clip_words:
            sub_filters = self.add_burn_in_subtitles(clip_words, clip_start, font_path)
            parts.extend(sub_filters)

        return ",".join(parts)

    @staticmethod
    def _build_af(
        duration: float,
        start_fade: float = 0.1,
        end_fade: float = 0.1,
        overall_fade: bool = True,
    ) -> str:
        """
        Build audio filter chain.
        overall_fade=True: 1s in/out fades for continuous clips (replaces 100ms boundary fades).
        overall_fade=False: 100ms boundary fades only (for segment edges in condensed clips).
        """
        parts: list[str] = []
        if overall_fade and duration > 2.0:
            # Single 1s in/out — no need for additional 100ms fades on top
            long_fade_out_st = max(0.0, duration - 1.0)
            parts.append("afade=t=in:st=0:d=1")
            parts.append(f"afade=t=out:st={long_fade_out_st:.3f}:d=1")
        else:
            # 100ms boundary fades to prevent audio pops at cut points
            parts.append(f"afade=t=in:st=0:d={start_fade:.3f}")
            fade_out_st = max(start_fade, duration - end_fade)
            parts.append(f"afade=t=out:st={fade_out_st:.3f}:d={end_fade:.3f}")
        parts.append("loudnorm=I=-16:LRA=11:TP=-1.5")
        return ",".join(parts)

    @staticmethod
    def _run_ffmpeg(
        src: str,
        dst: str,
        start: float,
        duration: float,
        vf: str,
        af: str,
    ) -> None:
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            src,
            "-t",
            f"{duration:.3f}",
            "-vf",
            vf,
            "-af",
            af,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            dst,
        ]
        logger.debug("FFmpeg cmd: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            tail = "\n".join(result.stderr.splitlines()[-40:])
            raise RuntimeError(f"FFmpeg failed (rc={result.returncode}):\n{tail}")

    @staticmethod
    def _ffprobe_exe() -> str:
        """Return absolute path to ffprobe binary from bundled ffmpeg dir, or bare 'ffprobe'."""
        ffmpeg_dir = _get_ffmpeg_dir()
        if ffmpeg_dir:
            ext = ".exe" if sys.platform == "win32" else ""
            candidate = Path(ffmpeg_dir) / f"ffprobe{ext}"
            if candidate.exists():
                return str(candidate)
        return "ffprobe"

    @staticmethod
    def _probe_video(path: str) -> dict:
        ffprobe = VideoEditor._ffprobe_exe()
        cmd = [
            ffprobe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffprobe failed for {path} "
                f"(exe={ffprobe}, rc={result.returncode}): "
                f"stdout={result.stdout[:200]!r} stderr={result.stderr[:200]!r}"
            )
        data = json.loads(result.stdout)
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                return {"width": int(s["width"]), "height": int(s["height"])}
        raise RuntimeError(f"No video stream in {path}: streams={[s.get('codec_type') for s in data.get('streams', [])]}")

    @staticmethod
    def probe_duration(path: str) -> float:
        """Return video duration in seconds via ffprobe. Falls back to 0.0 on error."""
        cmd = [
            VideoEditor._ffprobe_exe(),
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return 0.0
        try:
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
        except (ValueError, KeyError):
            return 0.0


# ─────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────


class AutoHighlightEngine:
    def __init__(
        self,
        provider: str = "openai",
        api_key: str = "",
        llm_model: str = "",
        whisper_model: str = "base",
        downloads_dir: str = "downloads",
        output_dir: str = "output",
        base_url: str = "",
    ) -> None:
        self.downloader = Downloader(downloads_dir)
        self.transcriber = Transcriber(model_size=whisper_model)
        from config_client import fetch_config as _fetch_config
        self.analyzer = AIAnalyzer(
            provider=provider, api_key=api_key, model=llm_model, base_url=base_url,
            workflow_config=_fetch_config(),
        )
        self.editor = VideoEditor(output_dir)
        self.silence_remover = SilenceRemover()

    def process(
        self,
        source: str,
        target_duration: int = 60,
        n_clips: int = 5,
        vertical: bool = True,
        language: str | None = None,
        font_path: str | None = None,
        burn_subtitles: bool = True,
        remove_silence: bool = False,
        smart_mode: bool = False,
        condense_mode: bool = False,
        range_mode: bool = False,
        range_label: str = "",
        range_lo: int = 30,
        range_hi: int = 60,
        max_resolution: int = 720,
        auto_delete_source: bool = True,
        status_callback: Callable[[str], None] | None = None,
        clip_saved_callback: Callable[[dict], None] | None = None,
    ) -> list[dict]:
        """
        Full pipeline: Download → (Silence Removal) → Transcribe → AI Analyze → Render.
        When smart_mode=True, n_clips is a per-video cap; actual count derives from
        video_duration // target_duration after transcription.
        """

        def update(msg: str) -> None:
            logger.info(msg)
            if status_callback:
                status_callback(msg)

        is_url = source.startswith(("http://", "https://"))
        if is_url:
            update(f"⬇️ Downloading video ({max_resolution}p max)…")
            video_path = self.downloader.download(
                source,
                progress_callback=status_callback,
                max_height=max_resolution,
            )
        else:
            video_path = source
        update(f"✅ Video ready: {Path(video_path).name}")

        if remove_silence:
            update("🔇 Removing silence gaps…")
            silent_out = str(
                Path(video_path).with_stem(Path(video_path).stem + "_nosilence")
            )
            video_path = self.silence_remover.remove_silence(
                video_path, silent_out, progress_callback=status_callback
            )
            update("✅ Silence removed")

        update("🎙️ Transcribing audio (may take several minutes for long videos)…")
        words = self.transcriber.transcribe(video_path, language=language)
        if not words:
            raise ValueError("Transcription returned no words. Check audio track.")
        update(f"✅ Transcription complete: {len(words)} words")

        # DIAG markers — these prints survive a crash because we flush.
        # If user sees "STEP A" but not "STEP B", we know where it crashed.
        print(f"[DIAG] STEP A: post-transcribe, words={len(words)}, smart_mode={smart_mode}", flush=True)

        effective_n_clips = n_clips
        if smart_mode:
            print(f"[DIAG] STEP B: calling probe_duration on {video_path}", flush=True)
            probed = VideoEditor.probe_duration(video_path)
            print(f"[DIAG] STEP B done: probed={probed}", flush=True)
            video_duration = probed if probed > 0 else words[-1]["end"]
            ref_duration = (range_lo + range_hi) // 2 if range_mode else target_duration
            auto_count = max(1, int(video_duration // ref_duration))
            effective_n_clips = min(auto_count, n_clips)
            update(
                f"🧠 Smart Count: {video_duration:.0f}s video → "
                f"{auto_count} possible clips → using {effective_n_clips} (cap={n_clips})"
            )

        modes: list[str] = []
        if smart_mode:
            modes.append("Smart Count")
        if range_mode:
            modes.append(f"Range ({range_label})")
        if condense_mode:
            modes.append("Condense")
        if not modes:
            modes.append("Hook-First")
        update(f"🧠 AI analyzing highlights ({' + '.join(modes)} mode)…")
        print(f"[DIAG] STEP C: calling analyze_highlights, provider={getattr(self.analyzer, 'provider', '?')}", flush=True)

        highlights = self.analyzer.analyze_highlights(
            words,
            target_duration=target_duration,
            n_clips=effective_n_clips,
            smart_mode=smart_mode,
            condense_mode=condense_mode,
            range_mode=range_mode,
            range_label=range_label,
            range_lo=range_lo,
            range_hi=range_hi,
        )
        update(f"✅ Found {len(highlights)} highlight segments")

        results: list[dict] = []
        for i, hl in enumerate(highlights, 1):
            is_condensed = "segments" in hl and len(hl["segments"]) > 1
            seg_count = len(hl.get("segments", [])) if is_condensed else 1
            update(
                f"🎬 Rendering clip {i}/{len(highlights)}: {hl.get('title', '')[:40]}"
                + (f" [{seg_count} segments]" if is_condensed else "")
            )
            base: dict = {
                "title": hl.get("title", f"Clip {i}"),
                "score": hl.get("score", 0),
                "hook_strength": hl.get("hook_strength", 0),
                "reason": hl.get("reason", ""),
                "reason_for_duration": hl.get("reason_for_duration", ""),
                "selected_range": hl.get("selected_range", ""),
                "caption": hl.get("caption", ""),
                "start": hl.get("start")
                or (hl["segments"][0]["start"] if is_condensed else 0),
                "end": hl.get("end")
                or (hl["segments"][-1]["end"] if is_condensed else 0),
                "duration": hl.get("total_duration") or hl.get("duration", 0),
                "duration_warning": hl.get("duration_warning"),
                "condensed": is_condensed,
                "segment_count": seg_count,
            }
            try:
                out = self.editor.process_clip(
                    source_path=video_path,
                    highlight=hl,
                    words=words,
                    clip_index=i,
                    vertical=vertical,
                    font_path=font_path,
                    burn_subtitles=burn_subtitles,
                    progress_callback=status_callback,
                )
                clip_result = {**base, "output_path": out}
                results.append(clip_result)
                if clip_saved_callback:
                    try:
                        clip_saved_callback(clip_result)
                    except Exception as cb_err:
                        logger.warning(f"clip_saved_callback failed: {cb_err}")
            except Exception as e:
                logger.error(f"Clip {i} render failed: {e}")
                failed = {**base, "output_path": None, "error": str(e)}
                results.append(failed)
                if clip_saved_callback:
                    try:
                        clip_saved_callback(failed)
                    except Exception as cb_err:
                        logger.warning(f"clip_saved_callback failed: {cb_err}")

        update("🎉 All clips processed!")

        if auto_delete_source and is_url and Path(video_path).exists():
            try:
                Path(video_path).unlink()
                logger.info(f"Auto-deleted source: {video_path}")
            except OSError as e:
                logger.warning(f"Could not delete source file: {e}")

        return results
