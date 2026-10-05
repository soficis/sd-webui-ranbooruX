import importlib
import sys

from ranboorux.run_options import UI_ARGUMENT_FIELDS, RunComponents


def _reload_ranbooru():
    sys.modules.pop("scripts.ranbooru", None)
    return importlib.import_module("scripts.ranbooru")


def test_ui_argument_contract_length(stub_modules):
    ranbooru = _reload_ranbooru()
    script = ranbooru.Script()

    components_txt = script.ui(is_img2img=False)
    assert len(components_txt) == len(UI_ARGUMENT_FIELDS)
    assert RunComponents.from_sequence(components_txt).script_args() == components_txt

    components_img = script.ui(is_img2img=True)
    assert len(components_img) == len(UI_ARGUMENT_FIELDS)
    assert RunComponents.from_sequence(components_img).script_args() == components_img

    for i, comp in enumerate(components_txt):
        assert comp is not None, f"Component at index {i} is None"


def test_ui_layout_preserves_script_arg_order(stub_modules):
    """Guards that UI regrouping does not shift or reorder script-arg component positions."""
    from ranboorux.run_options import RunOptions

    ranbooru = _reload_ranbooru()
    script = ranbooru.Script()

    components = script.ui(is_img2img=False)
    assert len(components) == len(UI_ARGUMENT_FIELDS)

    rc = RunComponents.from_sequence(components)
    ro = RunOptions.from_script_args(components)
    for idx, field in enumerate(UI_ARGUMENT_FIELDS):
        assert rc.components[field] is components[idx], f"Mismatch in rc at index {idx} for {field}"
        assert getattr(ro, field) is components[idx], f"Mismatch in ro at index {idx} for {field}"
