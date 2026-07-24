import json
import types

from ranboorux import requesting


def _public_dns(monkeypatch):
    monkeypatch.setattr(
        requesting.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (None, None, None, None, ("93.184.216.34", 443)),
        ],
    )


def test_redact_url_hides_credential_query_values():
    url = "https://site.test/api?api_key=secret&user_id=123&tags=1girl"

    assert requesting.redact_url(url) == (
        "https://site.test/api?api_key=<redacted>&user_id=<redacted>&tags=1girl"
    )


def test_booru_session_uses_cached_session_without_global_patch(monkeypatch):
    _public_dns(monkeypatch)
    calls = []

    class FakeCachedSession:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

        def get(self, *_args, **_kwargs):
            return types.SimpleNamespace(
                status_code=200,
                headers={"content-type": "image/png"},
                content=b"ok",
                raise_for_status=lambda: None,
                close=lambda: None,
            )

    fake_cache = types.SimpleNamespace(
        CachedSession=FakeCachedSession,
        install_cache=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("global install_cache should not be called")
        ),
    )
    monkeypatch.setattr(requesting, "requests_cache", fake_cache)

    session = requesting.BooruSession(use_cache=True)

    assert isinstance(session._session, FakeCachedSession)
    assert calls


def test_get_bytes_rejects_large_response(monkeypatch):
    _public_dns(monkeypatch)

    class FakeSession:
        def get(self, *_args, **_kwargs):
            return types.SimpleNamespace(
                status_code=200,
                headers={"content-type": "image/png"},
                content=b"12345",
                raise_for_status=lambda: None,
                close=lambda: None,
            )

    monkeypatch.setattr(requesting.requests, "Session", lambda: FakeSession())
    session = requesting.BooruSession(use_cache=False)

    try:
        session.get_bytes("https://site.test/image.png", max_bytes=4)
    except requesting.ResponseTooLargeError as exc:
        assert "exceeded 4 bytes" in str(exc)
    else:
        raise AssertionError("expected ResponseTooLargeError")


def test_get_rejects_private_ip_before_request(monkeypatch):
    calls = []

    class FakeSession:
        def get(self, *_args, **_kwargs):
            calls.append(True)
            return types.SimpleNamespace(status_code=200, headers={})

    monkeypatch.setattr(requesting.requests, "Session", lambda: FakeSession())
    session = requesting.BooruSession(use_cache=False)

    try:
        session.get("http://127.0.0.1/private")
    except requesting.UnsafeUrlError:
        pass
    else:
        raise AssertionError("expected UnsafeUrlError")

    assert calls == []


def test_validate_outbound_url_rejects_carrier_grade_nat():
    try:
        requesting.validate_outbound_url("http://100.64.0.1/api")
    except requesting.UnsafeUrlError:
        pass
    else:
        raise AssertionError("expected UnsafeUrlError")


def test_validate_outbound_url_rejects_ipv6_loopback():
    try:
        requesting.validate_outbound_url("http://[::1]/api")
    except requesting.UnsafeUrlError:
        pass
    else:
        raise AssertionError("expected UnsafeUrlError")


def test_validate_outbound_url_rejects_hostname_alias_with_private_result(monkeypatch):
    monkeypatch.setattr(
        requesting.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (None, None, None, None, ("93.184.216.34", 443)),
            (None, None, None, None, ("10.0.0.7", 443)),
        ],
    )

    try:
        requesting.validate_outbound_url("https://site.test/api")
    except requesting.UnsafeUrlError:
        pass
    else:
        raise AssertionError("expected UnsafeUrlError")


def test_connected_socket_rejects_rebound_private_peer_before_request():
    class FakeSocket:
        def __init__(self):
            self.closed = False

        def getpeername(self):
            return ("10.0.0.5", 443)

        def close(self):
            self.closed = True

    sock = FakeSocket()

    try:
        requesting._validate_connected_socket(sock)
    except requesting.UnsafeUrlError:
        pass
    else:
        raise AssertionError("expected UnsafeUrlError")

    assert sock.closed is True


