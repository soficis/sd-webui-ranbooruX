from __future__ import annotations

import importlib
import importlib.util
import logging
import os
from types import ModuleType

from ranboorux.requesting import sanitize_exception_text

logger = logging.getLogger("ranboorux")


def _load_module_from_path(module_name: str, module_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError("Unable to load module spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_external_code(extension_root: str) -> ModuleType:
    candidates = [
        "sd_forge_controlnet.lib_controlnet.external_code",
        "extensions.sd_forge_controlnet.lib_controlnet.external_code",
        "extensions.sd-webui-controlnet.scripts.external_code",
    ]
    errors = []
    for mod in candidates:
        try:
            return importlib.import_module(mod)
        except Exception as exc:
            errors.append(f"{mod}: {exc.__class__.__name__}")
            logger.debug(f"ControlNet candidate {mod} failed: {sanitize_exception_text(str(exc))}")

    try:
        env_root = os.environ.get("SD_FORGE_CONTROLNET_PATH") or os.environ.get("RANBOORUX_CN_PATH")
        if env_root:
            env_path = os.path.join(env_root, "lib_controlnet", "external_code.py")
            if os.path.isfile(env_path):
                return _load_module_from_path(
                    "sd_forge_controlnet.lib_controlnet.external_code",
                    env_path,
                )
            errors.append("env: configured ControlNet external_code.py not found")
    except Exception as exc:
        errors.append(f"env_load: {exc.__class__.__name__}")

    try:
        webui_root = None
        try:
            from modules import paths as webui_paths

            webui_root = getattr(webui_paths, "script_path", None)
            if not webui_root:
                errors.append("modules.paths.script_path unavailable")
        except Exception as exc:
            errors.append("modules.paths.script_path unavailable")
            logger.debug(f"modules.paths.script_path failed: {sanitize_exception_text(str(exc))}")
        if webui_root:
            builtin_path = os.path.join(
                webui_root,
                "extensions-builtin",
                "sd_forge_controlnet",
                "lib_controlnet",
                "external_code.py",
            )
            if os.path.isfile(builtin_path):
                return _load_module_from_path(
                    "sd_forge_controlnet.lib_controlnet.external_code",
                    builtin_path,
                )
            errors.append("builtin: ControlNet external_code.py not found")
    except Exception as exc:
        errors.append(f"builtin_load: {exc.__class__.__name__}")

    try:
        ext_path = os.path.join(
            extension_root, "sd_forge_controlnet", "lib_controlnet", "external_code.py"
        )
        if os.path.isfile(ext_path):
            return _load_module_from_path(
                "sd_forge_controlnet.lib_controlnet.external_code",
                ext_path,
            )
        errors.append("extension: bundled ControlNet external_code.py not found")
    except Exception as exc:
        errors.append(f"extension_load: {exc.__class__.__name__}")

    raise ImportError("Unable to import ControlNet external_code. Attempts: " + "; ".join(errors))
