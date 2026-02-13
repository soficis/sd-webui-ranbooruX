import types


def _make_script():
    import scripts.ranbooru as ranbooru

    return ranbooru.Script()


def test_load_external_code_via_primary_import(monkeypatch):
    script = _make_script()
    import importlib

    module = types.SimpleNamespace(name="external_code")
    target = "sd_forge_controlnet.lib_controlnet.external_code"
    original_import = importlib.import_module

    def fake_import(name):
        if name == target:
            return module
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    assert script._load_cn_external_code() is module
    monkeypatch.setattr(importlib, "import_module", original_import)


def test_load_external_code_failure(monkeypatch):
    script = _make_script()
    import importlib

    monkeypatch.setattr(
        importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError(name))
    )
    monkeypatch.setattr("os.path.isfile", lambda path: False)
    raised = False
    try:
        script._load_cn_external_code()
    except ImportError:
        raised = True
    assert raised
