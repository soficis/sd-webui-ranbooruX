from __future__ import annotations

import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3 import PoolManager
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool

try:
    import requests_cache
except Exception:  # pragma: no cover - requests_cache is optional in host tests
    requests_cache = None


SENSITIVE_QUERY_PARAMS = {
    "x-amz-credential",
    "x-amz-signature",
    "x-amz-security-token",
    "x-amz-date",
    "x-goog-signature",
    "x-goog-credential",
    "signature",
    "sig",
    "token",
    "access_token",
    "authorization",
    "key",
    "api_key",
    "user_id",
    "password",
}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 5
STREAM_CHUNK_SIZE = 64 * 1024
DEFAULT_API_MAX_BYTES = 5 * 1024 * 1024


class ResponseTooLargeError(RuntimeError):
    pass


class UnsafeUrlError(ValueError):
    pass


class InvalidContentTypeError(RuntimeError):
    pass


class BooruResponseError(ValueError):
    pass


@dataclass
class BoundedResponse:
    url: str
    status_code: int
    headers: Mapping[str, str]
    content: bytes
    encoding: Optional[str] = None

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding or "utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.content.decode(self.encoding or "utf-8"))

    def raise_for_status(self) -> None:
        if 400 <= int(self.status_code) < 600:
            raise RuntimeError(f"HTTP status {self.status_code} for {redact_url(self.url)}")


def redact_url(url: object) -> str:
    text = str(url or "")
    if not text:
        return text
    try:
        parsed = urlparse(text)
        if not parsed.query:
            return text
        qsl = parse_qsl(parsed.query, keep_blank_values=True)
        new_qsl = []
        for name, value in qsl:
            if name.lower() in SENSITIVE_QUERY_PARAMS:
                new_qsl.append((name, "<redacted>"))
            else:
                new_qsl.append((name, value))

        query_parts = []
        for name, val in new_qsl:
            if val == "<redacted>":
                query_parts.append(f"{quote(name)}=<redacted>")
            else:
                query_parts.append(urlencode([(name, val)]))

        return parsed._replace(query="&".join(query_parts)).geturl()
    except Exception:
        return text


def redact_paths(text: str) -> str:
    if not text:
        return text

    idx = 0
    result = []
    n = len(text)

    def detect_prefix(pos):
        # 1. file-URI or file://
        if text[pos:].lower().startswith("file:" + "///"):
            return 8, "file"
        if text[pos:].lower().startswith("file:" + "//"):
            return 7, "file"

        # 2. UNC path starts with \\
        if text[pos:].startswith("\\\\"):
            rest = text[pos + 2 :]
            if rest and (rest[0].isalnum() or rest[0] in "._-"):
                return 2, "unc"

        # 3. Windows drive path: [a-zA-Z]:\ or [a-zA-Z]:/
        is_word_boundary = pos == 0 or not text[pos - 1].isalnum()
        if is_word_boundary and pos + 2 < n:
            if text[pos].isalpha() and text[pos + 1] == ":" and text[pos + 2] in "\\/":
                return 3, "win"

        # 4. POSIX absolute path: starts with / and not followed by /
        is_posix_boundary = pos == 0 or (not text[pos - 1].isalnum() and text[pos - 1] != "/")
        if is_posix_boundary and text[pos] == "/":
            if pos + 1 < n and text[pos + 1] == "/":
                return None
            return 1, "posix"

        return None

    while idx < n:
        prefix_info = detect_prefix(idx)
        if prefix_info is None:
            result.append(text[idx])
            idx += 1
            continue

        prefix_len, ptype = prefix_info
        start_path_idx = idx

        scan_idx = idx + prefix_len
        bracket_stack = []

        while scan_idx < n:
            char = text[scan_idx]

            # Stop on quotes, tabs, newlines
            if char in "'\"`\t\r\n":
                break

            # Stop on unmatched brackets
            if char in "([{":
                bracket_stack.append(char)
            elif char in ")]}":
                if not bracket_stack:
                    break
                top = bracket_stack.pop()
                if (
                    (char == ")" and top != "(")
                    or (char == "]" and top != "[")
                    or (char == "}" and top != "{")
                ):
                    break

            # Stop on trailing punctuation followed by space or end of string
            is_last = scan_idx + 1 == n
            next_char = text[scan_idx + 1] if not is_last else ""
            if char in ".,!?;" and (is_last or next_char.isspace()):
                break

            # Stop before another path prefix or a URL starts
            rem = text[scan_idx:]
            if rem.lower().startswith(("http://", "https://", "file:" + "//")):
                break

            is_new_path_boundary = scan_idx > 0 and text[scan_idx - 1] not in "\\/:"
            if is_new_path_boundary and rem.startswith("\\\\"):
                break

            is_rem_word_boundary = scan_idx == 0 or not text[scan_idx - 1].isalnum()
            if is_new_path_boundary and is_rem_word_boundary and len(rem) >= 3:
                if rem[0].isalpha() and rem[1] == ":" and rem[2] in "\\/":
                    break
            if (
                is_new_path_boundary
                and is_rem_word_boundary
                and rem.startswith("/")
                and not rem.startswith("//")
            ):
                break

            scan_idx += 1

        path_str = text[start_path_idx:scan_idx]
        stripped_path = path_str.rstrip()
        trailing_spaces = path_str[len(stripped_path) :]

        result.append("<redacted-path>")
        result.append(trailing_spaces)
        idx = scan_idx

    return "".join(result)


