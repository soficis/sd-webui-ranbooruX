def _make_script():
    import scripts.ranbooru as ranbooru

    return ranbooru.Script()


def test_utf8_round_trip_japanese(tmp_path):
    script = _make_script()
    path = tmp_path / "jp.txt"
    tags = ["東方", "魔法少女", "水着", "english_tag"]
    script._write_list_file(str(path), tags)
    assert script._read_list_file(str(path)) == tags


def test_utf8_round_trip_symbols(tmp_path):
    script = _make_script()
    path = tmp_path / "symbols.txt"
    tags = ["tag_one", "x/y", "a+b", "score:>=10"]
    script._write_list_file(str(path), tags)
    assert script._read_list_file(str(path)) == tags


def test_read_empty_file(tmp_path):
    script = _make_script()
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    assert script._read_list_file(str(path)) == []


def test_windows_newlines(tmp_path):
    script = _make_script()
    path = tmp_path / "windows.txt"
    path.write_text("one\r\ntwo\r\nthree\r\n", encoding="utf-8")
    assert script._read_list_file(str(path)) == ["one", "two", "three"]


def test_no_trailing_newline(tmp_path):
    script = _make_script()
    path = tmp_path / "no_trailing.txt"
    path.write_text("one\ntwo\nthree", encoding="utf-8")
    assert script._read_list_file(str(path)) == ["one", "two", "three"]


def test_atomic_write(tmp_path):
    script = _make_script()
    path = tmp_path / "atomic.txt"
    script._write_list_file(str(path), ["alpha", "beta"])
    assert path.read_text(encoding="utf-8") == "alpha\nbeta"


def test_atomic_write_overwrite(tmp_path):
    script = _make_script()
    path = tmp_path / "atomic_overwrite.txt"
    script._write_list_file(str(path), ["one", "two"])
    script._write_list_file(str(path), ["three"])
    assert script._read_list_file(str(path)) == ["three"]
