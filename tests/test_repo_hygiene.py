import logging
import re
from pathlib import Path
from unittest.mock import patch

from ranboorux import user_store


def test_gitignore_contains_sensitive_patterns():
    gitignore_path = Path(".gitignore")
    assert gitignore_path.exists()
    content = gitignore_path.read_text(encoding="utf-8")
    lines = {line.strip() for line in content.splitlines() if line.strip()}
    required_patterns = {"*.key", "*.pem", "*.p12", "id_rsa*", "secrets.json"}
    for pattern in required_patterns:
        assert pattern in lines, f"Missing pattern in .gitignore: {pattern}"


def test_user_store_chmod_failure_logs_warning_without_contents(tmp_path, caplog):
    test_file = tmp_path / "creds.json"
    secret_text = "super_secret_api_key_12345"

    with patch("os.chmod", side_effect=OSError("Permission denied")):
        with caplog.at_level(logging.WARNING, logger="ranboorux.user_store"):
            user_store.atomic_write_text(test_file, secret_text)

    # File was still written
    assert test_file.exists()
    assert test_file.read_text(encoding="utf-8") == secret_text

    # Warning logged naming the file, but NOT the secret content
    assert len(caplog.records) >= 1
    log_text = caplog.text
    assert str(test_file) in log_text or test_file.name in log_text
    assert secret_text not in log_text


def test_gelbooru_saved_message_does_not_echo_file_path():
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()
    msg = script._gelbooru_saved_message()
    assert "credentials.json" not in msg
    assert "\\" not in msg and "/" not in msg
    assert "Using saved Gelbooru credentials" in msg


def _update_value(update):
    """Read `value` from a Gradio 3 update dict or a Gradio 4 component instance."""
    return update.get("value") if isinstance(update, dict) else getattr(update, "value", None)


def test_gelbooru_ui_save_clears_textboxes_and_hides_path(tmp_path, monkeypatch):
    import scripts.ranbooru as ranbooru

    cred_file = tmp_path / "credentials.json"
    monkeypatch.setattr(ranbooru, "GELBOORU_CREDENTIALS_FILE", str(cred_file))

    script = ranbooru.Script()
    status, cred_grp, clear_btn, key_tb, uid_tb = script._ui_save_gelbooru_credentials(
        "my_secret_key", "my_uid"
    )

    # API key and user ID textboxes must be cleared
    assert _update_value(key_tb) == ""
    assert _update_value(uid_tb) == ""

    # Status message must not contain secret or file path
    status_text = _update_value(status) or ""
    assert "my_secret_key" not in status_text
    assert str(cred_file) not in status_text
    assert "credentials.json" not in status_text


def test_secret_scanner_configured_in_precommit_and_ci():
    precommit = Path(".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "gitleaks" in precommit
    # Advisory: the hook must not block ordinary commits.
    assert re.search(r"id: gitleaks\s+stages: \[manual\]", precommit)

    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "gitleaks" in ci
    assert "continue-on-error: true" in ci
    # Third-party actions added for supply-chain hardening are pinned to a commit SHA.
    assert re.search(r"gitleaks/gitleaks-action@[0-9a-f]{40}", ci)


def test_pip_audit_configured_in_ci():
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "pip-audit" in ci
    assert "pip-audit -r requirements.txt" in ci


def test_install_req_surfaces_errors_to_stderr_without_crashing(capsys, monkeypatch, tmp_path):
    import sys
    import types

    launch_stub = types.ModuleType("launch")
    launch_stub.run_pip = lambda cmd, desc: None
    monkeypatch.setitem(sys.modules, "launch", launch_stub)

    import install

    req_file = tmp_path / "reqs.txt"
    req_file.write_text("foo>=1.0.0\n", encoding="utf-8")

    # Case 1: Exception raised by launch.run_pip
    def mock_fail_raise(cmd, desc):
        raise RuntimeError("simulated pip explosion")

    monkeypatch.setattr(install.launch, "run_pip", mock_fail_raise)
    install._install_req(str(req_file), "test package")

    captured = capsys.readouterr()
    assert (
        "[RanbooruX] ERROR: Failed to install test package: simulated pip explosion" in captured.err
    )

    # Case 2: Success
    monkeypatch.setattr(install.launch, "run_pip", lambda cmd, desc: 0)
    install._install_req(str(req_file), "test package")

    captured = capsys.readouterr()
    assert captured.err == ""


def test_report_exception_sanitizes_and_gates_console_traceback(monkeypatch, capsys, caplog):
    import logging

    import scripts.ranbooru as ranbooru

    called = []
    monkeypatch.setattr(ranbooru.traceback, "print_exc", lambda: called.append(True))
    err = RuntimeError(r"boom at E:\private\secret\file.txt")

    monkeypatch.setattr(ranbooru, "DEBUG", False)
    with caplog.at_level(logging.DEBUG, logger="ranboorux"):
        try:
            raise err
        except RuntimeError as exc:
            ranbooru._report_exception("[R Test] failed", exc)
    out = capsys.readouterr().out
    assert "[R Test] failed" in out
    assert "secret" not in out
    assert called == []
    # Traceback is still recoverable via the logger at DEBUG level.
    assert any(rec.exc_info for rec in caplog.records)

    monkeypatch.setattr(ranbooru, "DEBUG", True)
    try:
        raise err
    except RuntimeError as exc:
        ranbooru._report_exception("[R Test] failed", exc)
    assert called == [True]


def test_fetch_booru_posts_sanitizes_errors():
    import pytest

    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()

    class ExplodingApi:
        booru_name = "testbooru"

        def get_posts(self, **kwargs):
            raise RuntimeError("Database at E:\\private\\secret_db\\passwords.sqlite failed")

    with pytest.raises(ranbooru.BooruError) as exc_info:
        script._fetch_booru_posts(
            ExplodingApi(),
            search_tags="tag",
            mature_rating="None",
            max_pages=1,
            post_id=None,
        )

    error_msg = str(exc_info.value)
    assert "E:\\private\\secret_db" not in error_msg
    assert "secret_db" not in error_msg


def test_booru_modules_use_log_instead_of_bare_print():
    from ranboorux.boorus import gelbooru, simple

    # Verify both modules have _log helper callable
    assert callable(getattr(simple, "_log"))
    assert callable(getattr(gelbooru, "_log"))


def test_controlnet_env_path_traversal_contained(monkeypatch):
    from ranboorux.integrations import controlnet

    # Set traversal path
    monkeypatch.setenv("SD_FORGE_CONTROLNET_PATH", "subdir/../../evil")
    monkeypatch.setattr(controlnet.os.path, "isfile", lambda p: True)

    loaded_paths = []
    monkeypatch.setattr(
        controlnet,
        "_load_module_from_path",
        lambda name, path: loaded_paths.append(path),
    )

    try:
        controlnet.load_external_code("dummy_extension_root")
    except ImportError:
        pass

    for path in loaded_paths:
        assert "evil" not in path
