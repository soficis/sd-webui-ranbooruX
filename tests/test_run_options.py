import pytest

from ranboorux.run_options import UI_ARGUMENT_FIELDS, RunComponents, RunOptions


def test_ui_argument_field_order_is_frozen():
    assert len(UI_ARGUMENT_FIELDS) == 62
    assert UI_ARGUMENT_FIELDS[:6] == (
        "enabled",
        "tags",
        "booru",
        "gelbooru_api_key",
        "gelbooru_user_id",
        "gelbooru_compat_base_url",
    )
    assert UI_ARGUMENT_FIELDS[-5:] == (
        "use_tag_catalog",
        "catalog_path",
        "lora_auto_detect_pony",
        "lora_detected_loras",
        "lora_blacklist",
    )


def test_run_options_from_script_args_maps_names_once():
    values = list(range(len(UI_ARGUMENT_FIELDS)))

    options = RunOptions.from_script_args(values)

    assert options.enabled == 0
    assert options.tags == 1
    assert options.gelbooru.compat_base_url == 5
    assert options.image_workflow.use_img2img == 12
    assert options.tag_filters.remove_text_tags == 50
    assert options.loranado.blacklist == 61
    assert options.as_dict() == dict(zip(UI_ARGUMENT_FIELDS, values))


def test_run_options_rejects_wrong_count():
    with pytest.raises(ValueError, match="Expected 62"):
        RunOptions.from_script_args([object()])


def test_run_components_round_trips_script_args_in_contract_order():
    values = [object() for _ in UI_ARGUMENT_FIELDS]
    components = RunComponents.from_sequence(values)

    assert components.script_args() == values


def test_run_components_rejects_missing_fields():
    components = RunComponents({"enabled": object()})

    with pytest.raises(ValueError, match="Missing RanbooruX components"):
        components.script_args()
