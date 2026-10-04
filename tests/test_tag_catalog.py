import csv
import json
import os
from pathlib import Path


def _write_catalog(tmp_path: Path) -> Path:
    rows = [
        ("1girl", 0, 1000, ""),
        ("naruto", 4, 500, "uchiwa"),
        ("copyright_tag", 3, 400, ""),
        ("speech_bubble", 0, 300, ""),
        ("blonde_hair", 0, 2000, ""),
        ("blue_hair", 0, 1500, "azure hair"),
        ("green_eyes", 0, 1200, "emerald eyes"),
    ]
    path = tmp_path / "danbooru_tags.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["tag", "category", "count", "alias"])
        writer.writerows(rows)
    return path


def _write_headerless_catalog(tmp_path: Path) -> Path:
    rows = [
        "1girl,0,1000,",
        "naruto,4,500,uchiwa",
        "blonde_hair,0,2000,",
    ]
    path = tmp_path / "danbooru_headerless.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    return path


def _make_script(tmp_path):
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()
    script._use_tag_catalog = False
    script._catalog = ranbooru.NoopCatalog()
    script._tag_catalog_diag = {}
    return script


def test_catalog_passthrough_when_disabled(tmp_path):
    script = _make_script(tmp_path)
    tags = ["1girl", "rating:s"]
    filtered, diag = script._apply_optional_catalog(
        tags,
        keep_hair_eye=True,
        drop_series=False,
        drop_characters=False,
        drop_textual=False,
    )
    assert filtered == tags
    assert diag["mode"] == "catalog"


def test_bundled_catalog_exists():
    import scripts.ranbooru as ranbooru

    assert Path(ranbooru.BUNDLED_CATALOG_PATH).is_file()


def test_resolve_catalog_path_bundled(tmp_path):
    import scripts.ranbooru as ranbooru

    script = _make_script(tmp_path)
    script._catalog_source = "bundled"
    script._tag_catalog_path = ""
    assert script._resolve_catalog_path() == ranbooru.BUNDLED_CATALOG_PATH


def test_resolve_catalog_path_custom(tmp_path, monkeypatch):
    import scripts.ranbooru as ranbooru

    fake_catalogs = tmp_path / "user" / "catalogs"
    fake_catalogs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ranbooru, "USER_CATALOGS_DIR", str(fake_catalogs))

    script = _make_script(tmp_path)
    custom_path = str(fake_catalogs / "custom.csv")
    script._catalog_source = "custom"
    script._custom_catalog_path = custom_path
    assert script._resolve_catalog_path() == str(Path(custom_path).resolve())


def test_validate_csv_valid_with_header(tmp_path):
    script = _make_script(tmp_path)
    catalog_path = _write_catalog(tmp_path)
    ok, msg = script._validate_csv_format(str(catalog_path))
    assert ok, msg


def test_validate_csv_valid_headerless(tmp_path):
    script = _make_script(tmp_path)
    catalog_path = _write_headerless_catalog(tmp_path)
    ok, msg = script._validate_csv_format(str(catalog_path))
    assert ok, msg


def test_validate_csv_invalid_2_columns(tmp_path):
    script = _make_script(tmp_path)
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("tag,count\nfoo,1\n", encoding="utf-8")
    ok, msg = script._validate_csv_format(str(bad_csv))
    assert not ok
    assert "columns" in msg.lower()


def test_catalog_filters_categories(tmp_path):
    catalog_path = _write_catalog(tmp_path)
    script = _make_script(tmp_path)

    script._use_tag_catalog = True
    script._tag_catalog_path = str(catalog_path)
    ok, msg = script._load_tag_catalog()
    assert ok, msg

    tags = ["1girl", "naruto", "copyright_tag", "speech_bubble", "rating:s"]
    filtered, diag = script._apply_optional_catalog(
        tags,
        keep_hair_eye=True,
        drop_series=True,
        drop_characters=True,
        drop_textual=True,
    )
    assert "naruto" not in filtered
    assert "copyright_tag" not in filtered
    assert "speech_bubble" not in filtered
    assert "1girl" in filtered
    dropped_reasons = {entry["reason"] for entry in diag["dropped"]}
    assert dropped_reasons.issuperset({"character", "series", "textual"})