def redact_urls_in_text(text: str) -> str:
    # Find all http/https URLs in the text
    url_pattern = re.compile(r"https?://[^\s'\")]+", re.IGNORECASE)

    def repl(match):
        return redact_url(match.group(0))

    return url_pattern.sub(repl, text)


def sanitize_exception_text(text: str) -> str:
    if not text:
        return text
    # First, redact paths (so URL-like file-URI paths get redacted completely)
    text = redact_paths(text)
    # Next, redact any remaining HTTP/HTTPS URLs
    text = redact_urls_in_text(text)
    return text


def sanitize_exception(exc: Exception) -> Exception:
    if isinstance(
        exc,
        (
            UnsafeUrlError,
            ResponseTooLargeError,
            InvalidContentTypeError,
            BooruResponseError,
        ),
    ):
        return exc
    return RuntimeError(sanitize_exception_text(str(exc)))


def safe_exception_message(operation: str, url: object, exc: BaseException) -> str:
    sanitized_msg = sanitize_exception_text(str(exc))
    return f"{operation} failed for {redact_url(url)} ({exc.__class__.__name__}: {sanitized_msg})"


def _has_sensitive_query(url: object) -> bool:
    text = str(url or "")
    if not text:
        return False
    try:
        parsed = urlparse(text)
        if not parsed.query:
            return False
        qsl = parse_qsl(parsed.query, keep_blank_values=True)
        for name, _ in qsl:
            if name.lower() in SENSITIVE_QUERY_PARAMS:
                return True
    except Exception:
        pass
    return False


def _is_public_ip(address: object) -> bool:
    try:
        parsed = ipaddress.ip_address(str(address))
    except ValueError:
        return False
    return bool(
        parsed.is_global
        and not parsed.is_loopback
        and not parsed.is_link_local
        and not parsed.is_multicast
        and not parsed.is_unspecified
        and not parsed.is_reserved
    )


def _close_socket(sock: object) -> None:
    close = getattr(sock, "close", None)
    if callable(close):
        close()


def _validate_connected_socket(sock: object) -> None:
    getpeername = getattr(sock, "getpeername", None)
    if not callable(getpeername):
        return
    peer = getpeername()
    address = peer[0] if isinstance(peer, tuple) and peer else None
    if address is None:
        raise UnsafeUrlError("Connected socket has no peer address")
    if not _is_public_ip(address):
        _close_socket(sock)
        raise UnsafeUrlError(f"Connected peer resolves to a blocked address: {address}")


class _SafeHTTPConnection(HTTPConnection):
    def _new_conn(self):
        sock = super()._new_conn()
        _validate_connected_socket(sock)
        return sock


class _SafeHTTPSConnection(HTTPSConnection):
    def _new_conn(self):
        sock = super()._new_conn()
        _validate_connected_socket(sock)
        return sock


