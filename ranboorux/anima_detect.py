"""Anima model detection for Forge Neo.

Provides standalone detection of Anima (2B DiT) models by inspecting
the loaded sd_model object. No dependency on ``modules.shared`` or
``scripts.ranbooru`` — purely parameter-based.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any, Optional

_ANIMA_WORD_PATTERN = re.compile(r"(?<![a-zA-Z0-9])anima(?![a-zA-Z0-9])", re.IGNORECASE)


@dataclass(frozen=True)
class ModelCapabilities:
    family: str  # "anima" | "sdxl" | "unknown"
    variant: str  # "base" | "aesthetic" | "turbo" | "2.9b" | "3.8b" | ""
    prompt_style: str  # "booru_tags"
    emits_score_tags: bool
    quality_prefix: str
    negative_default: str
    cfg_range: tuple[float, float]
    steps_range: tuple[int, int]
    detection_method: str = "none"


_NEGATIVE_DEFAULT = (
    "worst quality, low quality, score_1, score_2, score_3, "
    "artist name, blurry, jpeg artifacts, chromatic aberration"
)

# Variant delta table: variant -> (emits_score_tags, quality_prefix, cfg_range, steps_range)
_ANIMA_VARIANT_DELTAS: dict[str, tuple[bool, str, tuple[float, float], tuple[int, int]]] = {
    "aesthetic": (
        False,
        "masterpiece, best quality, safe, ",
        (3.0, 5.0),
        (30, 50),
    ),
    "turbo": (
        True,
        "masterpiece, best quality, score_7, safe, ",
        (1.0, 2.0),
        (8, 12),
    ),
    "2.9b": (
        True,
        "masterpiece, best quality, score_7, safe, ",
        (4.0, 5.0),
        (30, 50),
    ),
    "3.8b": (
        True,
        "masterpiece, best quality, score_7, safe, ",
        (4.0, 5.0),
        (30, 50),
    ),
    "base": (
        True,
        "masterpiece, best quality, score_7, safe, ",
        (4.0, 5.0),
        (30, 50),
    ),
}


def get_capabilities(
    family: str, variant: str, detection_method: str = "none"
) -> ModelCapabilities:
    """Return immutable ModelCapabilities record for a given family/variant."""
    if family == "anima":
        delta = _ANIMA_VARIANT_DELTAS.get(variant, _ANIMA_VARIANT_DELTAS["base"])
        emits_score_tags, quality_prefix, cfg_range, steps_range = delta
        return ModelCapabilities(
            family="anima",
            variant=variant if variant in _ANIMA_VARIANT_DELTAS else "base",
            prompt_style="booru_tags",
            emits_score_tags=emits_score_tags,
            quality_prefix=quality_prefix,
            negative_default=_NEGATIVE_DEFAULT,
            cfg_range=cfg_range,
            steps_range=steps_range,
            detection_method=detection_method,
        )
    return ModelCapabilities(
        family="unknown",
        variant="",
        prompt_style="booru_tags",
        emits_score_tags=False,
        quality_prefix="",
        negative_default="",
        cfg_range=(4.0, 8.0),
        steps_range=(20, 30),
        detection_method="none",
    )


def resolve_anima_variant(model_name: str) -> str:
    """Derive Anima variant from model/checkpoint name."""
    if not model_name:
        return "base"
    name = model_name.lower()
    if "aesthetic" in name:
        return "aesthetic"
    if "turbo" in name:
        return "turbo"
    if "2.9b" in name:
        return "2.9b"
    if "3.8b" in name:
        return "3.8b"
    return "base"


def _resolve_checkpoint_name(sd_model: Any) -> Optional[str]:
    """Return the checkpoint filename from *sd_model* if available."""
    if sd_model is None:
        return None
    if isinstance(sd_model, str):
        return sd_model
    # 1. Direct filename attribute (Forge engine standard)
    filename = getattr(sd_model, "filename", None)
    if filename is not None:
        return str(filename)
    # 2. CheckpointInfo object on Forge engine
    ckpt_info = getattr(sd_model, "sd_checkpoint_info", None)
    if ckpt_info is not None:
        for attr in ("filename", "name_for_extra", "name", "title"):
            val = getattr(ckpt_info, attr, None)
            if val is not None:
                return str(val)
    # 3. Legacy WebUI attributes
    for attr in ("sd_model_checkpoint", "checkpoint", "model_checkpoint"):
        value = getattr(sd_model, attr, None)
        if value is not None:
            return str(value)
    return None


def get_anima_model_info(sd_model: Any) -> dict[str, Any]:
    """Detect whether *sd_model* is an Anima model and return details.

    Detection ranking:
    1. Architecture config (``sd_model.model_config``)
    2. Dynamic dispatch flag (``dynamic_args.anima``)
    3. Engine class name (``type(sd_model).__name__``)
    4. Checkpoint filename regex (``sd_model.filename`` or legacy attrs)

    Returns a dict with keys:
    ``detected``: True if identified as Anima.
    ``method``: "model_config" / "dynamic_args" / "class_name" / "filename" / "none".
    ``model_name``: matched checkpoint filename or class name.
    ``variant``: "base" / "aesthetic" / "turbo" / "2.9b" / "3.8b" / "".
    ``capabilities``: frozen ModelCapabilities record.
    """
    if sd_model is None:
        caps = get_capabilities("unknown", "", "none")
        return {
            "detected": False,
            "method": "none",
            "model_name": "",
            "variant": "",
            "capabilities": caps,
        }

    # If a string was passed directly (e.g. checkpoint name)
    if isinstance(sd_model, str):
        if bool(_ANIMA_WORD_PATTERN.search(sd_model)):
            variant = resolve_anima_variant(sd_model)
            caps = get_capabilities("anima", variant, "filename")
            return {
                "detected": True,
                "method": "filename",
                "model_name": sd_model,
                "variant": variant,
                "capabilities": caps,
            }
        caps = get_capabilities("unknown", "", "none")
        return {
            "detected": False,
            "method": "none",
            "model_name": sd_model,
            "variant": "",
            "capabilities": caps,
        }

    # 1. Check model_config (Rank 1 - most robust architecture config)
    model_config = getattr(sd_model, "model_config", None)
    if model_config is not None:
        config_name = type(model_config).__name__
        hf_repo = str(getattr(model_config, "huggingface_repo", "") or "")
        if config_name == "Anima" or hf_repo == "circlestone-labs/Anima":
            model_name = _resolve_checkpoint_name(sd_model) or config_name
            variant = resolve_anima_variant(model_name)
            caps = get_capabilities("anima", variant, "model_config")
            return {
                "detected": True,
                "method": "model_config",
                "model_name": model_name,
                "variant": variant,
                "capabilities": caps,
            }

    # 2. Check dynamic_args.anima (Rank 2 - maintainer-sanctioned dispatch)
    dynamic_args = getattr(sd_model, "dynamic_args", None)
    if dynamic_args is None and "backend.args" in sys.modules:
        dynamic_args = getattr(sys.modules["backend.args"], "dynamic_args", None)
    if dynamic_args is not None and getattr(dynamic_args, "anima", False) is True:
        model_name = _resolve_checkpoint_name(sd_model) or "Anima"
        variant = resolve_anima_variant(model_name)
        caps = get_capabilities("anima", variant, "dynamic_args")
        return {
            "detected": True,
            "method": "dynamic_args",
            "model_name": model_name,
            "variant": variant,
            "capabilities": caps,
        }

    # 3. Check class name (Rank 3 - engine class e.g. class Anima)
    class_name = type(sd_model).__name__
    if class_name == "Anima" or bool(_ANIMA_WORD_PATTERN.search(class_name)):
        model_name = _resolve_checkpoint_name(sd_model) or class_name
        variant = resolve_anima_variant(model_name)
        caps = get_capabilities("anima", variant, "class_name")
        return {
            "detected": True,
            "method": "class_name",
            "model_name": model_name,
            "variant": variant,
            "capabilities": caps,
        }

    # 4. Check checkpoint filename (Rank 4 - filename regex)
    checkpoint = _resolve_checkpoint_name(sd_model)
    if checkpoint and bool(_ANIMA_WORD_PATTERN.search(checkpoint)):
        variant = resolve_anima_variant(checkpoint)
        caps = get_capabilities("anima", variant, "filename")
        return {
            "detected": True,
            "method": "filename",
            "model_name": checkpoint,
            "variant": variant,
            "capabilities": caps,
        }

    caps = get_capabilities("unknown", "", "none")
    return {
        "detected": False,
        "method": "none",
        "model_name": "",
        "variant": "",
        "capabilities": caps,
    }


def is_anima_model(sd_model: Any) -> bool:
    """Return ``True`` if *sd_model* is an Anima (2B DiT) model."""
    return bool(get_anima_model_info(sd_model)["detected"])
