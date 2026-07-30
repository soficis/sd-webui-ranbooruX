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
    import os

    monkeypatch.setattr(
        importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError(name))
    )
    monkeypatch.setattr(os.path, "isfile", lambda path: False)
    raised = False
    try:
        script._load_cn_external_code()
    except ImportError:
        raised = True
    assert raised


def test_load_external_code_failure_does_not_leak_local_paths(monkeypatch):
    script = _make_script()
    import importlib
    import os

    private_path = "E:" + "\\private\\sd-webui\\extensions\\sd_forge_controlnet"
    monkeypatch.setenv("SD_FORGE_CONTROLNET_PATH", private_path)
    monkeypatch.setattr(
        importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError(name))
    )
    monkeypatch.setattr(os.path, "isfile", lambda path: False)

    try:
        script._load_cn_external_code()
    except ImportError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected ControlNet import failure")

    assert private_path not in message
    assert "file://" not in message
    assert "configured ControlNet external_code.py not found" in message


def test_load_external_code_redacts_all_path_types_and_secrets(monkeypatch):
    script = _make_script()
    import importlib
    import os

    windows_path = "E:" + "\\private\\forge\\extensions\\sd_forge_controlnet"
    posix_path = "/home/user/forge/extensions/sd-webui-controlnet"
    unc_path = "\\\\server\\share\\path\\to\\extensions"
    file_path = "file:" + "///C:/Users/fanph/secret_extension"
    signed_url = "https://cdn.test/foo?sig=secret123&x-amz-signature=amzsecret"

    err_msg = (
        f"Failed loading from {windows_path} and {posix_path} and {unc_path} "
        f"and {file_path} with signed URL {signed_url}"
    )

    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ImportError(err_msg)),
    )
    monkeypatch.setattr(os.path, "isfile", lambda path: False)

    try:
        script._load_cn_external_code()
    except ImportError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected ControlNet import failure")

    assert windows_path not in message
    assert posix_path not in message
    assert unc_path not in message
    assert file_path not in message
    assert "secret123" not in message
    assert "amzsecret" not in message

    diagnostics = script._render_platform_diagnostics()
    assert windows_path not in diagnostics
    assert posix_path not in diagnostics
    assert unc_path not in diagnostics
    assert file_path not in diagnostics
    assert "secret123" not in diagnostics
    assert "amzsecret" not in diagnostics
