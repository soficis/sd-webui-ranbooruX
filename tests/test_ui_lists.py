import os
import time

import pytest


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


def _export_value(update):
    return getattr(update, "value", None) or (
        update.get("value") if isinstance(update, dict) else None
    )


def _read_export(update):
    path = _export_value(update)
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


@pytest.fixture
def export_root(monkeypatch, tmp_path):
    ranbooru = _get_ranbooru()
    root = tmp_path / "exports"
    root.mkdir()
    monkeypatch.setattr(ranbooru, "_export_root", lambda: str(root))
    return root


def test_ui_export_writes_current_list(monkeypatch, tmp_path, export_root):
    ranbooru = _get_ranbooru()
    script = ranbooru.Script()

    p_file = tmp_path / "personal_remove.txt"
    p_file.write_text("tag1\ntag2\n", encoding="utf-8")
    f_file = tmp_path / "favorites.txt"
    f_file.write_text("fav1\nfav2\n", encoding="utf-8")
    monkeypatch.setattr(ranbooru, "PERSONAL_REMOVE_FILE", str(p_file))
    monkeypatch.setattr(ranbooru, "FAVORITES_FILE", str(f_file))

    script._ui_add_personal_tags("tag3")
    export_p = script._ui_export_personal_list()
    assert _read_export(export_p) == ["tag1", "tag2", "tag3"]

    script._ui_add_favorite_tags("fav3")
    export_f = script._ui_export_favorite_list()
    assert _read_export(export_f) == ["fav1", "fav2", "fav3"]


def test_ui_export_keeps_list_filename_and_shows_box(monkeypatch, tmp_path, export_root):
    ranbooru = _get_ranbooru()
    script = ranbooru.Script()
    p_file = tmp_path / "personal_remove.txt"
    p_file.write_text("tag1\n", encoding="utf-8")
    monkeypatch.setattr(ranbooru, "PERSONAL_REMOVE_FILE", str(p_file))

    update = script._ui_export_personal_list()
    path = _export_value(update)
    assert os.path.basename(path) == "personal_remove.txt"
    assert os.path.dirname(os.path.dirname(path)) == str(export_root)
    visible = update.visible if hasattr(update, "visible") else update.get("visible")
    assert visible is True


def test_ui_export_cross_tab_after_edit(monkeypatch, tmp_path, export_root):
    ranbooru = _get_ranbooru()
    script1 = ranbooru.Script()
    script2 = ranbooru.Script()

    p_file = tmp_path / "personal_remove.txt"
    p_file.write_text("initial_tag\n", encoding="utf-8")
    monkeypatch.setattr(ranbooru, "PERSONAL_REMOVE_FILE", str(p_file))

    script1._ui_add_personal_tags("new_tab1_tag")
    content = _read_export(script2._ui_export_personal_list())
    assert "new_tab1_tag" in content
    assert "initial_tag" in content


def test_ui_export_successive_calls_return_different_paths(monkeypatch, tmp_path, export_root):
    ranbooru = _get_ranbooru()
    script = ranbooru.Script()

    p_file = tmp_path / "personal_remove.txt"
    p_file.write_text("tag1\n", encoding="utf-8")
    monkeypatch.setattr(ranbooru, "PERSONAL_REMOVE_FILE", str(p_file))

    path1 = _export_value(script._ui_export_personal_list())
    path2 = _export_value(script._ui_export_personal_list())
    assert path1 != path2
    assert os.path.exists(path1)
    assert os.path.exists(path2)


def test_prune_old_exports_removes_only_stale_folders(tmp_path):
    ranbooru = _get_ranbooru()
    old_dir = tmp_path / "personal_old"
    new_dir = tmp_path / "personal_new"
    old_dir.mkdir()
    new_dir.mkdir()
    (old_dir / "personal_remove.txt").write_text("x", encoding="utf-8")
    stale = time.time() - ranbooru.EXPORT_MAX_AGE_SECONDS - 60
    os.utime(old_dir, (stale, stale))

    ranbooru._prune_old_exports(str(tmp_path))

    assert not old_dir.exists()
    assert new_dir.exists()


def test_prune_old_exports_missing_root_is_noop(tmp_path):
    ranbooru = _get_ranbooru()
    ranbooru._prune_old_exports(str(tmp_path / "does_not_exist"))


def test_list_mutation_outputs_structure(monkeypatch, tmp_path):
    ranbooru = _get_ranbooru()
    script = ranbooru.Script()

    p_file = tmp_path / "personal_remove.txt"
    p_file.write_text("t1\n", encoding="utf-8")
    monkeypatch.setattr(ranbooru, "PERSONAL_REMOVE_FILE", str(p_file))

    # Add returns (dropdown, textbox, display, status) -> 4 items (no DownloadButton)
    res_add = script._ui_add_personal_tags("newtag")
    assert len(res_add) == 4

    # Remove returns (dropdown, display, status) -> 3 items
    res_remove = script._ui_remove_personal_tags([])
    assert len(res_remove) == 3

    # Dedupe returns (dropdown, display, status) -> 3 items
    res_dedupe = script._ui_dedupe_personal_list()
    assert len(res_dedupe) == 3

    # Import returns (dropdown, import_file, display, status) -> 4 items
    import_file = tmp_path / "imp.txt"
    import_file.write_text("imp1\n", encoding="utf-8")
    res_import = script._ui_import_personal_list(str(import_file))
    assert len(res_import) == 4


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