class _SafeHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = _SafeHTTPConnection


class _SafeHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = _SafeHTTPSConnection


class _SafeHTTPAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            **pool_kwargs,
        )
        self.poolmanager.pool_classes_by_scheme = {
            "http": _SafeHTTPConnectionPool,
            "https": _SafeHTTPSConnectionPool,
        }

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        manager = super().proxy_manager_for(proxy, **proxy_kwargs)
        if hasattr(manager, "pool_classes_by_scheme"):
            manager.pool_classes_by_scheme = {
                "http": _SafeHTTPConnectionPool,
                "https": _SafeHTTPSConnectionPool,
            }
        return manager


def _resolve_host(hostname: str, port: Optional[int]) -> list[str]:
    try:
        return [str(ipaddress.ip_address(hostname))]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeUrlError(f"Could not resolve outbound host: {hostname}") from exc
    addresses = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr:
            addresses.append(str(sockaddr[0]))
    if not addresses:
        raise UnsafeUrlError(f"Could not resolve outbound host: {hostname}")
    return addresses


def validate_outbound_url(url: object) -> str:
    text = str(url or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError(f"Unsupported outbound URL scheme: {parsed.scheme or '<missing>'}")
    if not parsed.hostname:
        raise UnsafeUrlError("Outbound URL is missing a host")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("Outbound URL must not contain userinfo credentials")
    addresses = _resolve_host(parsed.hostname, parsed.port)
    blocked = [address for address in addresses if not _is_public_ip(address)]
    if blocked:
        raise UnsafeUrlError(f"Outbound URL resolves to a blocked address: {parsed.hostname}")
    return text


class BooruSession:
    def __init__(self, *, use_cache: bool = False, expire_after: int = 3600):
        session_factory = getattr(requests, "Session", None)
        self._cache_enabled = bool(use_cache)
        self._uncached_session = session_factory() if callable(session_factory) else requests
        self._install_safe_adapter(self._uncached_session)
        if use_cache:
            if requests_cache is None:
                raise RuntimeError("requests-cache is required when booru request cache is enabled")
            cached_session = getattr(requests_cache, "CachedSession", None)
            if not callable(cached_session):
                raise RuntimeError("requests-cache CachedSession is unavailable")
            self._session = cached_session(
                "ranbooru_cache",
                backend="sqlite",
                expire_after=expire_after,
                allowable_codes=(200,),
            )
            self._install_safe_adapter(self._session)
            return
        self._session = self._uncached_session

    @staticmethod
    def _install_safe_adapter(session: object) -> None:
        mount = getattr(session, "mount", None)
        if callable(mount):
            adapter = _SafeHTTPAdapter()
            mount("http://", adapter)
            mount("https://", adapter)

    def _session_for_url(self, url: str):
        if self._cache_enabled and _has_sensitive_query(url):
            return self._uncached_session
        return self._session

    def get(
        self,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        timeout: int = 30,
        stream: bool = False,
    ):
        try:
            current_url = validate_outbound_url(url)
            request_headers = dict(headers or {})
            history_urls = []
            chain_is_sensitive = _has_sensitive_query(current_url)

            for _ in range(MAX_REDIRECTS + 1):
                if chain_is_sensitive:
                    session = self._uncached_session
                else:
                    session = self._session_for_url(current_url)

                history_urls.append((session, current_url))

                response = session.get(
                    current_url,
                    headers=request_headers,
                    timeout=timeout,
                    allow_redirects=False,
                    stream=stream,
                )
                status_code = getattr(response, "status_code", None)
                if status_code not in REDIRECT_STATUSES:
                    return response
                location = (getattr(response, "headers", {}) or {}).get("location")

                # Remove from cache if the redirect target contains any sensitive queries
                if status_code in REDIRECT_STATUSES and location:
                    redirect_target = urljoin(current_url, location)
                    if _has_sensitive_query(redirect_target):
                        chain_is_sensitive = True

                    if chain_is_sensitive:
                        for hist_session, hist_url in history_urls:
                            delete_fn = getattr(hist_session, "delete", None)
                            if callable(delete_fn):
                                try:
                                    delete_fn(hist_url)
                                except Exception:
                                    pass

                close = getattr(response, "close", None)
                if callable(close):
                    close()
                if not location:
                    return response
                current_url = validate_outbound_url(urljoin(current_url, location))
            raise UnsafeUrlError(f"Too many redirects while fetching {redact_url(url)}")
        except Exception as exc:
            raise sanitize_exception(exc) from None

    def _read_bounded_response(self, response: object, url: str, max_bytes: int) -> bytes:
        response_headers = getattr(response, "headers", {}) or {}
        content_length = (
            response_headers.get("content-length") if hasattr(response_headers, "get") else None
        )
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    raise ResponseTooLargeError(
                        f"Response from {redact_url(url)} exceeded {max_bytes} bytes"
                    )
            except ValueError:
                pass

        chunks: list[bytes] = []
        total = 0
        try:
            iter_content = getattr(response, "iter_content", None)
            if callable(iter_content):
                for chunk in iter_content(chunk_size=STREAM_CHUNK_SIZE):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise ResponseTooLargeError(
                            f"Response from {redact_url(url)} exceeded {max_bytes} bytes"
                        )
                    chunks.append(chunk)
                return b"".join(chunks)

            content = getattr(response, "content", b"") or b""
            if len(content) > max_bytes:
                raise ResponseTooLargeError(
                    f"Response from {redact_url(url)} exceeded {max_bytes} bytes"
                )
            return content
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def get_json(
        self,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        timeout: int = 30,
        max_bytes: int = DEFAULT_API_MAX_BYTES,
    ) -> Any:
        response = self.get(url, headers=headers, timeout=timeout, stream=True)
        try:
            response.raise_for_status()
            response_headers = getattr(response, "headers", {}) or {}
            content_type = (
                response_headers.get("content-type", "") if hasattr(response_headers, "get") else ""
            )
            normalized_content_type = content_type.lower().split(";", 1)[0].strip()
            if normalized_content_type and "json" not in normalized_content_type:
                raise InvalidContentTypeError(
                    f"Response from {redact_url(url)} was not JSON ({content_type})"
                )
            content = self._read_bounded_response(response, url, max_bytes)
            encoding = getattr(response, "encoding", None)
            try:
                return json.loads(content.decode(encoding or "utf-8"))
            except Exception as exc:
                raise BooruResponseError(sanitize_exception_text(str(exc))) from exc
        except Exception:
            close = getattr(response, "close", None)
            if callable(close):
                close()
            raise

    def get_text(
        self,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        timeout: int = 30,
        max_bytes: int = DEFAULT_API_MAX_BYTES,
    ) -> BoundedResponse:
        response = self.get(url, headers=headers, timeout=timeout, stream=True)
        try:
            response.raise_for_status()
            content = self._read_bounded_response(response, url, max_bytes)
            return BoundedResponse(
                url=str(getattr(response, "url", url) or url),
                status_code=int(getattr(response, "status_code", 200) or 200),
                headers=getattr(response, "headers", {}) or {},
                content=content,
                encoding=getattr(response, "encoding", None),
            )
        except Exception:
            close = getattr(response, "close", None)
            if callable(close):
                close()
            raise

    def get_bytes(
        self,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        timeout: int = 30,
        max_bytes: int = 25 * 1024 * 1024,
    ) -> bytes:
        response = self.get(url, headers=headers, timeout=timeout, stream=True)
        try:
            response.raise_for_status()
            response_headers = getattr(response, "headers", {}) or {}
            content_type = (
                response_headers.get("content-type", "") if hasattr(response_headers, "get") else ""
            )
            if content_type and not content_type.lower().split(";", 1)[0].startswith("image/"):
                raise InvalidContentTypeError(
                    f"Response from {redact_url(url)} was not an image ({content_type})"
                )
            return self._read_bounded_response(response, url, max_bytes)
        except Exception:
            close = getattr(response, "close", None)
            if callable(close):
                close()
            raise

    def close(self) -> None:
        for session in (self._session, self._uncached_session):
            close = getattr(session, "close", None)
            if callable(close):
                close()