def test_get_rejects_redirect_to_private_ip(monkeypatch):
    _public_dns(monkeypatch)

    class FakeSession:
        def __init__(self):
            self.calls = []

        def get(self, url, **_kwargs):
            self.calls.append(url)
            return types.SimpleNamespace(
                status_code=302,
                headers={"location": "http://127.0.0.1/private"},
                close=lambda: None,
            )

    fake = FakeSession()
    monkeypatch.setattr(requesting.requests, "Session", lambda: fake)
    session = requesting.BooruSession(use_cache=False)

    try:
        session.get("https://site.test/start")
    except requesting.UnsafeUrlError:
        pass
    else:
        raise AssertionError("expected UnsafeUrlError")

    assert fake.calls == ["https://site.test/start"]


def test_cached_session_bypasses_cache_for_sensitive_urls(monkeypatch):
    _public_dns(monkeypatch)
    cached_calls = []
    uncached_calls = []

    class FakeResponse:
        status_code = 200
        headers = {}

    class FakeCachedSession:
        def __init__(self, *_args, **_kwargs):
            pass

        def get(self, url, **_kwargs):
            cached_calls.append(url)
            return FakeResponse()

    class FakeUncachedSession:
        def get(self, url, **_kwargs):
            uncached_calls.append(url)
            return FakeResponse()

    monkeypatch.setattr(requesting.requests, "Session", lambda: FakeUncachedSession())
    monkeypatch.setattr(
        requesting,
        "requests_cache",
        types.SimpleNamespace(CachedSession=FakeCachedSession),
    )

    session = requesting.BooruSession(use_cache=True)
    session.get("https://site.test/api?api_key=secret&user_id=123")

    assert cached_calls == []
    assert uncached_calls == ["https://site.test/api?api_key=secret&user_id=123"]


def test_cached_session_bypasses_cache_for_sensitive_redirect(monkeypatch):
    _public_dns(monkeypatch)
    cached_calls = []
    uncached_calls = []

    class FakeCachedSession:
        def __init__(self, *_args, **_kwargs):
            pass

        def get(self, url, **_kwargs):
            cached_calls.append(url)
            return types.SimpleNamespace(
                status_code=302,
                headers={"location": "https://site.test/api?api_key=secret"},
                close=lambda: None,
            )

    class FakeUncachedSession:
        def get(self, url, **_kwargs):
            uncached_calls.append(url)
            return types.SimpleNamespace(status_code=200, headers={})

    monkeypatch.setattr(requesting.requests, "Session", lambda: FakeUncachedSession())
    monkeypatch.setattr(
        requesting,
        "requests_cache",
        types.SimpleNamespace(CachedSession=FakeCachedSession),
    )

    session = requesting.BooruSession(use_cache=True)
    session.get("https://site.test/start")

    assert cached_calls == ["https://site.test/start"]
    assert uncached_calls == ["https://site.test/api?api_key=secret"]


def test_get_bytes_streams_until_limit_without_materializing_full_response(monkeypatch):
    _public_dns(monkeypatch)

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "image/png"}

        def __init__(self):
            self.iterated_chunks = 0

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            del chunk_size
            for chunk in (b"1234", b"5678", b"9012"):
                self.iterated_chunks += 1
                yield chunk

        def close(self):
            return None

    response = FakeResponse()

    class FakeSession:
        def get(self, *_args, **_kwargs):
            return response

    monkeypatch.setattr(requesting.requests, "Session", lambda: FakeSession())
    session = requesting.BooruSession(use_cache=False)

    try:
        session.get_bytes("https://site.test/image.png", max_bytes=5)
    except requesting.ResponseTooLargeError:
        pass
    else:
        raise AssertionError("expected ResponseTooLargeError")

    assert response.iterated_chunks == 2


