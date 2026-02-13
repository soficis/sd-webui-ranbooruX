import importlib
import sys


def _reload_ranbooru():
    sys.modules.pop("scripts.ranbooru", None)
    return importlib.import_module("scripts.ranbooru")


def test_import_forge_stubs(stub_modules):
    module = _reload_ranbooru()
    assert module is not None


def test_import_no_model_hijack(stub_modules_without_model_hijack):
    module = _reload_ranbooru()
    assert module is not None


def test_import_no_inputaccordion(stub_modules_without_inputaccordion):
    module = _reload_ranbooru()
    assert module is not None


def test_smoke_import_all_stubs(stub_modules):
    modules_pkg = sys.modules.get("modules")
    if modules_pkg is not None:
        for attr in ("sd_hijack", "ui_components"):
            if hasattr(modules_pkg, attr):
                delattr(modules_pkg, attr)
    sys.modules.pop("modules.sd_hijack", None)
    sys.modules.pop("modules.ui_components", None)
    module = _reload_ranbooru()
    assert module is not None
