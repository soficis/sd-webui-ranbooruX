"""Gelbooru and GelbooruCompatible booru classes."""

import random
import time
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus

from ranboorux import http_client as rb_http_client
from ranboorux.boorus import Booru


class Gelbooru(Booru):
    def __init__(self, fringe_benefits, credentials: Optional[Dict[str, str]] = None):
        from scripts.ranbooru import POST_AMOUNT, _sanitize_gelbooru_credential

        super().__init__(
            "Gelbooru",
            f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&limit={POST_AMOUNT}",
        )
        self.fringeBenefits = fringe_benefits
        credentials = credentials or {}
        self.api_key = (
            _sanitize_gelbooru_credential(credentials.get("api_key"))
            if isinstance(credentials, dict)
            else ""
        )
        self.user_id = (
            _sanitize_gelbooru_credential(credentials.get("user_id"))
            if isinstance(credentials, dict)
            else ""
        )

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        import scripts.ranbooru as _r
        from scripts.ranbooru import BooruError

        _r.COUNT = 0
        all_fetched_posts = []
        if not self.api_key or not self.user_id:
            raise BooruError(
                "Gelbooru requires an API key and user ID. Set them under RanbooruX \u00bb Gelbooru settings."
            )
        credentials_query = (
            f"&api_key={quote_plus(self.api_key)}&user_id={quote_plus(self.user_id)}"
        )
        if post_id:
            query_url = f"{self.base_api_url}{credentials_query}&id={post_id}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if fetched_data and "post" in fetched_data and isinstance(fetched_data["post"], list):
                all_fetched_posts = fetched_data["post"]
            _r.COUNT = len(all_fetched_posts)
            print(f"[R] Found {_r.COUNT} post(s) for ID: {post_id}")
        else:
            page = random.randint(0, max_pages - 1)
            query_url = f"{self.base_api_url}{credentials_query}&pid={page}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if fetched_data and "post" in fetched_data and isinstance(fetched_data["post"], list):
                all_fetched_posts = fetched_data["post"]
            if (
                fetched_data
                and "@attributes" in fetched_data
                and "count" in fetched_data["@attributes"]
            ):
                try:
                    _r.COUNT = int(fetched_data["@attributes"]["count"])
                except Exception:
                    _r.COUNT = len(all_fetched_posts)
            else:
                _r.COUNT = len(all_fetched_posts)
            print(
                f"[R] Fetched {len(all_fetched_posts)} posts from page {page}. Reported total (approx): {_r.COUNT}"
            )
        return [self._standardize_post(post) for post in all_fetched_posts]