def test_get_bytes_rejects_non_image_content_type(monkeypatch):
    _public_dns(monkeypatch)

    class FakeSession:
        def get(self, *_args, **_kwargs):
            return types.SimpleNamespace(
                status_code=200,
                headers={"content-type": "text/html"},
                raise_for_status=lambda: None,
                close=lambda: None,
            )

    monkeypatch.setattr(requesting.requests, "Session", lambda: FakeSession())
    session = requesting.BooruSession(use_cache=False)

    try:
        session.get_bytes("https://site.test/not-image")
    except requesting.InvalidContentTypeError as exc:
        assert "text/html" in str(exc)
    else:
        raise AssertionError("expected InvalidContentTypeError")


def test_get_json_parses_bounded_response_with_missing_content_type(monkeypatch):
    _public_dns(monkeypatch)

    class FakeResponse:
        status_code = 200
        headers = {}
        encoding = "utf-8"

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            del chunk_size
            yield b'{"ok": true}'

        def close(self):
            return None

    class FakeSession:
        def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(requesting.requests, "Session", lambda: FakeSession())
    session = requesting.BooruSession(use_cache=False)

    assert session.get_json("https://site.test/api") == {"ok": True}


def test_get_json_rejects_declared_oversized_response_before_parsing(monkeypatch):
    _public_dns(monkeypatch)

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json", "content-length": "99"}

        def raise_for_status(self):
            return None

        def json(self):
            raise AssertionError("raw response json parser should not be called")

        def close(self):
            return None

    class FakeSession:
        def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(requesting.requests, "Session", lambda: FakeSession())
    session = requesting.BooruSession(use_cache=False)

    try:
        session.get_json("https://site.test/api", max_bytes=10)
    except requesting.ResponseTooLargeError:
        pass
    else:
        raise AssertionError("expected ResponseTooLargeError")


def test_get_json_rejects_chunked_oversized_response(monkeypatch):
    _public_dns(monkeypatch)

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        iterated_chunks = 0

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            del chunk_size
            for chunk in (b"12345", b"67890"):
                self.iterated_chunks += 1
                yield chunk

        def close(self):
            return None

    response = FakeResponse()

    class FakeSession:
        def get(self, *_args, **_kwargs):
            return response

    monkeypatch.setattr(requesting.requests, "Session", lambda: FakeSession())
    session = requesting.BooruSession(use_cache=False)

    try:
        session.get_json("https://site.test/api", max_bytes=6)
    except requesting.ResponseTooLargeError:
        pass
    else:
        raise AssertionError("expected ResponseTooLargeError")

    assert response.iterated_chunks == 2


def test_get_json_rejects_non_json_content_type(monkeypatch):
    _public_dns(monkeypatch)

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html"}

        def raise_for_status(self):
            return None

        def close(self):
            return None

    class FakeSession:
        def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(requesting.requests, "Session", lambda: FakeSession())
    session = requesting.BooruSession(use_cache=False)

    try:
        session.get_json("https://site.test/api")
    except requesting.InvalidContentTypeError:
        pass
    else:
        raise AssertionError("expected InvalidContentTypeError")


def test_get_json_surfaces_invalid_json(monkeypatch):
    _public_dns(monkeypatch)

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            del chunk_size
            yield b"{not-json"

        def close(self):
            return None

    class FakeSession:
        def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(requesting.requests, "Session", lambda: FakeSession())
    session = requesting.BooruSession(use_cache=False)

    try:
        session.get_json("https://site.test/api")
    except ValueError:
        pass
    else:
        raise AssertionError("expected JSON parse error")


def test_redact_url_mixed_case_and_percent_encoding():
    url1 = "https://site.test/api?X-Amz-Signature=secret123&X-goog-Credential=secret456&sig=secret789&normal=hello"
    redacted1 = requesting.redact_url(url1)
    assert "secret123" not in redacted1
    assert "secret456" not in redacted1
    assert "secret789" not in redacted1
    assert "X-Amz-Signature=<redacted>" in redacted1
    assert "X-goog-Credential=<redacted>" in redacted1
    assert "sig=<redacted>" in redacted1
    assert "normal=hello" in redacted1

    url2 = "https://site.test/api?api_key=secret%20key&password=hello%26world"
    redacted2 = requesting.redact_url(url2)
    assert "secret%20key" not in redacted2
    assert "hello%26world" not in redacted2
    assert "api_key=<redacted>" in redacted2
    assert "password=<redacted>" in redacted2


