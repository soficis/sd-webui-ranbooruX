import importlib
import sys
import types

import pytest


def _reload_ranbooru():
    sys.modules.pop("scripts.ranbooru", None)
    return importlib.import_module("scripts.ranbooru")


@pytest.mark.parametrize(
    "unit, expected",
    [
        ({"model": "anima-lllite-depth-1"}, True),
        ({"model": "None"}, False),
        ({"model": "none"}, False),
        ({"model": ""}, False),
        ({}, False),
        (types.SimpleNamespace(model="control_v11p_sd15_canny"), True),
        (types.SimpleNamespace(model="None"), False),
        (types.SimpleNamespace(), False),
    ],
)
def test_controlnet_unit_has_model(stub_modules, unit, expected):
    ranbooru = _reload_ranbooru()
    assert ranbooru._controlnet_unit_has_model(unit) is expected


class _FakeRunner:
    def __init__(self):
        self.alwayson_scripts = []
        self.scripts = []


def _attach(ranbooru, monkeypatch, handoff):
    monkeypatch.setattr(ranbooru.scripts, "ScriptRunner", _FakeRunner, raising=False)
    owner = types.SimpleNamespace(_cn_img2img_handoff=handoff, controlnet_weight=0.5)
    p = types.SimpleNamespace(comments=[])
    p_img2img = types.SimpleNamespace(scripts=None, script_args=None)
    # conftest stubs numpy and PIL, so the image is a sentinel passed straight through.
    monkeypatch.setattr(ranbooru.np, "array", lambda value: value, raising=False)
    img = types.SimpleNamespace(convert=lambda mode: f"prepared-{mode}")
    attached = ranbooru.Script._attach_controlnet_to_img2img(owner, p, p_img2img, img)
    return attached, p, p_img2img


def test_attach_controlnet_without_handoff_leaves_img2img_alone(stub_modules, monkeypatch):
    ranbooru = _reload_ranbooru()
    attached, _, p_img2img = _attach(ranbooru, monkeypatch, None)
    assert attached is False
    assert p_img2img.scripts is None and p_img2img.script_args is None


@pytest.mark.parametrize("as_dict", [True, False])
def test_attach_controlnet_enables_copy_of_unit0(stub_modules, monkeypatch, as_dict):
    ranbooru = _reload_ranbooru()
    fields = {"enabled": False, "weight": 1.0, "image": None, "model": "depth"}
    unit = dict(fields) if as_dict else types.SimpleNamespace(**fields)
    cn_script = object()
    attached, p, p_img2img = _attach(ranbooru, monkeypatch, (cn_script, 1, ["other", unit, "tail"]))

    assert attached is True
    assert p_img2img.scripts.alwayson_scripts == [cn_script]
    assert len(p_img2img.script_args) == 3 and p_img2img.script_args[0] == "other"
    new_unit = p_img2img.script_args[1]
    get = (lambda u, k: u[k]) if as_dict else getattr
    assert get(new_unit, "enabled") is True and get(new_unit, "weight") == 0.5
    assert get(new_unit, "image") == {"image": "prepared-RGB", "mask": None}
    # The first pass's unit must stay off, or ControlNet runs on a discarded image.
    assert get(unit, "enabled") is False and get(unit, "image") is None


def test_attach_controlnet_failure_is_reported(stub_modules, monkeypatch):
    ranbooru = _reload_ranbooru()
    attached, p, p_img2img = _attach(ranbooru, monkeypatch, (object(), 5, ["only"]))
    assert attached is False
    assert p_img2img.scripts is None
    assert p.comments == [ranbooru.CONTROLNET_IMG2IMG_FAILED_NOTE]


@pytest.mark.parametrize("as_dict", [True, False])
def test_controlnet_unit_copy_leaves_original_untouched(stub_modules, as_dict):
    ranbooru = _reload_ranbooru()
    unit = {"enabled": True} if as_dict else types.SimpleNamespace(enabled=True)
    clone = ranbooru._controlnet_unit_copy(unit, enabled=False)
    assert ranbooru._controlnet_unit_enabled(unit) is True
    assert ranbooru._controlnet_unit_enabled(clone) is False
