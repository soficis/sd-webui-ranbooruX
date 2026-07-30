"""Anima model detection for Forge Neo.

Provides standalone detection of Anima (2B DiT) models by inspecting
the loaded sd_model object.  No dependency on ``modules.shared`` or
``scripts.ranbooru`` — purely parameter-based.
"""

from __future__ import annotations

from typing import Any, Optional


def _resolve_checkpoint_name(sd_model: Any) -> Optional[str]:
    """Return the checkpoint filename from *sd_model* if available."""
    for attr in ("sd_model_checkpoint", "checkpoint", "model_checkpoint"):
        value = getattr(sd_model, attr, None)
        if value is not None:
            return str(value)
    return None


def get_anima_model_info(sd_model: Any) -> dict[str, Any]:
    """Detect whether *sd_model* is an Anima model and return details.

    Returns a dict with keys:

    ``detected``
        ``True`` if the model is identified as Anima.
    ``method``
        ``"filename"`` / ``"class_name"`` / ``"none"``.
    ``model_name``
        The matched checkpoint filename or class name, or ``""``.
    """
    if sd_model is None:
        return {"detected": False, "method": "none", "model_name": ""}

    # PRIMARY: checkpoint filename contains "anima" (case-insensitive)
    checkpoint = _resolve_checkpoint_name(sd_model)
    if checkpoint:
        if "anima" in checkpoint.lower():
            return {
                "detected": True,
                "method": "filename",
                "model_name": checkpoint,
            }

    # SECONDARY: class name contains "Anima"
    class_name = type(sd_model).__name__
    if "Anima" in class_name:
        return {
            "detected": True,
            "method": "class_name",
            "model_name": class_name,
        }

    return {"detected": False, "method": "none", "model_name": ""}


def is_anima_model(sd_model: Any) -> bool:
    """Return ``True`` if *sd_model* is an Anima (2B DiT) model.

    Detection order (whichever matches first wins):

    1. Checkpoint filename containing "anima" (case-insensitive).
    2. Class name containing ``"Anima"`` (e.g. ``class Anima(ForgeDiffusionEngine)``).

    Returns ``False`` for ``None`` input or when no signal is found.
    """
    return bool(get_anima_model_info(sd_model)["detected"])
