"""UI helpers for pure data conversions and list operations."""

from pathlib import Path
from typing import Optional, Sequence, Tuple


def upload_to_path(uploaded: object) -> str:
    """Accepts str, pathlib.Path, dict with name/path/orig_name, or an object with .name attribute."""
    if isinstance(uploaded, str):
        return uploaded
    if isinstance(uploaded, Path):
        return str(uploaded)
    if isinstance(uploaded, dict):
        for key in ("name", "path", "orig_name"):
            val = uploaded.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return ""
    if hasattr(uploaded, "name"):
        name_val = getattr(uploaded, "name")
        if isinstance(name_val, str) and name_val.strip():
            return name_val.strip()
    return ""


def read_uploaded_text(path: str, max_bytes: int = 1_048_576) -> Tuple[str, Optional[str]]:
    """Reads uploaded text file with utf-8-sig encoding and error replacement.

    Returns (text, error).
    """
    if not path or not path.strip():
        return "", "No file path provided"
    p = Path(path)
    try:
        if not p.is_file():
            return "", f"File not found: {p.name}"
        size = p.stat().st_size
        if size > max_bytes:
            return "", f"File too large ({size} bytes, limit {max_bytes} bytes)"
        content = p.read_text(encoding="utf-8-sig", errors="replace")
        return content, None
    except OSError as exc:
        return "", f"Error reading file: {exc}"


def next_rating(current: Optional[str], available: Sequence[str]) -> str:
    """Implements rating fallback logic (D2).

    Keep the current rating if the new booru offers it.
    Otherwise map Sensitive -> Safe (if available), and anything else missing -> 'All'.
    """
    if current and current in available:
        return current
    if current == "Sensitive" and "Safe" in available:
        return "Safe"
    if "All" in available:
        return "All"
    return available[0] if available else "All"


def format_list_status(
    op: str,
    *,
    added: int = 0,
    skipped: int = 0,
    removed: int = 0,
    filename: str = "",
    error: Optional[str] = None,
) -> str:
    """Format status messages for list operations."""
    if error:
        return f"Failed to import: {error}"
    if op == "add":
        if added > 0:
            noun = "tag" if added == 1 else "tags"
            if skipped > 0:
                return f"Added {added} {noun} ({skipped} already present)."
            return f"Added {added} {noun}."
        if skipped > 0:
            return f"No new tags added ({skipped} already present)."
        return "No tags added."
    if op == "remove":
        if removed > 0:
            noun = "tag" if removed == 1 else "tags"
            return f"Removed {removed} {noun}."
        return "Nothing selected."
    if op == "dedupe":
        if removed > 0:
            noun = "duplicate" if removed == 1 else "duplicates"
            return f"Removed {removed} {noun}."
        return "No duplicates found."
    if op == "import":
        fn = filename or "file"
        if added > 0:
            noun = "tag" if added == 1 else "tags"
            if skipped > 0:
                return f"Imported {added} {noun} from {fn} ({skipped} already present)."
            return f"Imported {added} {noun} from {fn}."
        if skipped > 0:
            return f"No new tags imported from {fn} ({skipped} already present)."
        return f"No tags found to import from {fn}."
    return ""


def get_filter_preset_values(preset_name: str) -> Tuple[Tuple[bool, ...], str]:
    """Returns an 11-tuple of booleans and a status message for filter presets.

    The 11 booleans correspond in order to:
    (remove_bad_tags, remove_text_tags, remove_artist_tags, remove_character_tags,
     remove_series_tags, remove_clothing_tags, remove_furry_tags, remove_headwear_tags,
     remove_girl_suffix_tags, preserve_hair_eye_colors, restrict_subject_tags)
    """
    if preset_name == "Quick Strip":
        values = (True,) * 11
    elif preset_name == "Strip Series/Character":
        values = (True, True, True, True, True, False, False, False, False, False, False)
    elif preset_name == "Preserve Base Colors":
        values = (True, True, False, False, False, False, False, False, False, True, False)
    elif preset_name == "Reset to defaults":
        values = (True, True, False, False, False, False, False, False, False, False, False)
    else:
        values = (False,) * 11

    count = sum(1 for v in values if v)
    noun = "filter" if count == 1 else "filters"
    msg = f"Applied preset: {preset_name}, {count} {noun} on"
    return values, msg
