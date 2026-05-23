import base64
import os
from openai import OpenAI


def _encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def analyze_clip_frames(
    client: OpenAI,
    frame_paths: list[str],
    source_video_name: str,
    timestamp: str,
    granularity: str = "medium",
    model: str = "gpt-4o",
    topic: str = "",
) -> dict:
    """
    Send frames to GPT-4V and get back a structured analysis.
    granularity: "coarse" | "medium" | "fine"
    Returns dict with: description, tags, suggested_category, category_description
    """
    granularity_instruction = {
        "coarse": (
            "Use broad, general category names (e.g., 'dribbling', 'goal', 'celebration'). "
            "Avoid overly specific distinctions."
        ),
        "medium": (
            "Use moderately specific category names that capture the main action and subject "
            "(e.g., 'messi_dribbling', 'ronaldo_free_kick'). Balance specificity with reusability."
        ),
        "fine": (
            "Use highly specific category names capturing subject, action, context, and position "
            "(e.g., 'messi_left_wing_1v2_dribbling', 'ronaldo_penalty_kick_celebration'). "
            "Prefer precision over grouping."
        ),
    }.get(granularity, "")

    image_content = []
    for path in frame_paths:
        b64 = _encode_image(path)
        image_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}",
                    "detail": "low",
                },
            }
        )

    topic_line = f"Library topic: '{topic}'. Use topic-specific terminology for category names.\n" if topic else ""

    image_content.append(
        {
            "type": "text",
            "text": (
                f"These frames are from a video clip. Source file: '{source_video_name}', "
                f"timestamp: {timestamp}.\n"
                f"{topic_line}\n"
                "Analyze the content carefully and respond ONLY with valid JSON in this exact format:\n"
                "{\n"
                '  "content_type": "one of: gameplay | interview | celebration | analysis | highlight | other",\n'
                '  "description": "One or two sentences describing what is happening in this clip.",\n'
                '  "tags": ["tag1", "tag2", "tag3"],\n'
                '  "suggested_category": "snake_case_folder_name",\n'
                '  "category_description": "Short description of what this category contains."\n'
                "}\n\n"
                "content_type definitions (pick exactly one):\n"
                "- gameplay: actual match/game action (dribbling, goals, tackles, passes during play)\n"
                "- interview: someone talking to camera, press conference, Q&A, talking head\n"
                "- celebration: post-goal or post-win celebrations, reactions\n"
                "- analysis: studio discussion, tactical breakdown, commentary panel\n"
                "- highlight: montage or compilation clips\n"
                "- other: anything that doesn't fit above\n\n"
                f"Category naming guidance: {granularity_instruction}\n\n"
                "CRITICAL RULE for suggested_category:\n"
                "- For interview/analysis/other: the category name MUST contain the content_type word "
                "(e.g. 'messi_interview', 'player_press_conference', 'tactical_analysis').\n"
                "- NEVER name a non-gameplay clip with a gameplay action word "
                "(e.g. NEVER 'messi_dribbling' for an interview clip).\n"
                "- For gameplay: name by the specific action (e.g. 'messi_dribbling', 'nfl_touchdown').\n"
                "Use snake_case for suggested_category. Do not include any text outside the JSON."
            ),
        }
    )

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": image_content}],
        max_tokens=400,
        temperature=0.2,
    )

    raw = response.choices[0].message.content.strip()

    import json
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            result = json.loads(match.group())
        else:
            result = {
                "description": raw,
                "tags": [],
                "suggested_category": "uncategorized",
                "category_description": "Clips that could not be automatically categorized.",
                "content_type": "other",
            }

    return result


def cleanup_frames(frame_paths: list[str]) -> None:
    for path in frame_paths:
        try:
            os.remove(path)
        except OSError:
            pass
    if frame_paths:
        import shutil
        try:
            shutil.rmtree(os.path.dirname(frame_paths[0]), ignore_errors=True)
        except Exception:
            pass
