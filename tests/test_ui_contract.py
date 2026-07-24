import importlib
import sys

from ranboorux.run_options import UI_ARGUMENT_FIELDS, RunComponents


def _reload_ranbooru():
    sys.modules.pop("scripts.ranbooru", None)
    return importlib.import_module("scripts.ranbooru")


def test_ui_argument_contract_length(stub_modules):
    ranbooru = _reload_ranbooru()
    script = ranbooru.Script()

    # Check with is_img2img = False
    components_txt = script.ui(is_img2img=False)
    assert len(components_txt) == len(UI_ARGUMENT_FIELDS)
    assert RunComponents.from_sequence(components_txt).script_args() == components_txt

    # Check with is_img2img = True
    components_img = script.ui(is_img2img=True)
    assert len(components_img) == len(UI_ARGUMENT_FIELDS)
    assert RunComponents.from_sequence(components_img).script_args() == components_img

    # Verify sequence contains mocked Gradio components
    for i, comp in enumerate(components_txt):
        assert comp is not None, f"Component at index {i} is None"
