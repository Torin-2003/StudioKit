import os
import shutil
import json
from pathlib import Path
from openai import OpenAI
from metadata import (
    list_existing_folders,
    load_folder_metadata,
    save_folder_metadata,
    add_clip_to_metadata,
    next_clip_index,
)


def resolve_target_folder(
    client: OpenAI,
    output_dir: str,
    suggested_category: str,
    category_description: str,
    granularity: str = "medium",
    model: str = "gpt-4o",
    topic: str = "",
    analysis_content_type: str = "",
) -> str:
    """
    Decide which existing folder to place a clip in, or create a new one.
    Uses GPT to avoid creating near-duplicate folders.
    Returns the resolved folder name (not full path).
    """
    existing = list_existing_folders(output_dir)

    if not existing:
        return suggested_category

    # Hard filter: only consider folders with matching content_type (if known)
    # This prevents interview clips from ever merging into gameplay folders
    clip_content_type = analysis_content_type or ""
    same_type = [e for e in existing if e.get("content_type", "") == clip_content_type] if clip_content_type else []
    if clip_content_type and same_type:
        candidate_folders = same_type
    else:
        candidate_folders = existing

    existing_summary = "\n".join(
        f'- "{e["folder_name"]}": {e["category_description"]}' for e in candidate_folders
    )

    granularity_rule = {
        "coarse": (
            "Be very aggressive about merging. If the new clip is even loosely related to an existing folder "
            "(same sport, same player, same type of action), ALWAYS use the existing folder. "
            "Only create a new folder if there is truly no overlap at all."
        ),
        "medium": (
            "Merge if the new clip and an existing folder share the same core action AND subject. "
            "Treat near-synonyms as identical: 'goal_celebration' and 'argentina_goal_celebration' are the SAME — use the existing one. "
            "'soccer' and 'football' are the SAME sport — merge them. "
            "Create a new folder only if no existing folder covers this action type."
        ),
        "fine": (
            "Create new folders when the subject or context differs noticeably. "
            "Still merge exact duplicates."
        ),
    }.get(granularity, "")

    topic_line = f"Library topic: '{topic}'. Category names should use terminology relevant to this topic.\n" if topic else ""

    content_type_line = f"This clip's content type: '{clip_content_type}'.\n" if clip_content_type else ""
    scope_note = (
        "All folders listed below are already pre-filtered to the same content type as this clip. "
        "Focus only on whether the specific action/subject matches closely enough to merge.\n"
        if clip_content_type and same_type
        else ""
    )

    prompt = (
        f"You are managing a structured video clip library. "
        f"A new clip needs to be placed in the correct folder.\n"
        f"{topic_line}"
        f"{content_type_line}"
        f"New clip suggested category: '{suggested_category}'\n"
        f"New clip category description: '{category_description}'\n\n"
        f"Existing folders (candidates):\n{existing_summary}\n\n"
        f"{scope_note}"
        f"Merging rule ({granularity}): {granularity_rule}\n\n"
        f"Synonyms that CAN be merged: 'soccer'/'football' (same sport), "
        f"country-prefixed vs generic names for the SAME action type.\n\n"
        f"Respond ONLY with valid JSON:\n"
        f'{{"action": "use_existing" | "create_new", "folder_name": "snake_case_name"}}\n'
        f"If use_existing, folder_name must exactly match one of the existing folder names.\n"
        f"If create_new, provide the new folder name in snake_case.\n"
        f"Do not include any text outside the JSON."
    )

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=100,
        temperature=0.1,
    )

    raw = response.choices[0].message.content.strip()

    try:
        result = json.loads(raw)
        return result["folder_name"]
    except (json.JSONDecodeError, KeyError):
        import re
        match = re.search(r'"folder_name"\s*:\s*"([^"]+)"', raw)
        if match:
            return match.group(1)
        return suggested_category


def place_clip(
    output_dir: str,
    clip_info: dict,
    analysis: dict,
    folder_name: str,
    source_video_name: str,
) -> str:
    """
    Move a raw clip into its target folder with a proper sequential name.
    Updates the folder's metadata.json.
    Returns the final clip path.
    """
    folder_path = Path(output_dir) / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)

    # Initialize folder metadata if new
    meta_path = folder_path / "metadata.json"
    if not meta_path.exists():
        save_folder_metadata(
            str(folder_path),
            {
                "folder_name": folder_name,
                "category_description": analysis.get("category_description", ""),
                "content_type": analysis.get("content_type", ""),
                "clips": [],
            },
        )

    src_path = clip_info["path"]
    if not Path(src_path).exists():
        raise FileNotFoundError(f"Clip file not found: {src_path}")

    idx = next_clip_index(str(folder_path))
    final_filename = f"{folder_name}_{idx:03d}.mp4"
    final_path = folder_path / final_filename

    shutil.move(src_path, str(final_path))

    add_clip_to_metadata(
        folder_path=str(folder_path),
        filename=final_filename,
        source_video=source_video_name,
        duration=clip_info["duration"],
        timestamp_in_source=clip_info["timestamp_in_source"],
        description=analysis.get("description", ""),
        tags=analysis.get("tags", []),
    )

    return str(final_path)


def cleanup_raw_clip(clip_path: str) -> None:
    try:
        os.remove(clip_path)
    except OSError:
        pass