class GelbooruCompatible(Booru):
    RETRIABLE_STATUS = {429, 500, 502, 503, 504}

    def __init__(
        self, base_url: str, retries: int = 3, backoff: float = 1.5, log_diagnostics: bool = True
    ):
        from scripts.ranbooru import _sanitize_gelbooru_compat_base_url

        sanitized = _sanitize_gelbooru_compat_base_url(base_url)
        if not sanitized:
            raise ValueError("Invalid Gelbooru-compatible base URL.")
        self.base_url = sanitized
        self.retries = max(1, retries)
        self.backoff = max(0.5, backoff)
        self.log_diagnostics = log_diagnostics
        self._post_endpoint = f"{self.base_url}/index.php?page=dapi&s=post&q=index"
        self._tag_endpoint = f"{self.base_url}/index.php?page=dapi&s=tag&q=index"
        self._alias_endpoint = f"{self.base_url}/index.php?page=dapi&s=tag_alias&q=index"
        super().__init__("Gelbooru-Compatible", self._post_endpoint)

    def _perform_request(self, url: str):
        from scripts.ranbooru import BooruError

        last_error: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                response = self.http.get(url, headers=self.headers, timeout=30, stream=True)
            except Exception as exc:
                last_error = exc
                self._log_retry(url, attempt, f"Request error: {exc.__class__.__name__}")
            else:
                if response.status_code in self.RETRIABLE_STATUS:
                    last_error = BooruError(f"Status {response.status_code}")
                    self._log_retry(url, attempt, f"Status {response.status_code}")
                    close = getattr(response, "close", None)
                    if callable(close):
                        close()
                else:
                    content = self.http._read_bounded_response(
                        response,
                        url,
                        rb_http_client.DEFAULT_API_MAX_BYTES,
                    )
                    return rb_http_client.BoundedResponse(
                        url=str(getattr(response, "url", url) or url),
                        status_code=int(getattr(response, "status_code", 200) or 200),
                        headers=getattr(response, "headers", {}) or {},
                        content=content,
                        encoding=getattr(response, "encoding", None),
                    )
            time.sleep(min(self.backoff * attempt, 5.0))
        if last_error is None:
            error_summary = "unknown error"
        elif isinstance(last_error, BooruError):
            error_summary = str(last_error)
        else:
            error_summary = last_error.__class__.__name__
        raise BooruError(
            f"HTTP Error fetching from {self.booru_name}: {error_summary} for {rb_http_client.redact_url(url)}"
        )

    def _log_retry(self, url: str, attempt: int, message: str) -> None:
        from scripts.ranbooru import _log

        _log(f"{self.booru_name}: retry {attempt} for {rb_http_client.redact_url(url)} - {message}")

    def _log_snippet(self, response) -> None:
        from scripts.ranbooru import _log

        if not self.log_diagnostics:
            return
        snippet = response.text.strip().replace("\n", " ")[:200]
        _log(
            f"{self.booru_name}: {rb_http_client.redact_url(getattr(response, 'url', ''))} -> {snippet}"
        )

    def _parse_json_entities(self, payload, entity_key: str) -> Tuple[List[dict], Optional[int]]:
        entries: List[dict] = []
        approx = None
        if isinstance(payload, dict):
            possible = payload.get(entity_key)
            if isinstance(possible, list):
                entries = possible
            elif isinstance(possible, dict):
                entries = [possible]
            attrs = payload.get("@attributes")
            if isinstance(attrs, dict) and "count" in attrs:
                try:
                    approx = int(attrs["count"])
                except (TypeError, ValueError):
                    approx = None
        elif isinstance(payload, list):
            entries = payload
        return entries, approx

    def _parse_xml_entities(
        self, text_payload: str, entity_key: str
    ) -> Tuple[List[dict], Optional[int]]:
        from scripts.ranbooru import BooruError

        probe = (text_payload or "").lower()
        if ("<posts" not in probe) and ("<post " not in probe):
            raise BooruError(f"{self.booru_name} response does not look like DAPI XML.")
        try:
            root = ET.fromstring(text_payload)
        except ET.ParseError as exc:
            raise BooruError(f"Failed to parse XML from {self.booru_name}: {exc}") from exc
        entries = [element.attrib for element in root.findall(entity_key)]
        if not entries and root.tag == entity_key:
            entries = [root.attrib]
        approx = None
        count_attr = root.attrib.get("count") if hasattr(root, "attrib") else None
        if count_attr is not None:
            try:
                approx = int(count_attr)
            except (TypeError, ValueError):
                approx = None
        if approx is None:
            approx = len(entries)
        return entries, approx

    def _request_dapi(self, url_base: str, entity_key: str) -> Tuple[List[dict], int]:
        from scripts.ranbooru import BooruError

        json_url = f"{url_base}&json=1"
        try:
            response = self._perform_request(json_url)
            self._log_snippet(response)
            ct = (response.headers.get("content-type") or "").lower()
            text_head = (response.text or "").lstrip()[:64].lower()
            if (
                "html" in ct
                or text_head.startswith("<!doctype html")
                or text_head.startswith("<html")
            ):
                raise BooruError(
                    f"{self.booru_name} returned HTML for JSON request. The site may be blocking API access or the base URL is not DAPI-compatible."
                )
            payload = response.json()
            entries, approx = self._parse_json_entities(payload, entity_key)
            if entries:
                return entries, approx or len(entries)
        except (ValueError, BooruError):
            pass

        response = self._perform_request(url_base)
        self._log_snippet(response)
        ct2 = (response.headers.get("content-type") or "").lower()
        text2 = response.text or ""
        text2_head = text2.lstrip()[:64].lower()
        if (
            "html" in ct2
            or text2_head.startswith("<!doctype html")
            or text2_head.startswith("<html")
        ):
            raise BooruError(
                f"{self.booru_name} returned HTML. Expected DAPI XML/JSON. Verify the base URL (e.g., https://realbooru.com) or that the site allows API access."
            )
        entries, approx = self._parse_xml_entities(text2, entity_key)
        return entries, approx or 0

    def get_posts(self, tags_query: str = "", max_pages: int = 10, post_id: Optional[int] = None):
        import scripts.ranbooru as _r
        from scripts.ranbooru import POST_AMOUNT

        _r.COUNT = 0
        posts: List[dict] = []
        if post_id:
            query_base = f"{self._post_endpoint}&limit={POST_AMOUNT}&id={post_id}{tags_query}"
            posts, approx = self._request_dapi(query_base, "post")
            _r.COUNT = approx
            print(f"[R] Gelbooru-compatible: found {len(posts)} post(s) for ID: {post_id}")
        else:
            page = random.randint(0, max_pages - 1) if max_pages > 0 else 0
            query_base = f"{self._post_endpoint}&limit={POST_AMOUNT}&pid={page}{tags_query}"
            posts, approx = self._request_dapi(query_base, "post")
            _r.COUNT = approx
            print(
                f"[R] Gelbooru-compatible: fetched {len(posts)} posts from page {page}. Reported count={approx}"
            )
        standardized = []
        for post in posts:
            normalized = self._standardize_post(post)
            normalized["source_base_url"] = self.base_url
            standardized.append(normalized)
        return standardized

    def get_tags(self, name_pattern: Optional[str] = None, limit: int = 100) -> List[dict]:
        query = f"{self._tag_endpoint}&limit={limit}"
        if name_pattern:
            query += f"&name_pattern={quote_plus(name_pattern)}"
        tags, _ = self._request_dapi(query, "tag")
        return tags

    def get_tag_aliases(self, name_pattern: Optional[str] = None, limit: int = 100) -> List[dict]:
        query = f"{self._alias_endpoint}&limit={limit}"
        if name_pattern:
            query += f"&name_pattern={quote_plus(name_pattern)}"
        aliases, _ = self._request_dapi(query, "tag_alias")
        return aliases