def test_gelbooru_saved_message_no_mojibake():
    ranbooru = _get_ranbooru()
    script = ranbooru.Script()
    msg = script._gelbooru_saved_message()
    assert msg == "Using saved Gelbooru credentials."
    assert "?" not in msg


def test_list_handlers_status_message(monkeypatch, tmp_path):
    ranbooru = _get_ranbooru()
    script = ranbooru.Script()

    p_file = tmp_path / "personal_remove.txt"
    p_file.write_text("existing_tag\n", encoding="utf-8")
    monkeypatch.setattr(ranbooru, "PERSONAL_REMOVE_FILE", str(p_file))

    # Add tag -> last element has status
    res = script._ui_add_personal_tags("new_tag")
    val = getattr(res[-1], "value", None) or (
        res[-1].get("value") if isinstance(res[-1], dict) else None
    )
    assert val == "Added 1 tag."

    # Remove with nothing selected -> last element has status
    res = script._ui_remove_personal_tags([])
    val = getattr(res[-1], "value", None) or (
        res[-1].get("value") if isinstance(res[-1], dict) else None
    )
    assert val == "Nothing selected."

    # Import valid -> last element has status
    import_file = tmp_path / "import_personal.txt"
    import_file.write_text("imported_tag_1, imported_tag_2\n", encoding="utf-8")
    res = script._ui_import_personal_list(str(import_file))
    val = getattr(res[-1], "value", None) or (
        res[-1].get("value") if isinstance(res[-1], dict) else None
    )
    assert "Imported 2 tags" in val

    # Favorites: Add, Remove, Dedupe, Import
    f_file = tmp_path / "favorites.txt"
    f_file.write_text("fav_tag\n", encoding="utf-8")
    monkeypatch.setattr(ranbooru, "FAVORITES_FILE", str(f_file))

    res = script._ui_add_favorite_tags("new_fav")
    val = getattr(res[-1], "value", None) or (
        res[-1].get("value") if isinstance(res[-1], dict) else None
    )
    assert val == "Added 1 tag."

    res = script._ui_remove_favorite_tags([])
    val = getattr(res[-1], "value", None) or (
        res[-1].get("value") if isinstance(res[-1], dict) else None
    )
    assert val == "Nothing selected."

    res = script._ui_dedupe_favorite_list()
    val = getattr(res[-1], "value", None) or (
        res[-1].get("value") if isinstance(res[-1], dict) else None
    )
    assert "duplicate" in val.lower()

    res = script._ui_import_favorite_list(str(import_file))
    val = getattr(res[-1], "value", None) or (
        res[-1].get("value") if isinstance(res[-1], dict) else None
    )
    assert "Imported 2 tags" in val


def test_catalog_status_prefixes(monkeypatch, tmp_path):
    ranbooru = _get_ranbooru()
    script = ranbooru.Script()

    # Toggle off: bundled default catalog
    script._use_tag_catalog = False
    assert script._format_catalog_status() == "**OK:** Bundled default catalog"

    # Enabled but no catalog loaded
    script._use_tag_catalog = True
    script._catalog = None
    assert script._format_catalog_status().startswith("**Failed:**")

    # Load valid catalog
    cat_file = tmp_path / "danbooru_tags.csv"
    cat_file.write_text("tag,category,count,alias\n1girl,0,100,\n", encoding="utf-8")
    monkeypatch.setattr(script, "_resolve_catalog_path", lambda: str(cat_file))
    ok, msg = script._load_tag_catalog()
    assert ok
    assert msg.startswith("**OK:**")

    # Import failure has prefix
    ok, msg = script._import_custom_catalog(uploaded=None, path_hint="../../nonexistent.csv")
    assert not ok
    assert msg.startswith("**Failed:**")


def test_add_counts_ignore_preexisting_duplicates(monkeypatch, tmp_path):
    ranbooru = _get_ranbooru()
    script = ranbooru.Script()

    p_file = tmp_path / "personal_remove.txt"
    p_file.write_text("a\na\nb\n", encoding="utf-8")
    monkeypatch.setattr(ranbooru, "PERSONAL_REMOVE_FILE", str(p_file))

    res = script._ui_add_personal_tags("c, a")
    val = getattr(res[-1], "value", None) or (
        res[-1].get("value") if isinstance(res[-1], dict) else None
    )
    assert val == "Added 1 tag (1 already present)."
    assert script._read_list_file(str(p_file)) == ["a", "b", "c"]


def test_user_list_spec_rejects_unknown_key():
    ranbooru = _get_ranbooru()
    script = ranbooru.Script()
    with pytest.raises(KeyError):
        script._user_list_spec("nope")
