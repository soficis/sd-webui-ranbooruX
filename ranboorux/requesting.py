from __future__ import annotations

"""
Backward-compatibility shim — canonical SSRF-hardened HTTP implementation lives
in :mod:`ranboorux.http_client`.

``requesting.py`` is retained only so existing imports
(``from ranboorux.requesting import BooruSession``) keep working. Do NOT add
logic here; patch ``http_client.py`` instead.
"""

from ranboorux.http_client import (  # noqa: F401,F403
    DEFAULT_API_MAX_BYTES,
    MAX_REDIRECTS,
    REDIRECT_STATUSES,
    STREAM_CHUNK_SIZE,
    SENSITIVE_QUERY_PARAMS,
    BooruResponseError,
    BooruSession,
    BoundedResponse,
    InvalidContentTypeError,
    ResponseTooLargeError,
    UnsafeUrlError,
    _SafeHTTPAdapter,
    _SafeHTTPConnection,
    _SafeHTTPConnectionPool,
    _SafeHTTPSConnection,
    _SafeHTTPSConnectionPool,
    _close_socket,
    _has_sensitive_query,
    _is_public_ip,
    _resolve_host,
    _validate_connected_socket,
    redact_paths,
    redact_url,
    redact_urls_in_text,
    safe_exception_message,
    sanitize_exception,
    sanitize_exception_text,
    validate_outbound_url,
)

# Re-export everything from http_client for ``from ranboorux.requesting import *`` callers.
try:
    from ranboorux.http_client import __all__  # type: ignore[attr-defined]
except ImportError:
    pass
