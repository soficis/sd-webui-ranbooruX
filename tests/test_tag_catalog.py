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
    assert diag["mode"] == "legacy"


def test_bundled_catalog_exists():
    import scripts.ranbooru as ranbooru

    assert Path(ranbooru.BUNDLED_CATALOG_PATH).is_file()


def test_resolve_catalog_path_bundled(tmp_path):
    import scripts.ranbooru as ranbooru

    script = _make_script(tmp_path)
    script._catalog_source = "bundled"
    script._tag_catalog_path = ""
    assert script._resolve_catalog_path() == ranbooru.BUNDLED_CATALOG_PATH


def test_resolve_catalog_path_custom(tmp_path):
    script = _make_script(tmp_path)
    custom_path = str(tmp_path / "custom.csv")
    script._catalog_source = "custom"
    script._custom_catalog_path = custom_path
    assert script._resolve_catalog_path() == custom_path


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


def test_config_migration_v1_to_v2(tmp_path):
    import scripts.ranbooru as ranbooru

    catalog_path = _write_catalog(tmp_path)
    cfg = Path(ranbooru.TAG_CATALOG_CONFIG_FILE)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        json.dumps({"enabled": True, "path": str(catalog_path)}),
        encoding="utf-8",
    )
    script = ranbooru.Script()
    assert script._catalog_source == "custom"
    assert script._custom_catalog_path == str(catalog_path)
