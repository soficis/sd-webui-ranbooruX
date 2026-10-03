import logging
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


def test_gelbooru_ui_save_clears_textboxes_and_hides_path(tmp_path, monkeypatch):
    import scripts.ranbooru as ranbooru

    cred_file = tmp_path / "credentials.json"
    monkeypatch.setattr(ranbooru, "GELBOORU_CREDENTIALS_FILE", str(cred_file))

    script = ranbooru.Script()
    status, cred_grp, clear_btn, key_tb, uid_tb = script._ui_save_gelbooru_credentials(
        "my_secret_key", "my_uid"
    )

    # API key and user ID textboxes must be cleared
    assert key_tb.get("value") == ""
    assert uid_tb.get("value") == ""

    # Status message must not contain secret or file path
    status_text = status.get("value", "")
    assert "my_secret_key" not in status_text
    assert str(cred_file) not in status_text
    assert "credentials.json" not in status_text


def test_secret_scanner_configured_in_precommit_and_ci():
    precommit = Path(".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "gitleaks" in precommit

    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "gitleaks" in ci
    assert "continue-on-error: true" in ci


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

    # Case 2: Non-zero exit code returned by launch.run_pip
    def mock_fail_code(cmd, desc):
        return 1

    monkeypatch.setattr(install.launch, "run_pip", mock_fail_code)
    install._install_req(str(req_file), "test package")

    captured = capsys.readouterr()
    assert (
        "[RanbooruX] ERROR: Pip installation of test package failed with exit code 1"
        in captured.err
    )

    # Case 3: Success (returns 0 or None)
    monkeypatch.setattr(install.launch, "run_pip", lambda cmd, desc: 0)
    install._install_req(str(req_file), "test package")

    captured = capsys.readouterr()
    assert captured.err == ""
