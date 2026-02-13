from __future__ import annotations

from typing import Iterable, List


def split_prompt_tags(prompt: str) -> List[str]:
    if not isinstance(prompt, str):
        return []
    return [tag.strip() for tag in prompt.split(",") if tag.strip()]


def dedupe_keep_order(tags: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(tags))


def remove_repeated_tags(prompt: str) -> str:
    tags = split_prompt_tags(prompt)
    if not tags:
        return ""
    return ",".join(dedupe_keep_order(tags))


def limit_prompt_tags(prompt: str, limit_val, mode: str) -> str:
    tags = split_prompt_tags(prompt)
    if not tags:
        return ""
    if mode == "Limit":
        try:
            pct = float(limit_val)
        except Exception:
            return prompt
        if pct <= 0:
            return ""
        max_count = max(1, int(len(tags) * pct))
        return ",".join(tags[:max_count])
    if mode == "Max":
        try:
            max_count = int(limit_val)
        except Exception:
            return prompt
        if max_count <= 0:
            return prompt
        return ",".join(tags[:max_count])
    return prompt
