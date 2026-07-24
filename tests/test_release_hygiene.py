import os

from tools import build_release


def test_release_allowlist_excludes_internal_docs(tmp_path):
    src = tmp_path / "src"
    stage = tmp_path / "stage"
    allowed = [
        "README.md",
        "docs/usage.md",
        "docs/CHANGELOG.md",
        "docs/CONFIG.md",
        "docs/handoff/GEMINI_HANDOFF.md",
        "docs/joblog.txt",
        "docs/ranbooru backup.py",
        "docs/ranbooru_fix_bundle/ranbooru.py",
    ]
    for rel_path in allowed:
        path = src / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("content", encoding="utf-8")

    build_release.copy_by_allowlist(str(src), str(stage))

    assert (stage / "README.md").exists()
    assert (stage / "docs/usage.md").exists()
    assert (stage / "docs/CHANGELOG.md").exists()
    assert (stage / "docs/CONFIG.md").exists()
    assert not (stage / "docs/handoff/GEMINI_HANDOFF.md").exists()
    assert not (stage / "docs/joblog.txt").exists()
    assert not (stage / "docs/ranbooru backup.py").exists()
    assert not (stage / "docs/ranbooru_fix_bundle/ranbooru.py").exists()


def test_release_hygiene_rejects_internal_paths_and_private_content(tmp_path):
    stage = tmp_path / "stage"
    forbidden_files = [
        "docs/joblog.txt",
        "docs/handoff/GEMINI_HANDOFF.md",
        "docs/ranbooru backup.py",
        "docs/ranbooru_fix_bundle/ranbooru.py",
    ]
    for rel_path in forbidden_files:
        path = stage / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("content", encoding="utf-8")

    zip_path = tmp_path / "dirty_paths.zip"
    build_release.build_zip(str(stage), str(zip_path))

    try:
        build_release.check_archive_hygiene(str(zip_path))
    except ValueError:
        pass
    else:
        raise AssertionError("expected release hygiene failure")


def test_release_hygiene_rejects_file_uri_and_windows_absolute_paths(tmp_path):
    stage = tmp_path / "stage"
    docs_path = stage / "docs" / "usage.md"
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text("file:" + "///v:/private/handoff.md", encoding="utf-8")
    script_path = stage / "scripts" / "ranbooru.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("MODEL_PATH = r'E:\\private\\models'", encoding="utf-8")

    zip_path = tmp_path / "dirty_content.zip"
    build_release.build_zip(str(stage), str(zip_path))

    try:
        build_release.check_archive_hygiene(str(zip_path))
    except ValueError:
        pass
    else:
        raise AssertionError("expected release hygiene failure")


def test_release_builder_self_test_keeps_staging_paths_relative(tmp_path):
    src = tmp_path / "src"
    stage = tmp_path / "stage"
    path = src / "scripts" / "ranbooru.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("print('ok')", encoding="utf-8")

    build_release.copy_by_allowlist(str(src), str(stage))

    assert os.path.exists(stage / "scripts" / "ranbooru.py")
