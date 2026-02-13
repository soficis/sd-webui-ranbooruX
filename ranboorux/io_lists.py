from __future__ import annotations

import os
import re
import tempfile
from typing import Callable, Iterable, List, Optional

NormalizeFn = Optional[Callable[[str], str]]


def ensure_user_file(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.isfile(path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("")


def read_list_file(path: str, normalize_tag: NormalizeFn = None) -> List[str]:
    ensure_user_file(path)
    with open(path, "r", encoding="utf-8") as handle:
        contents = handle.read()
    if not contents:
        return []
    contents = contents.replace("\r\n", "\n").replace("\r", "\n")
    parts = [segment.strip() for segment in re.split(r"[\n,]+", contents) if segment.strip()]
    seen = set()
    ordered: List[str] = []
    for part in parts:
        key = normalize_tag(part) if callable(normalize_tag) else part.casefold()
        key = key or part.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(part)
    return ordered


def write_list_file(path: str, tags: Iterable[str], normalize_tag: NormalizeFn = None) -> None:
    ensure_user_file(path)
    seen = set()
    deduped: List[str] = []
    for tag in tags:
        cleaned = (tag or "").strip()
        if not cleaned:
            continue
        key = normalize_tag(cleaned) if callable(normalize_tag) else cleaned.casefold()
        key = key or cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
    parent_dir = os.path.dirname(path)
    payload = "\n".join(deduped)
    temp_path = None
    try:
        os.makedirs(parent_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=parent_dir,
            delete=False,
            prefix=".ranboorux_",
            suffix=".tmp",
        ) as handle:
            handle.write(payload)
            temp_path = handle.name
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.isfile(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