def test_exception_sanitization_mixed_content():
    exc_text = (
        "Error accessing file E:\\private\\forge\\extensions\\sd_forge_controlnet "
        "when calling https://cdn.test/foo?X-Amz-Signature=supersecret&normal=param"
    )
    sanitized = requesting.sanitize_exception_text(exc_text)
    assert "E:\\private" not in sanitized
    assert "supersecret" not in sanitized
    assert "<redacted-path>" in sanitized
    assert "X-Amz-Signature=<redacted>" in sanitized
    assert "normal=param" in sanitized


def test_cache_redirect_history_purged(monkeypatch):
    _public_dns(monkeypatch)

    class FakeResponse:
        def __init__(self, status_code, headers):
            self.status_code = status_code
            self.headers = headers

        def close(self):
            pass

    db = {}

    class MockBaseCache:
        def __init__(self):
            pass

        def get_response(self, key):
            return None

        def save_response(self, key, response, *args, **kwargs):
            pass

        def delete(self, key):
            if key in db:
                del db[key]

        def has_url(self, url):
            return url in db

        def contains(self, url):
            return url in db

        def urls(self):
            return list(db.keys())

    class FakeCachedSession:
        def __init__(self, *args, **kwargs):
            self.cache = MockBaseCache()

        def get(self, url, **kwargs):
            db[url] = True
            if url == "https://site.test/start":
                return FakeResponse(302, {"location": "https://site.test/redirect"})
            elif url == "https://site.test/redirect":
                return FakeResponse(
                    302, {"location": "https://site.test/api?X-Amz-Signature=secret"}
                )
            return FakeResponse(200, {})

        def delete(self, url):
            self.cache.delete(url)

    class FakeUncachedSession:
        def get(self, url, **kwargs):
            return FakeResponse(200, {})

    monkeypatch.setattr(requesting.requests, "Session", lambda: FakeUncachedSession())
    monkeypatch.setattr(
        requesting,
        "requests_cache",
        types.SimpleNamespace(CachedSession=FakeCachedSession),
    )

    session = requesting.BooruSession(use_cache=True)
    session.get("https://site.test/start")

    assert not session._session.cache.contains("https://site.test/start")
    assert not session._session.cache.contains("https://site.test/redirect")
    assert not session._session.cache.contains("https://site.test/api?X-Amz-Signature=secret")


def test_sanitize_exception_invalid_url_with_secrets_and_paths():
    from requests.exceptions import InvalidURL

    windows_path = "E:" + "\\private\\forge\\extensions\\sd_forge_controlnet"
    posix_path = "/home/user/forge/extensions/sd-webui-controlnet"
    unc_path = "\\\\server\\share\\path\\to\\extensions"
    file_path = "file:" + "///C:/Users/fanph/secret_extension"
    signed_url = "https://cdn.test/foo?sig=secret123&x-amz-signature=amzsecret"

    err_msg = (
        f"Invalid URL: {windows_path} and {posix_path} and {unc_path} "
        f"and {file_path} with signed URL {signed_url}"
    )

    exc = InvalidURL(err_msg)

    sanitized_exc = requesting.sanitize_exception(exc)

    assert isinstance(sanitized_exc, RuntimeError)
    message = str(sanitized_exc)

    assert windows_path not in message
    assert posix_path not in message
    assert unc_path not in message
    assert file_path not in message
    assert "secret123" not in message
    assert "amzsecret" not in message


