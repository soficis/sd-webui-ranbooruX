import random

from ranboorux.loranado import (
    filter_candidates,
    format_lora_prompt,
    normalize_lora_name,
    parse_custom_weights,
    select_loras,
)


def test_normalize_lora_name():
    assert normalize_lora_name("my_lora.safetensors") == "my_lora"
    assert normalize_lora_name("Folder/Another_Lora.pt") == "folder/another_lora"
    assert normalize_lora_name("") == ""
    assert normalize_lora_name(None) == ""


def test_parse_custom_weights():
    assert parse_custom_weights("0.5, 0.85, 1.0") == [0.5, 0.85, 1.0]
    assert parse_custom_weights("0.5, invalid, 1.0") == []
    assert parse_custom_weights("") == []
    assert parse_custom_weights(None) == []


def test_filter_candidates():
    candidates = [
        "lora_a.safetensors",
        "lora_b.safetensors",
        "lora_c.safetensors",
        "pony_lora.safetensors",
    ]

    # 1. Enabled candidate filtering
    enabled = ["lora_a", "pony_lora"]
    filtered_enabled = filter_candidates(candidates, enabled_loras=enabled, blacklist_loras=[])
    assert filtered_enabled == ["lora_a.safetensors", "pony_lora.safetensors"]

    # 2. Blacklist filtering
    blacklist = ["pony_lora"]
    filtered_blacklisted = filter_candidates(
        candidates, enabled_loras=[], blacklist_loras=blacklist
    )
    assert filtered_blacklisted == [
        "lora_a.safetensors",
        "lora_b.safetensors",
        "lora_c.safetensors",
    ]

    # 3. Both enabled and blacklist
    filtered_both = filter_candidates(candidates, enabled_loras=enabled, blacklist_loras=blacklist)
    assert filtered_both == ["lora_a.safetensors"]


def test_select_loras_deterministic():
    candidates = ["lora1.safetensors", "lora2.safetensors", "lora3.safetensors"]

    # Seeded random source to ensure determinism
    rng1 = random.Random(42)
    selection1 = select_loras(candidates, amount=2, lora_min=0.5, lora_max=0.9, random_source=rng1)

    rng2 = random.Random(42)
    selection2 = select_loras(candidates, amount=2, lora_min=0.5, lora_max=0.9, random_source=rng2)

    assert selection1 == selection2
    assert len(selection1) == 2
    # Verify name stripping in selections
    assert selection1[0][0] in ("lora1", "lora2", "lora3")
    assert 0.5 <= selection1[0][1] <= 0.9

    # Custom weights priority test
    rng3 = random.Random(100)
    selection_custom = select_loras(
        candidates,
        amount=3,
        lora_min=0.1,
        lora_max=0.2,
        custom_weights=[0.88, 0.99],
        random_source=rng3,
    )
    assert len(selection_custom) == 3
    # The first two should use custom weights, the third uses rng.uniform
    assert selection_custom[0][1] == 0.88
    assert selection_custom[1][1] == 0.99
    assert 0.1 <= selection_custom[2][1] <= 0.2


def test_format_lora_prompt():
    selected = [("lora_a", 0.75), ("lora_b", 1.0)]
    assert format_lora_prompt(selected) == "<lora:lora_a:0.75> <lora:lora_b:1.0>"
    assert format_lora_prompt([]) == ""
