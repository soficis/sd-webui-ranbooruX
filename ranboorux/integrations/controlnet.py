from __future__ import annotations

import importlib.util
import logging
import os
from types import ModuleType

from ranboorux.http_client import sanitize_exception_text
from ranboorux.safe_paths import safe_join

logger = logging.getLogger("ranboorux")


_CN_SUFFIX = ("lib_controlnet", "external_code.py")


def _resolve_env_controlnet_file(env_root: str, extension_root: str) -> str | None:
    """Return the first existing external_code.py for an env-configured ControlNet root.

    Relative values keep their historical meaning (relative to the process CWD, which
    is the WebUI root), then fall back to WebUI ``script_path`` and the extension root.
    """
    if os.path.isabs(env_root):
        bases = [os.path.abspath(env_root)]
    else:
        roots = [os.getcwd()]
        try:
            from modules import paths as webui_paths

            webui_root = getattr(webui_paths, "script_path", None)
            if webui_root:
                roots.append(webui_root)
        except Exception:
            pass
        roots.append(extension_root)
        bases = []
        for root in roots:
            try:
                bases.append(str(safe_join(root, env_root, follow_symlinks=False)))
            except (ValueError, OSError):
                continue
    for base in bases:
        try:
            candidate = str(safe_join(base, *_CN_SUFFIX, follow_symlinks=False))
        except (ValueError, OSError):
            continue
        if os.path.isfile(candidate):
            return candidate
    return None


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
            # This path is passed to spec_from_file_location/exec_module. The env var is
            # operator-controlled, so this does not defend against a hostile operator; it
            # only guarantees we load exactly <root>/lib_controlnet/external_code.py and a
            # relative value cannot walk out of its base via "..". Containment is lexical
            # so symlinked/junctioned ControlNet installs keep working.
            env_path = _resolve_env_controlnet_file(env_root, extension_root)
            if env_path and os.path.isfile(env_path):
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
