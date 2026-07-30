"""Booru base class and factory function."""

import random
from typing import Dict, List, Optional

from ranboorux import http_client as rb_http_client


class Booru:
    def __init__(self, booru_name, base_api_url, http_client=None):
        from scripts.ranbooru import Script

        self.booru_name = booru_name
        self.base_api_url = base_api_url
        self.http = http_client or rb_http_client.BooruSession()
        self.headers = {"user-agent": f"Ranbooru Extension/{Script.version} for Forge"}

    def _fetch_data(self, query_url):
        from scripts.ranbooru import BooruError, _log

        _log(f"Querying {self.booru_name}: {rb_http_client.redact_url(query_url)}")
        try:
            return self.http.get_json(query_url, headers=self.headers, timeout=30)
        except Exception as e:
            message = rb_http_client.safe_exception_message(
                f"fetching data from {self.booru_name}", query_url, e
            )
            _log(f"Error {message}")
            raise BooruError(f"HTTP Error {message}") from e

    def _is_direct_image_url(self, url):
        """Check if URL is a direct image URL (not from external sites like Pixiv/Twitter)"""
        if not url or not isinstance(url, str):
            return False

        # Skip external sites that don't provide direct image access
        external_sites = [
            "pixiv.net",
            "pximg.net",
            "twitter.com",
            "x.com",
            "t.co",
            "deviantart.com",
            "artstation.com",
            "instagram.com",
            "facebook.com",
            "patreon.com",
            "fanbox.cc",
        ]

        url_lower = url.lower()
        for site in external_sites:
            if site in url_lower:
                return False

        # Check if URL ends with common image extensions
        image_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"]
        if any(url_lower.endswith(ext) for ext in image_extensions):
            return True

        # Check if URL contains image-serving patterns
        if any(pattern in url_lower for pattern in ["/images/", "/img/", "/media/", "/files/"]):
            return True

        return False

    def _standardize_post(self, post_data):
        from scripts.ranbooru import _split_tag_string, _split_tag_string_override

        post = {}
        # extract tags in a robust way; some APIs return categorized tags as dicts
        raw_tags = post_data.get("tags", post_data.get("tag_string", ""))
        # store categorized lists when possible
        artist_tags = []
        character_tags = []
        copyright_tags = []
        if isinstance(post_data.get("tags"), dict):
            tags_dict = post_data.get("tags")
            # e621 style: tags dict with sublevels
            if isinstance(tags_dict.get("artist"), list):
                artist_tags = tags_dict.get("artist", [])
            if isinstance(tags_dict.get("character"), list):
                character_tags = tags_dict.get("character", [])
            if isinstance(tags_dict.get("copyright"), list):
                copyright_tags = tags_dict.get("copyright", [])
        if "tag_string_artist" in post_data:
            parsed = _split_tag_string_override(post_data.get("tag_string_artist"))
            if parsed is not None:
                artist_tags = parsed
        if "tag_string_character" in post_data:
            parsed = _split_tag_string_override(post_data.get("tag_string_character"))
            if parsed is not None:
                character_tags = parsed
        if "tag_string_copyright" in post_data:
            parsed = _split_tag_string_override(post_data.get("tag_string_copyright"))
            if parsed is not None:
                copyright_tags = parsed

        # For boorus that don't provide categorized tags, try to extract character tags from the main tag string
        # This handles cases like Gelbooru/Danbooru where character tags are mixed with other tags
        if not character_tags and isinstance(raw_tags, str):
            all_tags = _split_tag_string(raw_tags)
            for tag in all_tags:
                # Common patterns for character tags: contains parentheses (series name) or ends with specific patterns
                if (
                    ("(" in tag and ")" in tag)
                    or tag.endswith(r"_\(series\)")
                    or tag.endswith(r"_\(character\)")
                ):
                    character_tags.append(tag)
                # Also catch some common character name patterns (this is heuristic but should catch most)
                elif any(
                    series in tag.lower()
                    for series in [
                        "genshin_impact",
                        "touhou",
                        "fate_",
                        "azur_lane",
                        "kantai_collection",
                        "pokemon",
                    ]
                ):
                    character_tags.append(tag)

        post["tags"] = raw_tags
        post["artist_tags"] = artist_tags
        post["character_tags"] = character_tags
        post["copyright_tags"] = copyright_tags
        post["score"] = post_data.get("score", 0)
        post["file_url"] = post_data.get("file_url")
        if post["file_url"] is None:
            post["file_url"] = post_data.get("large_file_url")
        if post["file_url"] is None:
            # Check if source is a direct image URL before using it
            source_url = post_data.get("source")
            if source_url and self._is_direct_image_url(source_url):
                post["file_url"] = source_url
            else:
                post["file_url"] = None
        post["id"] = post_data.get("id")
        post["rating"] = post_data.get("rating")
        post["booru_name"] = self.booru_name
        return post

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        raise NotImplementedError