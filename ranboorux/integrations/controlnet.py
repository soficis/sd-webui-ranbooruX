from __future__ import annotations

import importlib
import importlib.util
import os
from types import ModuleType
from typing import Any


def _load_module_from_path(module_name: str, module_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module spec from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_external_code(extension_root: str) -> Any:
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
            errors.append(f"{mod}: {exc}")

    try:
        env_root = os.environ.get("SD_FORGE_CONTROLNET_PATH") or os.environ.get("RANBOORUX_CN_PATH")
        if env_root:
            env_path = os.path.join(env_root, "lib_controlnet", "external_code.py")
            if os.path.isfile(env_path):
                return _load_module_from_path(
                    "sd_forge_controlnet.lib_controlnet.external_code",
                    env_path,
                )
            errors.append(f"env:{env_path}: not found")
    except Exception as exc:
        errors.append(f"env_load: {exc}")

    try:
        webui_root = None
        try:
            from modules import paths as webui_paths

            webui_root = getattr(webui_paths, "script_path", None)
        except Exception as exc:
            errors.append(f"modules.paths.script_path: {exc}")
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
            errors.append(f"builtin:{builtin_path}: not found")
    except Exception as exc:
        errors.append(f"builtin_load: {exc}")

    try:
        ext_path = os.path.join(
            extension_root, "sd_forge_controlnet", "lib_controlnet", "external_code.py"
        )
        if os.path.isfile(ext_path):
            return _load_module_from_path(
                "sd_forge_controlnet.lib_controlnet.external_code",
                ext_path,
            )
        errors.append(f"file://{ext_path}: not found")
    except Exception as exc:
        errors.append(f"file_fallback: {exc}")

    raise ImportError("Unable to import ControlNet external_code. Attempts: " + "; ".join(errors))