def test_alias_normalization_hits_catalog(tmp_path):
    catalog_path = _write_catalog(tmp_path)
    script = _make_script(tmp_path)
    script._use_tag_catalog = True
    script._tag_catalog_path = str(catalog_path)
    ok, _ = script._load_tag_catalog()
    assert ok
    cache: dict[str, str] = {}
    normalized = script._normalize_cached("Uchiwa", cache)
    assert normalized == "naruto"


def test_extract_color_tags_uses_catalog_alias(tmp_path):
    catalog_path = _write_catalog(tmp_path)
    script = _make_script(tmp_path)
    script._use_tag_catalog = True
    script._tag_catalog_path = str(catalog_path)
    ok, _ = script._load_tag_catalog()
    assert ok
    hair, eyes = script._extract_color_tags("Azure Hair, emerald eyes")
    assert "blue hair" in hair
    assert "green eyes" in eyes


def test_unknown_linter_suggests(tmp_path):
    catalog_path = _write_catalog(tmp_path)
    script = _make_script(tmp_path)
    script._use_tag_catalog = True
    script._tag_catalog_path = str(catalog_path)
    ok, _ = script._load_tag_catalog()
    assert ok
    filtered, diag = script._apply_optional_catalog(
        ["blonde_heir"],
        keep_hair_eye=True,
        drop_series=False,
        drop_characters=False,
        drop_textual=False,
    )
    assert filtered == ["blonde_heir"]
    assert diag["mode"] == "catalog"
    assert diag["unknown"], "expected unknown suggestions"
    suggestions = diag["unknown"][0]["suggestions"]
    assert "blonde_hair" in suggestions


def test_import_custom_catalog(tmp_path):
    script = _make_script(tmp_path)
    catalog_path = _write_catalog(tmp_path)
    ok, msg = script._import_custom_catalog(str(catalog_path))
    assert ok, msg
    assert script._catalog_source == "custom"
    assert script._custom_catalog_path
    assert os.path.isfile(script._custom_catalog_path)


def test_legacy_catalog_config_is_not_migrated(tmp_path):
    import scripts.ranbooru as ranbooru

    catalog_path = _write_catalog(tmp_path)
    cfg = Path(ranbooru.TAG_CATALOG_CONFIG_FILE)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        json.dumps({"enabled": True, "path": str(catalog_path)}),
        encoding="utf-8",
    )
    script = ranbooru.Script()
    assert script._catalog_source == "bundled"
    assert script._custom_catalog_path == ""


def test_current_catalog_config_loads_custom_path(tmp_path):
    import scripts.ranbooru as ranbooru

    catalog_path = _write_catalog(tmp_path)
    cfg = Path(ranbooru.TAG_CATALOG_CONFIG_FILE)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        json.dumps({"enabled": True, "source": "custom", "custom_path": str(catalog_path)}),
        encoding="utf-8",
    )
    script = ranbooru.Script()
    assert script._catalog_source == "custom"
    assert script._custom_catalog_path == str(catalog_path)


