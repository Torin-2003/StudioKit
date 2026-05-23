import json
import hashlib
import os
from datetime import datetime
from pathlib import Path

PROCESSED_LOG_FILENAME = "processed_log.json"


def compute_file_hash(filepath: str, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def load_processed_log(output_dir: str) -> dict:
    log_path = Path(output_dir) / PROCESSED_LOG_FILENAME
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"processed_videos": []}


def save_processed_log(output_dir: str, log: dict) -> None:
    log_path = Path(output_dir) / PROCESSED_LOG_FILENAME
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def is_already_processed(output_dir: str, file_hash: str) -> dict | None:
    log = load_processed_log(output_dir)
    for entry in log["processed_videos"]:
        if entry["file_hash"] == file_hash:
            return entry
    return None


def register_processed_video(
    output_dir: str,
    filename: str,
    file_hash: str,
    clips_generated: int,
    folders_affected: list[str],
) -> None:
    log = load_processed_log(output_dir)
    log["processed_videos"].append(
        {
            "filename": filename,
            "file_hash": file_hash,
            "processed_at": datetime.utcnow().isoformat(),
            "clips_generated": clips_generated,
            "folders_affected": folders_affected,
        }
    )
    save_processed_log(output_dir, log)


def load_folder_metadata(folder_path: str) -> dict:
    meta_path = Path(folder_path) / "metadata.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    folder_name = Path(folder_path).name
    return {
        "folder_name": folder_name,
        "category_description": "",
        "clips": [],
    }


def save_folder_metadata(folder_path: str, metadata: dict) -> None:
    meta_path = Path(folder_path) / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def add_clip_to_metadata(
    folder_path: str,
    filename: str,
    source_video: str,
    duration: str,
    timestamp_in_source: str,
    description: str,
    tags: list[str],
) -> None:
    metadata = load_folder_metadata(folder_path)
    metadata["clips"].append(
        {
            "filename": filename,
            "source_video": source_video,
            "duration": duration,
            "timestamp_in_source": timestamp_in_source,
            "description": description,
            "tags": tags,
            "analyzed_at": datetime.utcnow().isoformat(),
        }
    )
    save_folder_metadata(folder_path, metadata)


def list_existing_folders(output_dir: str) -> list[dict]:
    """Return existing category folders with their descriptions."""
    result = []
    output_path = Path(output_dir)
    if not output_path.exists():
        return result
    for item in output_path.iterdir():
        if item.is_dir():
            meta_path = item / "metadata.json"
            if meta_path.exists():
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                result.append(
                    {
                        "folder_name": item.name,
                        "category_description": meta.get("category_description", ""),
                        "content_type": meta.get("content_type", ""),
                    }
                )
    return result


def next_clip_index(folder_path: str) -> int:
    metadata = load_folder_metadata(folder_path)
    if not metadata["clips"]:
        return 1
    import re
    indices = []
    for c in metadata["clips"]:
        m = re.search(r"_(\d+)\.mp4$", c.get("filename", ""))
        if m:
            indices.append(int(m.group(1)))
    return max(indices) + 1 if indices else len(metadata["clips"]) + 1


def remove_clip_from_metadata(folder_path: str, filename: str) -> None:
    metadata = load_folder_metadata(folder_path)
    metadata["clips"] = [c for c in metadata["clips"] if c["filename"] != filename]
    save_folder_metadata(folder_path, metadata)


def update_clip_in_metadata(folder_path: str, filename: str, description: str, tags: list[str]) -> None:
    metadata = load_folder_metadata(folder_path)
    for clip in metadata["clips"]:
        if clip["filename"] == filename:
            clip["description"] = description
            clip["tags"] = tags
            clip["analyzed_at"] = datetime.utcnow().isoformat()
            break
    save_folder_metadata(folder_path, metadata)
