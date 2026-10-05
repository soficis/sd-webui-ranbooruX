import importlib
import sys

import pytest

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


EXPECTED_ARG_LABELS = {
    "enabled": None,
    "tags": "Search tags",
    "booru": "Booru",
    "gelbooru_api_key": "Gelbooru API Key",
    "gelbooru_user_id": "Gelbooru User ID",
    "gelbooru_compat_base_url": "Gelbooru-compatible Base URL",
    "remove_bad_tags": "Remove common 'bad' tags",
    "max_pages": "Max Pages (tag search)",
    "change_dash": 'Convert "_" to spaces',
    "same_prompt": "Use same prompt for batch",
    "fringe_benefits": "Gelbooru: Fringe Benefits",
    "remove_tags": "Always remove tags",
    "use_img2img": "Use Image for Img2Img",
    "denoising": "Img2Img denoising",
    "use_last_img": "Use same image for batch",
    "change_background": "Change Background",
    "change_color": "Change Color",
    "shuffle_tags": "Shuffle tags",
    "post_id": "Post ID (Overrides tags/pages)",
    "mix_prompt": "Mix tags from multiple posts",
    "mix_amount": "Posts to mix",
    "chaos_mode": "Shuffle tags (chaos)",
    "chaos_amount": "Chaos Amount %",
    "limit_tags": "Limit tags by %",
    "max_tags": "Max tags (0=disabled)",
    "sorting_order": "Sort Order (tag search)",
    "mature_rating": "Mature Rating",
    "lora_folder": "LoRAs Subfolder",
    "lora_amount": "LoRAs Amount",
    "lora_min": "Min LoRAs Weight",
    "lora_max": "Max LoRAs Weight",
    "lora_enabled": None,
    "lora_custom_weights": "Custom Weights (optional)",
    "lora_lock_prev": "Lock previous LoRAs",
    "use_ip": "Use Image for ControlNet (Unit 0)",
    "use_search_txt": "Add line from Search File",
    "use_remove_txt": "Add tags from Remove File",
    "choose_search_txt": "Choose Search File",
    "choose_remove_txt": "Choose Remove File",
    "search_refresh_btn": None,
    "remove_refresh_btn": None,
    "crop_center": "Crop image to fit target",
    "enable_adetailer_support": "Enable RanbooruX ADetailer support",
    "use_same_seed": "Use same seed for batch",
    "reuse_cached_posts": "Reuse cached booru posts",
    "use_cache": "Cache Booru API requests",
    "log_prompt_sources": "Log image sources/prompts to txt",
    "remove_artist_tags": "Remove artist tags",
    "remove_character_tags": "Remove character tags",
    "remove_clothing_tags": "Remove clothing tags",
    "remove_text_tags": "Remove tag/text/commentary metadata",
    "restrict_subject_tags": "Keep only subject counts",
    "remove_furry_tags": "Filter furry/pokemon tags",
    "remove_headwear_tags": "Filter headwear / halo tags",
    "remove_girl_suffix_tags": "Filter _girl suffix tags",
    "preserve_hair_eye_colors": "Preserve base hair & eye colors",
    "remove_series_tags": "Remove series / franchise tags",
    "use_tag_catalog": "Use Danbooru Tag Catalog",
    "catalog_path": "Custom catalog path",
    "lora_auto_detect_pony": "Auto-detect PonyXL-compatible LoRAs",
    "lora_detected_loras": "Detected LoRAs (toggle enabled)",
    "lora_blacklist": "LoRAnado blacklist",
    "anima_auto_detect": "Auto-detect Anima model",
    "anima_tune_img2img": "Auto-tune Img2Img parameters for Anima",
    "controlnet_weight": "ControlNet weight",
}


def test_ui_layout_preserves_script_arg_order(stub_modules):
    """Guards that script-arg positions keep pointing at the same controls.

    Script args are positional, so a reorder of the components list silently feeds
    one control's value into another option. The snapshot pins field -> label.
    """
    ranbooru = _reload_ranbooru()
    script = ranbooru.Script()

    components = script.ui(is_img2img=False)
    assert len(components) == len(UI_ARGUMENT_FIELDS)

    actual = {
        field: getattr(component, "label", None)
        for field, component in zip(UI_ARGUMENT_FIELDS, components)
    }
    assert list(actual) == list(EXPECTED_ARG_LABELS)
    assert actual == EXPECTED_ARG_LABELS


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


def _track_created(monkeypatch, component_name):
    import gradio as gr

    created = []
    cls = getattr(gr, component_name)
    orig_init = cls.__init__

    def tracked_init(self, *args, **kwargs):
        created.append(self)
        orig_init(self, *args, **kwargs)

    monkeypatch.setattr(cls, "__init__", tracked_init)
    return created


def test_stub_rejects_kwargs_real_gradio_rejects(stub_modules):
    """gr.File has no `info` parameter in Gradio 4.40; the stub must fail like the real one."""
    import gradio as gr

    with pytest.raises(TypeError):
        gr.File(label="x", info="y")
    with pytest.raises(TypeError):
        gr.Button("x", label="y")


def test_list_display_boxes_are_not_saved_to_ui_config(stub_modules, monkeypatch):
    created = _track_created(monkeypatch, "Textbox")
    ranbooru = _reload_ranbooru()
    ranbooru.Script().ui(is_img2img=False)

    displays = [
        box
        for box in created
        if (box.label or "").startswith(("Personal removal list (", "Favorites list ("))
    ]
    assert len(displays) == 2
    for box in displays:
        assert getattr(box, "do_not_save_to_config", False) is True


def test_mode_amount_sliders_are_always_visible(stub_modules, monkeypatch):
    created = _track_created(monkeypatch, "Slider")
    ranbooru = _reload_ranbooru()
    ranbooru.Script().ui(is_img2img=False)

    by_label = {slider.label: slider for slider in created}
    for label in ("Posts to mix", "Chaos Amount %"):
        assert by_label[label].visible is True


def test_ui_post_id_lock_reapplied_on_page_load(stub_modules, monkeypatch):
    """A Post ID restored from ui-config.json must lock the search controls on load."""
    import types

    calls = []

    class _Root:
        def load(self, **kwargs):
            calls.append(kwargs)

    context_mod = types.ModuleType("gradio.context")
    context_mod.Context = types.SimpleNamespace(root_block=_Root())
    monkeypatch.setitem(sys.modules, "gradio.context", context_mod)

    ranbooru = _reload_ranbooru()
    script = ranbooru.Script()
    components = RunComponents.from_sequence(script.ui(is_img2img=False)).components

    post_id_loads = [c for c in calls if c["fn"] == script._ui_update_post_id_dependencies]
    assert len(post_id_loads) == 1
    load = post_id_loads[0]
    assert load["inputs"] == [components["post_id"]]
    assert load["outputs"] == [
        components["tags"],
        components["max_pages"],
        components["sorting_order"],
    ]


def test_register_page_load_without_gradio_context_is_noop(stub_modules, monkeypatch):
    monkeypatch.setitem(sys.modules, "gradio.context", None)
    ranbooru = _reload_ranbooru()
    assert ranbooru._register_page_load(lambda v: v, inputs=[], outputs=[]) is False