class TestCatalogPathHintContainment:
    def test_absolute_hint_outside_roots_refused(self, tmp_path, monkeypatch):
        import scripts.ranbooru as ranbooru

        script = _make_script(tmp_path)
        outside_file = tmp_path / "outside.csv"
        outside_file.write_text("tag,category,count,alias\n1girl,0,10,\n", encoding="utf-8")

        validate_called = []
        monkeypatch.setattr(
            script,
            "_validate_csv_format",
            lambda p: (validate_called.append(p), (True, ""))[1],
        )

        dest_dir = Path(ranbooru.USER_CATALOGS_DIR)
        before_files = set(dest_dir.glob("*")) if dest_dir.exists() else set()

        ok, msg = script._import_custom_catalog(uploaded=None, path_hint=str(outside_file))

        assert not ok
        assert not validate_called, "Validation should NOT be called if containment fails"
        after_files = set(dest_dir.glob("*")) if dest_dir.exists() else set()
        assert after_files == before_files, "No file should be created in user/catalogs/"
        assert str(outside_file.parent) not in msg

    def test_walkout_hint_refused(self, tmp_path):
        script = _make_script(tmp_path)
        ok, msg = script._import_custom_catalog(uploaded=None, path_hint="../../evil.csv")
        assert not ok
        assert ".." not in msg

    def test_hint_inside_user_catalogs_selected_without_copy(self, tmp_path, monkeypatch):
        import shutil

        import scripts.ranbooru as ranbooru

        dest_dir = Path(ranbooru.USER_CATALOGS_DIR)
        dest_dir.mkdir(parents=True, exist_ok=True)
        local_catalog = dest_dir / "existing_local.csv"
        local_catalog.write_text("tag,category,count,alias\n1girl,0,10,\n", encoding="utf-8")

        copy_called = []
        monkeypatch.setattr(shutil, "copy2", lambda src, dst: copy_called.append((src, dst)))

        script = _make_script(tmp_path)
        ok, msg = script._import_custom_catalog(uploaded=None, path_hint=str(local_catalog))
        assert ok, msg
        assert not copy_called, "Should select in-place without copy2 (avoids SameFileError)"
        assert script._custom_catalog_path == str(local_catalog.resolve())

    def test_hint_inside_bundled_catalogs_copied(self, tmp_path):
        import pytest

        import scripts.ranbooru as ranbooru

        bundled_dir = Path(ranbooru.BUNDLED_CATALOG_DIR)
        bundled_csv = bundled_dir / "danbooru_tags.csv"
        if not bundled_csv.exists():
            pytest.skip("Bundled catalog not present")

        script = _make_script(tmp_path)
        ok, msg = script._import_custom_catalog(uploaded=None, path_hint=str(bundled_csv))
        assert ok, msg
        assert script._custom_catalog_path.startswith(
            str(Path(ranbooru.USER_CATALOGS_DIR).resolve())
        )

    def test_symlink_out_hint_refused(self, tmp_path):
        import pytest

        import scripts.ranbooru as ranbooru

        dest_dir = Path(ranbooru.USER_CATALOGS_DIR)
        dest_dir.mkdir(parents=True, exist_ok=True)
        outside_file = tmp_path / "secret.csv"
        outside_file.write_text("tag,category,count,alias\n1girl,0,10,\n", encoding="utf-8")

        symlink_path = dest_dir / "symlink_evil.csv"
        try:
            if symlink_path.exists():
                symlink_path.unlink()
            os.symlink(outside_file, symlink_path)
        except (OSError, NotImplementedError):
            pytest.skip("Symlink creation requires elevated privilege")

        script = _make_script(tmp_path)
        ok, msg = script._import_custom_catalog(uploaded=None, path_hint=str(symlink_path))
        assert not ok

    def test_persisted_evil_custom_path_ignored_on_resolve(self, tmp_path):

        script = _make_script(tmp_path)
        script._catalog_source = "custom"
        script._custom_catalog_path = "C:\\Windows\\win.ini" if os.name == "nt" else "/etc/passwd"
        resolved = script._resolve_catalog_path()
        assert resolved == ""

    def test_upload_path_without_hint_still_imports(self, tmp_path):
        script = _make_script(tmp_path)
        catalog_path = _write_catalog(tmp_path)
        ok, msg = script._import_custom_catalog(uploaded={"name": str(catalog_path)}, path_hint="")
        assert ok, msg
        assert script._catalog_source == "custom"


def test_category_consts_and_lazy_registry(tmp_path):
    import scripts.ranbooru as ranbooru
    from ranboorux.boorus.simple import Danbooru, Safebooru
    from ranboorux.tag_pipeline import (
        CHARACTER_CATEGORY,
        SERIES_CATEGORY,
        is_character_tag,
        is_series_tag,
    )

    assert SERIES_CATEGORY == 3
    assert CHARACTER_CATEGORY == 4
    assert getattr(ranbooru, "SERIES_CATEGORY") == 3
    assert getattr(ranbooru, "CHARACTER_CATEGORY") == 4

    catalog = ranbooru.CsvCatalog(_write_catalog(tmp_path))
    assert is_series_tag("copyright_tag", catalog.category) is True
    assert is_character_tag("naruto", catalog.category) is True
    assert is_series_tag("1girl", catalog.category) is False
    assert is_character_tag("1girl", catalog.category) is False

    script = _make_script(tmp_path)
    danbooru_api = script._get_booru_api("danbooru", fringe_benefits=False)
    assert isinstance(danbooru_api, Danbooru)
    safebooru_api = script._get_booru_api("safebooru", fringe_benefits=False)
    assert isinstance(safebooru_api, Safebooru)
