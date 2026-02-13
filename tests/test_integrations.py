import types


def test_cn_integration(monkeypatch):
    import importlib

    from ranboorux.integrations import controlnet

    sentinel = types.SimpleNamespace(name="cn")
    target = "sd_forge_controlnet.lib_controlnet.external_code"

    def fake_import(name):
        if name == target:
            return sentinel
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    loaded = controlnet.load_external_code("C:/missing")
    assert loaded is sentinel


def test_ad_integration():
    from ranboorux.integrations import adetailer

    ok, message = adetailer.verify_patch_target(
        types.SimpleNamespace(process=lambda: None), "process"
    )
    assert ok
    assert "verified" in message.lower()
