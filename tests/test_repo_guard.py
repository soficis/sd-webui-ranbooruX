from tools import repo_guard


def test_repo_guard_is_not_applicable_without_git_metadata(tmp_path, capsys):
    files = repo_guard.get_files_to_check(tmp_path, [])

    captured = capsys.readouterr()
    assert files == []
    assert "not applicable in source release" in captured.out


def test_repo_guard_explicit_paths_still_checked_without_git_metadata(tmp_path):
    files = repo_guard.get_files_to_check(tmp_path, ["scripts/ranbooru.py"])

    assert files == ["scripts/ranbooru.py"]