def test_get_json_parser_failure_contains_sanitized_error(monkeypatch):
    _public_dns(monkeypatch)

    windows_path = "E:" + "\\private\\forge\\extensions\\sd_forge_controlnet"
    file_path = "file:" + "///C:/Users/fanph/secret_extension"
    signed_url = "https://cdn.test/foo?sig=secret123"

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            del chunk_size
            yield b"{}"

        def close(self):
            return None

    class FakeSession:
        def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(requesting.requests, "Session", lambda: FakeSession())
    session = requesting.BooruSession(use_cache=False)

    def mock_loads(*_args, **_kwargs):
        raise json.JSONDecodeError(
            f"Expecting value in document containing {windows_path} and {file_path} and {signed_url}",
            "{}",
            0,
        )

    monkeypatch.setattr(requesting.json, "loads", mock_loads)

    try:
        session.get_json("https://site.test/api")
    except requesting.BooruResponseError as exc:
        message = str(exc)
        assert exc.__cause__ is not None
        assert isinstance(exc.__cause__, json.JSONDecodeError)
    else:
        raise AssertionError("expected BooruResponseError")

    assert windows_path not in message
    assert file_path not in message
    assert "secret123" not in message
    assert "<redacted-path>" in message


def test_path_redaction_with_spaces():
    windows_path = "C:" + "\\Users\\user profile\\Private Folder\\file.py"
    unc_path = "\\\\server\\share name\\folder\\file.py"
    posix_path = "/home/user/Private Folder/file.py"
    file_path = "file:" + "///C:/Users/user/Private Folder/file.py"

    assert "user profile" not in requesting.sanitize_exception_text(
        "Error C:\\Users\\user profile\\Private Folder\\file.py."
    )
    assert "share name" not in requesting.sanitize_exception_text(
        "Error \\\\server\\share name\\folder\\file.py."
    )
    assert "Private Folder" not in requesting.sanitize_exception_text(
        "Error /home/user/Private Folder/file.py."
    )
    assert "Private Folder" not in requesting.sanitize_exception_text(
        "Error file:" + "///C:/Users/user/Private Folder/file.py."
    )

    signed_url = "https://cdn.test/foo?sig=secret123&x-amz-signature=amzsecret"
    mixed_msg = (
        f"Error accessing {windows_path} and {posix_path} and {unc_path} "
        f"and {file_path} with signed URL {signed_url}"
    )

    sanitized = requesting.sanitize_exception_text(mixed_msg)

    assert "user profile" not in sanitized
    assert "share name" not in sanitized
    assert "Private Folder" not in sanitized
    assert "secret123" not in sanitized
    assert "amzsecret" not in sanitized
    assert "<redacted-path>" in sanitized
    assert "x-amz-signature=<redacted>" in sanitized


def test_logger_handler_includes_no_secrets(monkeypatch):
    import logging
    import sys
    import types

    # Setup dummy modules to satisfy script base class lookup in ranbooru.py under test environment
    mock_modules = ["modules", "modules.scripts", "modules.shared", "modules.paths"]
    for m in mock_modules:
        if m not in sys.modules:
            sys.modules[m] = types.SimpleNamespace()
    sys.modules["modules.scripts"].Script = object

    import scripts.ranbooru as ranbooru

    records = []

    class MockHandler(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger("ranboorux")
    handler = MockHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    try:
        windows_path = "E:" + "\\private\\forge\\extensions\\sd_forge_controlnet"
        signed_url = "https://cdn.test/foo?sig=secret123"

        class MismatchedScript:
            @property
            def __class__(self):
                raise ValueError(f"Secret path: {windows_path} and URL {signed_url}")

        script = ranbooru.Script()
        script._is_adetailer_script(MismatchedScript())

        assert len(records) > 0
        for rec in records:
            msg = rec.getMessage()
            assert windows_path not in msg
            assert "secret123" not in msg

            assert not rec.exc_info

            for arg in rec.args or []:
                if isinstance(arg, Exception):
                    raise AssertionError("Raw exception object passed to logger")
                arg_str = str(arg)
                assert windows_path not in arg_str
                assert "secret123" not in arg_str
    finally:
        logger.removeHandler(handler)
