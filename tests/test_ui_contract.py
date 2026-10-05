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


def test_ui_components_and_buttons_have_unique_labels(stub_modules, monkeypatch):
    """Guards that value-bearing component labels and button texts are unique (U22, U24)."""
    import gradio as gr

    created_components = []

    def make_tracker(orig_cls):
        orig_init = orig_cls.__init__

        def tracked_init(self, *args, **kwargs):
            created_components.append((orig_cls.__name__, self, args, kwargs))
            orig_init(self, *args, **kwargs)

        return tracked_init

    for comp_name in (
        "Checkbox",
        "Textbox",
        "Dropdown",
        "Slider",
        "Radio",
        "File",
        "DownloadButton",
        "Button",
    ):
        cls = getattr(gr, comp_name)
        monkeypatch.setattr(cls, "__init__", make_tracker(cls))

    ranbooru = _reload_ranbooru()
    script = ranbooru.Script()
    script.ui(is_img2img=False)

    # Check button texts
    buttons = [c for c in created_components if c[0] in ("Button", "DownloadButton")]
    button_texts = []
    for comp_type, inst, args, kwargs in buttons:
        text = (
            kwargs.get("label")
            or (args[0] if args and isinstance(args[0], str) else None)
            or kwargs.get("value")
        )
        if text:
            button_texts.append(text)

    dup_buttons = [t for t in set(button_texts) if button_texts.count(t) > 1]
    assert not dup_buttons, f"Duplicate button texts found: {dup_buttons}"

    # Check value-bearing component labels
    value_components = [
        c
        for c in created_components
        if c[0] in ("Checkbox", "Textbox", "Dropdown", "Slider", "Radio", "File")
    ]
    labels = []
    for comp_type, inst, args, kwargs in value_components:
        label = kwargs.get("label") or (args[0] if args and isinstance(args[0], str) else None)
        if label:
            labels.append(label)

    dup_labels = [lbl for lbl in set(labels) if labels.count(lbl) > 1]
    assert not dup_labels, f"Duplicate component labels found: {dup_labels}"


def test_ui_post_id_dependencies(stub_modules):
    ranbooru = _reload_ranbooru()
    script = ranbooru.Script()

    # When post_id is provided, search controls should become non-interactive
    updates_non_empty = script._ui_update_post_id_dependencies("12345")
    assert len(updates_non_empty) == 3
    for up in updates_non_empty:
        val = up.interactive if hasattr(up, "interactive") else up.get("interactive")
        assert val is False

    # When post_id is empty, search controls should be interactive
    updates_empty = script._ui_update_post_id_dependencies("")
    assert len(updates_empty) == 3
    for up in updates_empty:
        val = up.interactive if hasattr(up, "interactive") else up.get("interactive")
        assert val is True

    # Whitespace only should be treated as empty
    updates_spaces = script._ui_update_post_id_dependencies("   ")
    assert len(updates_spaces) == 3
    for up in updates_spaces:
        val = up.interactive if hasattr(up, "interactive") else up.get("interactive")
        assert val is True
