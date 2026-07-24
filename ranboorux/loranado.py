from __future__ import annotations

import os
import random
from typing import Iterable, List, Optional, Tuple


def normalize_lora_name(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    # Strip extension and return lowercase
    return os.path.splitext(text)[0].strip().lower()


def parse_custom_weights(weights_str: Optional[str]) -> List[float]:
    if not weights_str:
        return []
    try:
        return [float(weight.strip()) for weight in weights_str.split(",")]
    except ValueError:
        return []


def filter_candidates(
    candidates: Iterable[str], enabled_loras: Iterable[str], blacklist_loras: Iterable[str]
) -> List[str]:
    """
    Filters candidates based on enabled selections and blacklists.
    All inputs and filters are normalized prior to matching.
    """
    enabled_selection = {
        normalize_lora_name(name) for name in enabled_loras if normalize_lora_name(name)
    }
    blacklist_selection = {
        normalize_lora_name(name) for name in blacklist_loras if normalize_lora_name(name)
    }

    # 1. Filter enabled candidates if any are selected
    filtered = list(candidates)
    if enabled_selection:
        filtered = [c for c in filtered if normalize_lora_name(c) in enabled_selection]

    # 2. Filter blacklist candidates
    if blacklist_selection:
        filtered = [c for c in filtered if normalize_lora_name(c) not in blacklist_selection]

    return filtered


def select_loras(
    candidates: List[str],
    amount: int,
    lora_min: float,
    lora_max: float,
    custom_weights: Optional[List[float]] = None,
    random_source=None,
) -> List[Tuple[str, float]]:
    """
    Selects the requested amount of LoRAs and assigns weights.
    Uses the provided random_source (e.g. random.Random(seed)) for deterministic results.
    """
    if not candidates:
        return []

    rng = random_source if random_source is not None else random

    num_to_select = min(max(1, int(amount)), len(candidates))
    chosen_files = rng.sample(candidates, num_to_select)

    weights = custom_weights if custom_weights is not None else []

    selected: List[Tuple[str, float]] = []
    for i in range(num_to_select):
        chosen_file = chosen_files[i]
        lora_name = os.path.splitext(chosen_file)[0]

        # Use custom weight if available, otherwise draw randomly
        if i < len(weights):
            weight = weights[i]
        else:
            weight = round(rng.uniform(lora_min, lora_max), 2)

        selected.append((lora_name, weight))

    return selected


def format_lora_prompt(selected_loras: Iterable[Tuple[str, float]]) -> str:
    fragments = [f"<lora:{name}:{weight}>" for name, weight in selected_loras]
    return " ".join(fragments)
