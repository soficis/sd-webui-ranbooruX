def test_remove_repeated_tags():
    import scripts.ranbooru as ranbooru

    assert ranbooru.remove_repeated_tags("a, b, a, c") == "a,b,c"
    assert ranbooru.remove_repeated_tags("") == ""
    assert ranbooru.remove_repeated_tags(None) == ""


def test_limit_prompt_tags():
    import scripts.ranbooru as ranbooru

    assert ranbooru.limit_prompt_tags("a, b, c, d", 0.5, "Limit") == "a,b"
    assert ranbooru.limit_prompt_tags("a, b, c, d", 2, "Max") == "a,b"
    assert ranbooru.limit_prompt_tags("a, b", "bad", "Max") == "a, b"
    assert ranbooru.limit_prompt_tags("a, b", 1, "Unknown") == "a, b"


def test_sanitize_gelbooru_credential_variants():
    import scripts.ranbooru as ranbooru

    assert ranbooru._sanitize_gelbooru_credential(' "api_key=abc%26user_id=def" ') == "abc"
    assert ranbooru._sanitize_gelbooru_credential("user_id= 123 ") == "123"
    assert ranbooru._sanitize_gelbooru_credential(None) == ""


def test_sanitize_gelbooru_compat_base_url():
    import scripts.ranbooru as ranbooru

    assert ranbooru._sanitize_gelbooru_compat_base_url("example.com/") == "https://example.com"
    assert (
        ranbooru._sanitize_gelbooru_compat_base_url("http://example.com////")
        == "http://example.com"
    )
    assert ranbooru._sanitize_gelbooru_compat_base_url("") == ""


def test_gelbooru_compat_parse_json_entities():
    import scripts.ranbooru as ranbooru

    client = ranbooru.GelbooruCompatible("https://example.com")
    payload = {"post": [{"id": "1"}, {"id": "2"}], "@attributes": {"count": "42"}}
    entries, approx = client._parse_json_entities(payload, "post")
    assert [entry["id"] for entry in entries] == ["1", "2"]
    assert approx == 42


def test_gelbooru_compat_parse_xml_entities():
    import scripts.ranbooru as ranbooru

    client = ranbooru.GelbooruCompatible("https://example.com")
    xml_payload = (
        "<posts count='2'>"
        "<post id='1' tags='a b' file_url='http://example.com/1.png' />"
        "<post id='2' tags='c' />"
        "</posts>"
    )
    entries, approx = client._parse_xml_entities(xml_payload, "post")
    assert entries[0]["id"] == "1"
    assert approx == 2


def test_standardize_post_uses_tag_dict():
    import scripts.ranbooru as ranbooru

    booru = ranbooru.Booru("Test", "https://example.com")
    post = booru._standardize_post(
        {
            "tags": {"artist": ["alice"], "character": ["bob"], "copyright": ["copy"]},
            "file_url": "http://example.com/img.png",
            "id": 12,
            "rating": "s",
        }
    )
    assert post["artist_tags"] == ["alice"]
    assert post["character_tags"] == ["bob"]
    assert post["copyright_tags"] == ["copy"]
    assert post["file_url"] == "http://example.com/img.png"


def test_standardize_post_tag_string_override_and_heuristic():
    import scripts.ranbooru as ranbooru

    booru = ranbooru.Booru("Test", "https://example.com")
    post = booru._standardize_post(
        {
            "tags": "foo_(series) bar",
            "tag_string_artist": "artist_one artist_two",
            "id": 5,
            "rating": "q",
        }
    )
    assert post["artist_tags"] == ["artist_one", "artist_two"]
    assert "foo_(series)" in post["character_tags"]


def _write_dummy_safetensors(path, metadata=None):
    import json

    payload = {"__metadata__": metadata or {}}
    header = json.dumps(payload).encode("utf-8")
    path.write_bytes(len(header).to_bytes(8, "little") + header + b"\x00")


