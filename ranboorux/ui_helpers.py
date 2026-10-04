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
