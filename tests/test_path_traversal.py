import builtins
import os
from pathlib import Path


def _make_script():
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()
    script._use_tag_catalog = False
    return script


def test_remove_file_traversal_refused(tmp_path, monkeypatch):
    outside_file = tmp_path / "outside_remove.txt"
    outside_file.write_text("evil_tag1, evil_tag2", encoding="utf-8")

    opened_files = []
    real_open = builtins.open

    def spy_open(path, *args, **kwargs):
        opened_files.append(str(path))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)

    script = _make_script()
    # Test absolute escape
    tags = script._read_remove_file(str(outside_file))
    assert tags == []
    assert str(outside_file) not in opened_files

    # Test walkout
    walkout = "../../outside_remove.txt"
    tags_walkout = script._read_remove_file(walkout)
    assert tags_walkout == []
    assert not any(Path(f).resolve() == outside_file.resolve() for f in opened_files)


def test_remove_file_valid(tmp_path, monkeypatch):
    import scripts.ranbooru as ranbooru

    remove_dir = tmp_path / "remove"
    remove_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ranbooru, "USER_REMOVE_DIR", str(remove_dir))

    valid_file = remove_dir / "clean_remove.txt"
    valid_file.write_text("bad_tag1, bad_tag2", encoding="utf-8")

    script = _make_script()
    tags = script._read_remove_file("clean_remove.txt")
    assert tags == ["bad_tag1", "bad_tag2"]


def test_search_file_traversal_refused(tmp_path, monkeypatch):
    outside_file = tmp_path / "outside_search.txt"
    outside_file.write_text("evil_search1\nevil_search2\n", encoding="utf-8")

    opened_files = []
    real_open = builtins.open

    def spy_open(path, *args, **kwargs):
        opened_files.append(str(path))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)

    script = _make_script()
    lines = script._read_search_file(str(outside_file))
    assert lines == []
    assert str(outside_file) not in opened_files


def test_search_file_valid(tmp_path, monkeypatch):
    import scripts.ranbooru as ranbooru

    search_dir = tmp_path / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ranbooru, "USER_SEARCH_DIR", str(search_dir))

    valid_file = search_dir / "clean_search.txt"
    valid_file.write_text("search_line_1\nsearch_line_2\n", encoding="utf-8")

    script = _make_script()
    lines = script._read_search_file("clean_search.txt")
    assert lines == ["search_line_1", "search_line_2"]


def test_lora_folder_traversal_refused(tmp_path, monkeypatch):
    from modules import shared

    lora_root = tmp_path / "models" / "lora"
    lora_root.mkdir(parents=True, exist_ok=True)

    class DummyCmdOpts:
        lora_dir = str(lora_root)

    monkeypatch.setattr(shared, "cmd_opts", DummyCmdOpts(), raising=False)

    script = _make_script()

    # Absolute escape
    outside_folder = tmp_path / "outside_lora"
    outside_folder.mkdir()
    res = script._resolve_lora_target_folder(str(outside_folder))
    assert res == ""

    # Walkout escape
    res_walkout = script._resolve_lora_target_folder("../../outside_lora")
    assert res_walkout == ""

    # Ensure scan does not list outside directory
    listdir_calls = []
    real_listdir = os.listdir

    def spy_listdir(path):
        listdir_calls.append(str(path))
        return real_listdir(path)

    monkeypatch.setattr(os, "listdir", spy_listdir)

    scan = script._scan_loranado_candidates("../../outside_lora")
    assert scan["all_files"] == []
    assert not any(str(outside_folder) in p for p in listdir_calls)


def test_lora_folder_valid_nested(tmp_path, monkeypatch):
    from modules import shared

    lora_root = tmp_path / "models" / "lora"
    sub_folder = lora_root / "character"
    sub_folder.mkdir(parents=True, exist_ok=True)

    class DummyCmdOpts:
        lora_dir = str(lora_root)

    monkeypatch.setattr(shared, "cmd_opts", DummyCmdOpts(), raising=False)

    script = _make_script()
    resolved = script._resolve_lora_target_folder("character")
    assert resolved == str(sub_folder.resolve())


def test_lora_ui_status_strings_echo_basename_only(tmp_path, monkeypatch):
    from modules import shared

    lora_root = tmp_path / "models" / "lora"
    sub_folder = lora_root / "secret_subfolder"
    sub_folder.mkdir(parents=True, exist_ok=True)

    dummy_lora = sub_folder / "test.safetensors"
    dummy_lora.write_bytes(b"dummy")

    class DummyCmdOpts:
        lora_dir = str(lora_root)

    monkeypatch.setattr(shared, "cmd_opts", DummyCmdOpts(), raising=False)

    script = _make_script()
    scan = script._scan_loranado_candidates("secret_subfolder")
    assert str(lora_root) not in scan["message"]
