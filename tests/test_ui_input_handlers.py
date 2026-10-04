def _get_ranbooru():
    import scripts.ranbooru as ranbooru

    return ranbooru


def test_sanitize_gelbooru_compat_base_url():
    ranbooru = _get_ranbooru()
    assert ranbooru._sanitize_gelbooru_compat_base_url("site.com/api/") == "https://site.com/api"
    assert (
        ranbooru._sanitize_gelbooru_compat_base_url("http://example.com///") == "http://example.com"
    )
    assert ranbooru._sanitize_gelbooru_compat_base_url("") == ""


def test_update_gelbooru_ui_visibility_branches(monkeypatch):
    ranbooru = _get_ranbooru()
    script = ranbooru.Script()

    # Branch 1: booru == 'gelbooru' with saved credentials
    monkeypatch.setattr(
        script,
        "_get_saved_gelbooru_credentials",
        lambda: {"api_key": "k", "user_id": "u"},
    )
    res = script._update_gelbooru_ui_visibility("gelbooru")
    # Textboxes (indices 3 and 4) must be cleared
    val3 = getattr(res[3], "value", None) or (
        res[3].get("value") if isinstance(res[3], dict) else None
    )
    val4 = getattr(res[4], "value", None) or (
        res[4].get("value") if isinstance(res[4], dict) else None
    )
    assert val3 == ""
    assert val4 == ""

    # Branch 2: booru == 'gelbooru' without saved credentials
    monkeypatch.setattr(script, "_get_saved_gelbooru_credentials", lambda: None)
    res = script._update_gelbooru_ui_visibility("gelbooru")
    # Textboxes must not specify value="" (preserving user typed text)
    val3 = getattr(res[3], "value", None) or (
        res[3].get("value") if isinstance(res[3], dict) else None
    )
    val4 = getattr(res[4], "value", None) or (
        res[4].get("value") if isinstance(res[4], dict) else None
    )
    assert val3 is None or val3 != ""

    # Branch 3: non-gelbooru
    res = script._update_gelbooru_ui_visibility("danbooru")
    val3 = getattr(res[3], "value", None) or (
        res[3].get("value") if isinstance(res[3], dict) else None
    )
    val4 = getattr(res[4], "value", None) or (
        res[4].get("value") if isinstance(res[4], dict) else None
    )
    assert val3 is None or val3 != ""
