import json

import pytest

from ranboorux.user_store import (
    UserStoreError,
    append_prompt_log,
    append_text_log,
    atomic_write_text,
    clear_gelbooru_credentials,
    load_catalog_preferences,
    load_gelbooru_credentials,
    read_list_file,
    save_catalog_preferences,
    save_gelbooru_credentials,
    write_list_file,
)


def test_credentials_operations(tmp_path):
    cred_file = tmp_path / "credentials.json"

    # 1. Missing file
    assert load_gelbooru_credentials(cred_file) is None

    # 2. Corrupt JSON
    cred_file.write_text("{invalid json", encoding="utf-8")
    with pytest.raises(UserStoreError):
        load_gelbooru_credentials(cred_file)

    # 3. Successful save & load
    save_gelbooru_credentials(cred_file, "my_api_key", "my_user_id")
    loaded = load_gelbooru_credentials(cred_file)
    assert loaded == {"api_key": "my_api_key", "user_id": "my_user_id"}

    # 4. Empty/invalid inputs
    with pytest.raises(ValueError):
        save_gelbooru_credentials(cred_file, "", "user")
    with pytest.raises(ValueError):
        save_gelbooru_credentials(cred_file, "key", "")

    # 5. Clear credentials
    clear_gelbooru_credentials(cred_file)
    assert cred_file.exists() is False


def test_list_file_operations(tmp_path):
    list_file = tmp_path / "list.txt"

    # 1. Missing file
    assert read_list_file(list_file) == []

    # 2. Duplicate entries & empty data & normalization
    tags = ["  1girl ", "blonde_hair", "1girl", "  ", "blue_eyes"]
    write_list_file(list_file, tags)

    read_tags = read_list_file(list_file)
    # Check that duplicates were removed and whitespace stripped
    assert read_tags == ["1girl", "blonde_hair", "blue_eyes"]

    # 3. Write with custom normalization
    def dummy_norm(val):
        return val.replace("_", " ").strip().lower()

    write_list_file(list_file, tags, normalize_fn=dummy_norm)
    # Normalized: 1girl (exact match), blonde hair (exact match), blue eyes (exact match)
    # The saved tags keep original characters but deduped on normalized key
    read_tags_norm = read_list_file(list_file, normalize_fn=dummy_norm)
    assert read_tags_norm == ["1girl", "blonde_hair", "blue_eyes"]


def test_prompt_log_append(tmp_path):
    log_file = tmp_path / "prompt_sources.jsonl"

    # 1. Append to missing file (creates it)
    payload1 = {"prompt": "1girl", "seed": 123}
    append_prompt_log(log_file, payload1)

    # 2. Append multiple entries
    payload2 = {"prompt": "2girls", "seed": 456}
    append_prompt_log(log_file, payload2)

    # Verify contents
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == payload1
    assert json.loads(lines[1]) == payload2

    append_text_log(tmp_path / "prompt_sources.txt", ["---", "prompt=1girl"])
    assert (tmp_path / "prompt_sources.txt").read_text(encoding="utf-8").splitlines() == [
        "---",
        "prompt=1girl",
    ]


def test_catalog_preferences(tmp_path):
    pref_file = tmp_path / "tag_catalog.json"

    # 1. Missing file (returns defaults)
    defaults = load_catalog_preferences(pref_file)
    assert defaults == {"enabled": True, "source": "bundled", "custom_path": ""}

    # 2. Corrupt JSON
    pref_file.write_text("not json", encoding="utf-8")
    with pytest.raises(UserStoreError):
        load_catalog_preferences(pref_file)

    # 3. Save and load current preferences
    save_catalog_preferences(
        pref_file,
        enabled=False,
        source="custom",
        custom_path="/path/to/custom",
    )
    loaded = load_catalog_preferences(pref_file)
    assert loaded == {"enabled": False, "source": "custom", "custom_path": "/path/to/custom"}


def test_atomic_write_cleanup(tmp_path):
    target = tmp_path / "sub" / "target.txt"

    # Trigger write error on directory permission issues or mock failures
    # By making the directory a file, we cause directory creation to fail
    tmp_path.joinpath("sub").write_text("blocking file")

    with pytest.raises(UserStoreError):
        atomic_write_text(target, "some content")

    # Check that no temporary files were left behind in the parent directory
    temp_files = list(tmp_path.glob(".ranboorux_tmp_*"))
    assert len(temp_files) == 0
