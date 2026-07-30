from __future__ import annotations

from typing import Any, List, Sequence


def repeat_to_length(values: Any, length: int) -> List[Any]:
    if length <= 0:
        return []
    if not isinstance(values, list):
        return [values] * length
    if not values:
        return [None] * length
    if len(values) == length:
        return list(values)
    return values * (length // len(values)) + values[: length % len(values)]


def replace_processed_results(
    processed: object,
    *,
    images: Sequence[Any],
    prompts: Sequence[Any],
    negative_prompts: Sequence[Any],
    infotexts: Sequence[Any],
    seed: int,
    subseed: int,
    width: int,
    height: int,
) -> None:
    image_list = list(images)
    prompt_list = list(prompts)
    negative_list = list(negative_prompts)
    infotext_list = list(infotexts)

    _replace_list_attr(processed, "images", image_list)
    prompt_value = prompt_list if len(prompt_list) > 1 else (prompt_list[0] if prompt_list else "")
    negative_value = (
        negative_list if len(negative_list) > 1 else (negative_list[0] if negative_list else "")
    )
    setattr(processed, "prompt", prompt_value)
    setattr(
        processed,
        "negative_prompt",
        negative_value,
    )
    _replace_list_attr(processed, "infotexts", infotext_list)
    setattr(processed, "seed", seed)
    setattr(processed, "subseed", subseed)
    setattr(processed, "width", width)
    setattr(processed, "height", height)

    _replace_list_attr(processed, "all_prompts", prompt_list)
    _replace_list_attr(processed, "all_negative_prompts", negative_list)
    _replace_list_attr(processed, "all_seeds", [seed + i for i in range(len(image_list))])
    _replace_list_attr(processed, "all_subseeds", [subseed + i for i in range(len(image_list))])

    for attr_name in ("cached_images", "images_list", "output_images", "_cached_images"):
        if hasattr(processed, attr_name):
            current = getattr(processed, attr_name)
            if isinstance(current, list):
                current.clear()
                current.extend(image_list)
            else:
                setattr(processed, attr_name, list(image_list))


def _replace_list_attr(target: object, attr_name: str, values: Sequence[Any]) -> None:
    current = getattr(target, attr_name, None)
    if isinstance(current, list):
        current.clear()
        current.extend(values)
    else:
        setattr(target, attr_name, list(values))
