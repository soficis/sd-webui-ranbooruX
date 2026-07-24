from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Union

PathLike = Union[str, Path]
NormalizeFn = Optional[Callable[[str], str]]


class UserStoreError(RuntimeError):
    """Raised when RanbooruX user-data storage cannot complete an operation."""


def sanitize_credential(value: object) -> str:
    if value is None:
        return ""
    text = "".join(char for char in str(value) if char.isprintable()).strip().strip('"').strip("'")
    if not text:
        return ""
    text = text.replace("%26", "&").replace("%3D", "=").replace("%3d", "=")
    lower = text.lower()
    if "api_key=" in lower or "user_id=" in lower or "&" in text:
        for segment in text.split("&"):
            segment_lower = segment.lower().strip()
            if segment_lower.startswith("api_key=") or segment_lower.startswith("user_id="):
                return segment.split("=", 1)[1].strip()
        text = text.split("&", 1)[0].strip()
    for prefix in ("api_key=", "user_id="):
        if text.lower().startswith(prefix):
            text = text[len(prefix) :].strip()
    return text


def atomic_write_text(file_path: PathLike, content: str) -> None:
    target = Path(file_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path_value = tempfile.mkstemp(
            dir=target.parent,
            prefix=".ranboorux_",
            suffix=".tmp",
        )
    except OSError as exc:
        raise UserStoreError(f"Could not prepare atomic write for {target}: {exc}") from exc

    temp_path = Path(temp_path_value)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        temp_path.replace(target)
    except Exception as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError as cleanup_exc:
            raise UserStoreError(
                f"Could not write {target}; cleanup also failed: {cleanup_exc}"
            ) from exc
        raise UserStoreError(f"Could not write {target}: {exc}") from exc


def ensure_text_file(file_path: PathLike) -> None:
    target = Path(file_path)
    if target.is_file():
        return
    atomic_write_text(target, "")


def load_gelbooru_credentials(file_path: PathLike) -> Optional[Dict[str, str]]:
    target = Path(file_path)
    if not target.is_file():
        return None
    try:
        with target.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise UserStoreError(f"Invalid Gelbooru credentials JSON in {target}") from exc
    except OSError as exc:
        raise UserStoreError(f"Could not read Gelbooru credentials from {target}: {exc}") from exc

    if not isinstance(data, Mapping):
        return None
    api_key = sanitize_credential(data.get("api_key"))
    user_id = sanitize_credential(data.get("user_id"))
    if api_key and user_id:
        return {"api_key": api_key, "user_id": user_id}
    return None


def save_gelbooru_credentials(file_path: PathLike, api_key: object, user_id: object) -> None:
    sanitized_api_key = sanitize_credential(api_key)
    sanitized_user_id = sanitize_credential(user_id)
    if not sanitized_api_key or not sanitized_user_id:
        raise ValueError("Both Gelbooru API key and user ID are required")
    content = json.dumps(
        {"api_key": sanitized_api_key, "user_id": sanitized_user_id},
        ensure_ascii=False,
        indent=2,
    )
    atomic_write_text(file_path, content)


def clear_gelbooru_credentials(file_path: PathLike) -> None:
    target = Path(file_path)
    try:
        if target.is_file():
            target.unlink()
    except OSError as exc:
        raise UserStoreError(f"Could not remove Gelbooru credentials at {target}: {exc}") from exc


def read_list_file(file_path: PathLike, normalize_fn: NormalizeFn = None) -> List[str]:
    target = Path(file_path)
    if not target.is_file():
        return []
    try:
        contents = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise UserStoreError(f"Could not read list file {target}: {exc}") from exc

    contents = contents.replace("\r\n", "\n").replace("\r", "\n")
    parts = [segment.strip() for segment in re.split(r"[\n,]+", contents) if segment.strip()]
    seen: set[str] = set()
    ordered: List[str] = []
    for part in parts:
        key = normalize_fn(part) if callable(normalize_fn) else part.casefold()
        key = key or part.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(part)
    return ordered


def write_list_file(
    file_path: PathLike, tags: Iterable[object], normalize_fn: NormalizeFn = None
) -> None:
    seen: set[str] = set()
    deduped: List[str] = []
    for tag in tags:
        cleaned = (str(tag) if tag is not None else "").strip()
        if not cleaned:
            continue
        key = normalize_fn(cleaned) if callable(normalize_fn) else cleaned.casefold()
        key = key or cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
    atomic_write_text(file_path, "\n".join(deduped))


def append_prompt_log(file_path: PathLike, payload: Mapping[str, object]) -> None:
    target = Path(file_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(dict(payload), ensure_ascii=False))
            handle.write("\n")
    except OSError as exc:
        raise UserStoreError(f"Could not append prompt log {target}: {exc}") from exc


def append_text_log(file_path: PathLike, lines: Iterable[str]) -> None:
    target = Path(file_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            for line in lines:
                handle.write(str(line))
                if not str(line).endswith("\n"):
                    handle.write("\n")
    except OSError as exc:
        raise UserStoreError(f"Could not append text log {target}: {exc}") from exc


def load_catalog_preferences(file_path: PathLike) -> Dict[str, object]:
    defaults: Dict[str, object] = {"enabled": True, "source": "bundled", "custom_path": ""}
    target = Path(file_path)
    if not target.is_file():
        return dict(defaults)
    try:
        with target.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise UserStoreError(f"Invalid catalog preference JSON in {target}") from exc
    except OSError as exc:
        raise UserStoreError(f"Could not read catalog preferences from {target}: {exc}") from exc

    if not isinstance(data, Mapping):
        return dict(defaults)
    source = data.get("source", "bundled")
    source_text = source.strip().lower() if isinstance(source, str) else "bundled"
    if source_text not in ("bundled", "custom"):
        source_text = "bundled"
    custom_path = data.get("custom_path", "")
    return {
        "enabled": bool(data.get("enabled", True)),
        "source": source_text,
        "custom_path": custom_path.strip() if isinstance(custom_path, str) else "",
    }


def save_catalog_preferences(
    file_path: PathLike,
    *,
    enabled: bool,
    source: str,
    custom_path: object,
) -> None:
    source_text = source if source in ("bundled", "custom") else "bundled"
    payload = {
        "enabled": bool(enabled),
        "source": source_text,
        "custom_path": str(custom_path).strip() if custom_path is not None else "",
    }
    atomic_write_text(file_path, json.dumps(payload, ensure_ascii=False, indent=2))
