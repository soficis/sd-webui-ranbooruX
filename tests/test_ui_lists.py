def _get_ranbooru():
    import scripts.ranbooru as ranbooru

    return ranbooru


def test_default_build_state_list_selectors_empty(monkeypatch, tmp_path):
    ranbooru = _get_ranbooru()
    script = ranbooru.Script()

    # Create dummy list files with items
    p_file = tmp_path / "personal_remove.txt"
    p_file.write_text("tag1\ntag2\n", encoding="utf-8")
    f_file = tmp_path / "favorites.txt"
    f_file.write_text("fav1\nfav2\n", encoding="utf-8")

    monkeypatch.setattr(ranbooru, "PERSONAL_REMOVE_FILE", str(p_file))
    monkeypatch.setattr(ranbooru, "FAVORITES_FILE", str(f_file))

    script.ui(is_img2img=False)

    # Personal remove dropdown and favorites dropdown should have value=[] at build
    assert hasattr(script, "_ui_personal_dropdown")
    assert script._ui_personal_dropdown.value == []
    assert hasattr(script, "_ui_favorites_dropdown")
    assert script._ui_favorites_dropdown.value == []


def test_ui_remove_personal_tags(monkeypatch, tmp_path):
    ranbooru = _get_ranbooru()
    script = ranbooru.Script()

    p_file = tmp_path / "personal_remove.txt"
    p_file.write_text("tag1\ntag2\ntag3\n", encoding="utf-8")
    monkeypatch.setattr(ranbooru, "PERSONAL_REMOVE_FILE", str(p_file))

    # Removing empty selection does not alter file
    mtime_before = p_file.stat().st_mtime_ns
    script._ui_remove_personal_tags([])
    assert p_file.stat().st_mtime_ns == mtime_before
    assert p_file.read_text(encoding="utf-8").splitlines() == ["tag1", "tag2", "tag3"]

    # Removing specific item removes only that item
    script._ui_remove_personal_tags(["tag2"])
    assert p_file.read_text(encoding="utf-8").splitlines() == ["tag1", "tag3"]


def test_ui_import_personal_list(monkeypatch, tmp_path):
    ranbooru = _get_ranbooru()
    script = ranbooru.Script()

    p_file = tmp_path / "personal_remove.txt"
    p_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(ranbooru, "PERSONAL_REMOVE_FILE", str(p_file))

    # Import via str path
    import_file = tmp_path / "import1.txt"
    import_file.write_text("imported1, imported2", encoding="utf-8")
    script._ui_import_personal_list(str(import_file))
    assert "imported1" in p_file.read_text(encoding="utf-8")
    assert "imported2" in p_file.read_text(encoding="utf-8")

    # Import with BOM stripped
    import_bom = tmp_path / "import_bom.txt"
    import_bom.write_text("bom_tag", encoding="utf-8-sig")
    script._ui_import_personal_list(import_bom)
    assert "bom_tag" in p_file.read_text(encoding="utf-8")
    assert "\ufeff" not in p_file.read_text(encoding="utf-8")

    # Import with dict format
    import_dict_file = tmp_path / "import_dict.txt"
    import_dict_file.write_text("dict_tag", encoding="utf-8")
    script._ui_import_personal_list({"name": str(import_dict_file)})
    assert "dict_tag" in p_file.read_text(encoding="utf-8")

    # Import with >1MiB rejected
    large_file = tmp_path / "large.txt"
    large_file.write_bytes(b"a" * (1024 * 1024 + 10))
    mtime = p_file.stat().st_mtime_ns
    script._ui_import_personal_list(str(large_file))
    assert p_file.stat().st_mtime_ns == mtime  # unchanged


def test_list_mutation_download_button_outputs(monkeypatch, tmp_path):
    ranbooru = _get_ranbooru()
    script = ranbooru.Script()

    p_file = tmp_path / "personal_remove.txt"
    p_file.write_text("t1\n", encoding="utf-8")
    monkeypatch.setattr(ranbooru, "PERSONAL_REMOVE_FILE", str(p_file))

    # Add tag returns download button update
    res = script._ui_add_personal_tags("newtag", [])
    # Should return (dropdown_update, textbox_update, download_btn_update, ...)
    # The download button update must contain value=str(p_file)
    btn_update = res[2]
    val = getattr(btn_update, "value", None) or (
        btn_update.get("value") if isinstance(btn_update, dict) else None
    )
    assert val == str(p_file)


def test_get_available_ratings_with_current():
    ranbooru = _get_ranbooru()

    # 1-arg backward compat
    res = ranbooru.get_available_ratings("e621")
    val = getattr(res, "value", None) or (res.get("value") if isinstance(res, dict) else None)
    assert val == "All"

    # 2-arg keeping rating
    res = ranbooru.get_available_ratings("e621", current="Safe")
    val = getattr(res, "value", None) or (res.get("value") if isinstance(res, dict) else None)
    assert val == "Safe"

    # Sensitive falls back to Safe on full booru (e621)
    res = ranbooru.get_available_ratings("e621", current="Sensitive")
    val = getattr(res, "value", None) or (res.get("value") if isinstance(res, dict) else None)
    assert val == "Safe"

    # Falls back to All on safebooru
    res = ranbooru.get_available_ratings("safebooru", current="Safe")
    val = getattr(res, "value", None) or (res.get("value") if isinstance(res, dict) else None)
    assert val == "All"


def test_note_run_failure():
    ranbooru = _get_ranbooru()

    class DummyP:
        def __init__(self):
            self.comments = {}

        def comment(self, text):
            self.comments[text] = 1

    p = DummyP()
    ranbooru._note_run_failure(p, "boom at E:\\secret\\dir")
    assert len(p.comments) == 1
    comment_text = list(p.comments.keys())[0]
    assert comment_text.startswith("RanbooruX: ")
    assert "secret" not in comment_text


def test_note_postprocess_failure():
    ranbooru = _get_ranbooru()

    class DummyProcessed:
        def __init__(self):
            self.comments = "Existing comment\n"

    proc = DummyProcessed()
    ranbooru._note_postprocess_failure(proc, "No valid images for Img2Img.")
    assert "Existing comment" in proc.comments
    assert "RanbooruX: No valid images for Img2Img." in proc.comments