def test_show_fringe_benefits_only_visible_for_gelbooru(active_gradio_version):
    import scripts.ranbooru as ranbooru

    gelbooru = ranbooru.show_fringe_benefits("gelbooru")
    danbooru = ranbooru.show_fringe_benefits("danbooru")
    if active_gradio_version == "3":
        assert gelbooru["visible"] is True
        assert danbooru["visible"] is False
    else:
        assert gelbooru is not None
        assert danbooru is not None


def test_loranado_scan_detects_ponyxl_markers(tmp_path):
    import types
    import scripts.ranbooru as ranbooru

    ranbooru.shared.cmd_opts = types.SimpleNamespace(lora_dir=str(tmp_path))
    _write_dummy_safetensors(tmp_path / "pony_magic.safetensors")
    _write_dummy_safetensors(tmp_path / "xlp_style.safetensors")
    _write_dummy_safetensors(tmp_path / "ponytail_style.safetensors")
    _write_dummy_safetensors(
        tmp_path / "metadata_style.safetensors",
        metadata={"ss_base_model_version": "PonyDiffusionXL"},
    )
    _write_dummy_safetensors(
        tmp_path / "metadata_arch.safetensors",
        metadata={"modelspec.architecture": "Pony XL"},
    )
    _write_dummy_safetensors(
        tmp_path / "metadata_noise.safetensors",
        metadata={"ss_tag_frequency": {"pony": 3}},
    )
    _write_dummy_safetensors(
        tmp_path / "generic_style.safetensors",
        metadata={"ss_base_model_version": "sd1.5"},
    )

    script = ranbooru.Script()
    result = script._scan_loranado_candidates("")
    assert "pony_magic" in result["detected_names"]
    assert "xlp_style" in result["detected_names"]
    assert "metadata_style" in result["detected_names"]
    assert "metadata_arch" in result["detected_names"]
    assert "generic_style" not in result["detected_names"]
    assert "ponytail_style" not in result["detected_names"]
    assert "metadata_noise" not in result["detected_names"]


def test_loranado_detection_ignores_unrelated_metadata_keys():
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()
    assert not script._is_ponyxl_lora(
        "generic_style.safetensors",
        {"ss_tag_frequency": {"pony": 12}},
    )
    assert script._is_ponyxl_lora(
        "generic_style.safetensors",
        {"ss_base_model_version": "Pony XL"},
    )


def test_apply_loranado_respects_enabled_and_blacklist(tmp_path):
    import types
    import scripts.ranbooru as ranbooru

    ranbooru.shared.cmd_opts = types.SimpleNamespace(lora_dir=str(tmp_path))
    _write_dummy_safetensors(tmp_path / "pony_a.safetensors")
    _write_dummy_safetensors(tmp_path / "pony_b.safetensors")

    class DummyProcessing:
        def __init__(self):
            self.prompt = "base prompt"

    script = ranbooru.Script()
    proc = DummyProcessing()
    updated = script._apply_loranado(
        proc,
        lora_enabled=True,
        lora_folder="",
        lora_amount=2,
        lora_min=0.5,
        lora_max=1.0,
        lora_custom_weights="0.7,0.8",
        lora_lock_prev=False,
        lora_auto_detect_pony=True,
        lora_detected_loras=["pony_a", "pony_b"],
        lora_blacklist=["pony_b"],
    )
    assert "<lora:pony_a:0.7>" in updated.prompt
    assert "pony_b" not in updated.prompt


def test_post_rejected_by_filter_does_not_reject_unrelated_tags():
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()
    post = {
        "booru_name": "danbooru",
        "id": 123,
        "tags": "solo",
        "artist_tags": [],
        "character_tags": [],
        "copyright_tags": [],
    }

    rejected, reason = script._post_rejected_by_filter(
        post,
        filter_ctx=None,
        toggles=(
            True,   # remove_artist
            True,   # remove_character
            True,   # remove_clothing
            True,   # remove_text
            True,   # restrict_subject
            True,   # remove_furry
            True,   # remove_headwear
            True,   # remove_girl_suffix
            True,   # preserve_hair_eye
            True,   # remove_series
        ),
        base_colors=(set(), set()),
        allowed_subjects=set(),
        cache={},
        favorites_guard=set(),
    )

    assert rejected is False
    assert reason is None
