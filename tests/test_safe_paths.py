import os
import sys
from pathlib import Path

import pytest

from ranboorux.safe_paths import contained_path, safe_join


def test_valid_nested_path(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    child = root / "subdir" / "target.csv"
    child.parent.mkdir()
    child.write_text("data")

    res = contained_path(root, child)
    assert res == child.resolve()
    assert isinstance(res, Path)


def test_absolute_path_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("outside")

    with pytest.raises(ValueError, match="outside"):
        contained_path(root, outside)


def test_dot_dot_walkout(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    escape_path = str(root / ".." / "outside.csv")

    with pytest.raises(ValueError):
        contained_path(root, escape_path)


def test_sibling_prefix_trap(tmp_path):
    root = tmp_path / "catalogs"
    root.mkdir()
    sibling = tmp_path / "catalogs_evil"
    sibling.mkdir()
    evil_file = sibling / "target.csv"
    evil_file.write_text("evil")

    with pytest.raises(ValueError):
        contained_path(root, evil_file)


def test_target_equals_root_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError, match="strictly below"):
        contained_path(root, root)


def test_empty_string_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError):
        contained_path(root, "")
    with pytest.raises(ValueError):
        contained_path(root, "   ")
    with pytest.raises(ValueError):
        contained_path("", root)


def test_embedded_nul_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError):
        contained_path(root, "file\0name.csv")


def test_safe_join_basic(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    target = root / "sub" / "file.csv"
    target.parent.mkdir()
    target.write_text("ok")

    res = safe_join(root, "sub", "file.csv")
    assert res == target.resolve()


def test_safe_join_rejects_absolute_parts(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    abs_part = "/etc/passwd" if os.name != "nt" else "C:\\Windows\\win.ini"

    with pytest.raises(ValueError):
        safe_join(root, abs_part)


def test_safe_join_rejects_walkout(tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError):
        safe_join(root, "..", "escape.csv")


def test_symlink_pointing_outside(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("secret")

    link = root / "link_to_outside.csv"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation requires elevated privilege or unsupported on OS")

    with pytest.raises(ValueError):
        contained_path(root, link)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows drive test")
def test_different_drive_win32():
    # If on C:, test D:, or vice versa
    curr_drive = Path.cwd().drive.upper()
    other_drive = "D:" if curr_drive != "D:" else "C:"
    root = Path(f"{curr_drive}\\test_root")
    candidate = Path(f"{other_drive}\\some_file.csv")

    with pytest.raises(ValueError):
        contained_path(root, candidate)


def test_trailing_dot_or_space_windows(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    # On Windows, "file.csv." or "file.csv " is resolved by OS to "file.csv" or rejected
    # contained_path should handle it safely without escaping root
    candidate = str(root / "file.csv.")
    try:
        res = contained_path(root, candidate)
        # If accepted, must be strictly under root
        assert os.path.commonpath([str(root.resolve()), str(res)]) == str(root.resolve())
    except ValueError:
        pass  # Also valid if rejected
