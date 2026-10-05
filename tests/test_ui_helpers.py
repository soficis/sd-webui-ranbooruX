from pathlib import Path

from ranboorux.ui_helpers import format_list_status, next_rating, read_uploaded_text, upload_to_path


class DummyNamedFile:
    def __init__(self, name: str):
        self.name = name


def test_upload_to_path_str():
    assert upload_to_path("foo/bar.txt") == "foo/bar.txt"


def test_upload_to_path_pathlib():
    p = Path("foo/bar.txt")
    assert upload_to_path(p) == str(p)


def test_upload_to_path_dict():
    assert upload_to_path({"name": " /path/to/file.csv "}) == "/path/to/file.csv"
    assert upload_to_path({"path": "/path/to/file.csv"}) == "/path/to/file.csv"
    assert upload_to_path({"orig_name": "file.csv"}) == "file.csv"
    assert upload_to_path({"other": "ignore"}) == ""


def test_upload_to_path_named_object():
    obj = DummyNamedFile("/tmp/upload.txt")
    assert upload_to_path(obj) == "/tmp/upload.txt"


def test_upload_to_path_invalid():
    assert upload_to_path(None) == ""
    assert upload_to_path(12345) == ""


def test_read_uploaded_text_success(tmp_path: Path):
    f = tmp_path / "tags.txt"
    f.write_text("tag1, tag2\ntag3", encoding="utf-8")
    text, err = read_uploaded_text(str(f))
    assert err is None
    assert text == "tag1, tag2\ntag3"


def test_read_uploaded_text_strips_bom(tmp_path: Path):
    f = tmp_path / "tags_bom.txt"
    f.write_text("tag1, tag2", encoding="utf-8-sig")
    text, err = read_uploaded_text(str(f))
    assert err is None
    assert text == "tag1, tag2"
    assert not text.startswith("\ufeff")


def test_read_uploaded_text_too_large(tmp_path: Path):
    f = tmp_path / "large.txt"
    f.write_bytes(b"x" * (1024 * 1024 + 1))
    text, err = read_uploaded_text(str(f))
    assert err is not None
    assert "large" in err.lower() or "size" in err.lower() or "limit" in err.lower()
    assert text == ""


def test_read_uploaded_text_missing_file(tmp_path: Path):
    f = tmp_path / "nonexistent.txt"
    text, err = read_uploaded_text(str(f))
    assert err is not None
    assert "not found" in err.lower() or "missing" in err.lower() or "error" in err.lower()
    assert text == ""


def test_read_uploaded_text_empty_path():
    text, err = read_uploaded_text("")
    assert err is not None
    assert text == ""


def test_next_rating():
    single_choices = ["All", "Safe", "Sensitive", "Questionable", "Explicit"]
    full_choices = ["All", "Safe", "Questionable", "Explicit"]
    none_choices = ["All"]

    # Kept when available
    assert next_rating("Safe", single_choices) == "Safe"
    assert next_rating("Safe", full_choices) == "Safe"
    assert next_rating("Questionable", full_choices) == "Questionable"
    assert next_rating("Explicit", full_choices) == "Explicit"

    # Sensitive falls back to Safe when Safe available in full
    assert next_rating("Sensitive", full_choices) == "Safe"

    # Sensitive falls back to All on none
    assert next_rating("Sensitive", none_choices) == "All"
    # Safe falls back to All on none
    assert next_rating("Safe", none_choices) == "All"

    # "All" stays "All"
    assert next_rating("All", full_choices) == "All"
    assert next_rating("All", single_choices) == "All"
    assert next_rating("All", none_choices) == "All"

    # None / Unknown falls back to "All"
    assert next_rating(None, full_choices) == "All"
    assert next_rating("Unknown", full_choices) == "All"


def test_format_list_status():
    # add
    assert format_list_status("add", added=3, skipped=2) == "Added 3 tags (2 already present)."
    assert format_list_status("add", added=1, skipped=0) == "Added 1 tag."
    assert format_list_status("add", added=0, skipped=2) == "No new tags added (2 already present)."
    assert format_list_status("add", added=0, skipped=0) == "No tags added."

    # remove
    assert format_list_status("remove", removed=2) == "Removed 2 tags."
    assert format_list_status("remove", removed=1) == "Removed 1 tag."
    assert format_list_status("remove", removed=0) == "Nothing selected."

    # dedupe
    assert format_list_status("dedupe", removed=4) == "Removed 4 duplicates."
    assert format_list_status("dedupe", removed=1) == "Removed 1 duplicate."
    assert format_list_status("dedupe", removed=0) == "No duplicates found."

    # import
    assert (
        format_list_status("import", added=12, skipped=0, filename="tags.txt")
        == "Imported 12 tags from tags.txt."
    )
    assert (
        format_list_status("import", added=12, skipped=3, filename="tags.txt")
        == "Imported 12 tags from tags.txt (3 already present)."
    )
    assert (
        format_list_status("import", added=1, skipped=0, filename="tags.txt")
        == "Imported 1 tag from tags.txt."
    )
    assert (
        format_list_status("import", added=0, skipped=0, filename="tags.txt")
        == "No tags found to import from tags.txt."
    )
    assert (
        format_list_status("import", error="File too large") == "Failed to import: File too large"
    )
