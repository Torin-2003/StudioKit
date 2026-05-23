import subprocess
import os
import shutil
import cv2
from pathlib import Path
from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector


def get_video_fps(video_path: str) -> float:
    cap = cv2.VideoCapture(video_path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        return fps if fps > 0 else 30.0
    finally:
        cap.release()


def detect_scenes(video_path: str, threshold: float = 27.0, min_clip_sec: float = 0.5) -> list[tuple]:
    """
    Detect scene boundaries in a video.
    Returns list of (start_timecode, end_timecode) tuples.
    threshold: sensitivity — lower = more cuts detected (5-100 range)
    min_clip_sec: scenes shorter than this are filtered out before returning
    """
    video = open_video(video_path)
    fps = get_video_fps(video_path)
    min_scene_len = max(1, int(fps * min_clip_sec))

    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=threshold, min_scene_len=min_scene_len))
    scene_manager.detect_scenes(video, show_progress=False)
    scene_list = scene_manager.get_scene_list()

    if not scene_list:
        duration = video.duration
        return [(video.base_timecode, duration)]

    # Secondary filter: drop any scene still shorter than min_clip_sec
    filtered = [
        s for s in scene_list
        if (s[1].get_seconds() - s[0].get_seconds()) >= min_clip_sec
    ]
    return filtered if filtered else scene_list


def timecode_to_seconds(tc) -> float:
    return tc.get_seconds()


def seconds_to_hhmmss(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _is_black_clip(clip_path: str, brightness_threshold: float = 15.0, sample_frames: int = 5) -> bool:
    """Return True if the clip is predominantly black (average brightness below threshold)."""
    cap = cv2.VideoCapture(clip_path)
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total == 0:
            return False
        indices = [int(total * i / sample_frames) for i in range(min(sample_frames, total))]
        brightness_sum = 0.0
        count = 0
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness_sum += cv2.mean(gray)[0]
            count += 1
        if count == 0:
            return False
        return (brightness_sum / count) < brightness_threshold
    except Exception:
        return False
    finally:
        cap.release()


def split_video(
    video_path: str,
    scenes: list[tuple],
    output_dir: str,
    base_name: str,
    progress_callback=None,
    min_clip_sec: float = 0.5,
    black_filter: bool = True,
    brightness_threshold: float = 15.0,
) -> list[dict]:
    """
    Split video into clips using ffmpeg based on scene list.
    Returns list of dicts with clip info: path, start, end, duration.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    fps = get_video_fps(video_path)
    one_frame = 1.0 / fps  # trim this from the end of every clip

    clips = []
    total = len(scenes)

    for i, (start_tc, end_tc) in enumerate(scenes):
        start_sec = timecode_to_seconds(start_tc)
        end_sec = timecode_to_seconds(end_tc)
        # subtract one frame so the last frame of the next scene doesn't bleed in
        duration_sec = max(0, end_sec - start_sec - one_frame)

        if duration_sec < min_clip_sec:
            continue

        clip_filename = f"{base_name}_raw_{i + 1:03d}.mp4"
        clip_path = str(output_path / clip_filename)

        cmd = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-ss", str(start_sec),
            "-t", str(duration_sec),
            "-c:v", "libx264",
            "-c:a", "aac",
            "-avoid_negative_ts", "1",
            clip_path,
        ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        if black_filter and _is_black_clip(clip_path, brightness_threshold):
            try:
                os.remove(clip_path)
            except OSError:
                pass
            continue

        clips.append(
            {
                "path": clip_path,
                "filename": clip_filename,
                "start": seconds_to_hhmmss(start_sec),
                "end": seconds_to_hhmmss(end_sec),
                "duration": seconds_to_hhmmss(duration_sec),
                "timestamp_in_source": f"{seconds_to_hhmmss(start_sec)} - {seconds_to_hhmmss(end_sec)}",
            }
        )

        if progress_callback:
            progress_callback(i + 1, total, clip_filename)

    return clips


def extract_frames(clip_path: str, num_frames: int = 3) -> list[str]:
    """
    Extract evenly spaced frames from a clip as JPEG files.
    Returns list of temp image file paths.
    """
    import tempfile

    cap = cv2.VideoCapture(clip_path)
    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames == 0:
            return []

        num_frames = min(num_frames, total_frames)
        indices = [int(total_frames * i / num_frames) for i in range(num_frames)]

        frame_paths = []
        tmp_dir = tempfile.mkdtemp()

        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue
            frame_path = os.path.join(tmp_dir, f"frame_{idx:06d}.jpg")
            cv2.imwrite(frame_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            frame_paths.append(frame_path)

        if not frame_paths:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return frame_paths
    finally:
        cap.release()
