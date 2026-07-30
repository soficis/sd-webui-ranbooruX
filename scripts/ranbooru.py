import csv
import difflib
import json
import logging
import os
import random
import re
import shutil
import sys
import traceback
import unicodedata
from contextlib import ExitStack, contextmanager
from datetime import datetime
from io import BytesIO
from typing import Dict, Iterable, List, Optional, Set, Tuple

import gradio as gr
import modules.scripts as scripts
import numpy as np
from modules import shared
from modules.processing import (
    StableDiffusionProcessing,
    StableDiffusionProcessingImg2Img,
    process_images,
)
from PIL import Image

try:
    from modules.ui_components import InputAccordion
except ImportError:
    InputAccordion = gr.Accordion
from modules.scripts import basedir

from ranboorux import catalog as rb_catalog
from ranboorux import http_client as rb_http_client
from ranboorux import image_ops as rb_image_ops
from ranboorux import loranado as rb_loranado
from ranboorux import mutation_scope as rb_mutation_scope
from ranboorux import run_options as rb_run_options
from ranboorux import tag_pipeline as rb_tag_pipeline
from ranboorux import user_store as rb_user_store
from ranboorux.anima_detect import get_anima_model_info
from ranboorux.boorus import Booru
from ranboorux.integrations import adetailer as rb_adetailer_integration
from ranboorux.integrations import adetailer_orchestration as rb_adetailer_orch
from ranboorux.integrations import adetailer_runtime as rb_adetailer_runtime
from ranboorux.integrations import controlnet as rb_controlnet_integration
from ranboorux.integrations import img2img_lifecycle as rb_img2img_lifecycle

# --- Constants and Paths ---
EXTENSION_ROOT = basedir()
# Ensure extension root is on sys.path for local package imports (e.g., sd_forge_controlnet)
if EXTENSION_ROOT not in sys.path:
    sys.path.append(EXTENSION_ROOT)
USER_DATA_DIR = os.path.join(EXTENSION_ROOT, "user")
USER_SEARCH_DIR = os.path.join(USER_DATA_DIR, "search")
USER_REMOVE_DIR = os.path.join(USER_DATA_DIR, "remove")
LOG_DIR = os.path.join(USER_DATA_DIR, "logs")
os.makedirs(USER_SEARCH_DIR, exist_ok=True)
os.makedirs(USER_REMOVE_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

GELBOORU_CREDENTIALS_DIR = os.path.join(USER_DATA_DIR, "gelbooru")
GELBOORU_CREDENTIALS_FILE = os.path.join(GELBOORU_CREDENTIALS_DIR, "credentials.json")

PERSONAL_REMOVE_FILE = os.path.join(USER_REMOVE_DIR, "personal_remove.txt")
FAVORITES_FILE = os.path.join(USER_SEARCH_DIR, "favorites.txt")
PROMPT_LOG_JSONL = os.path.join(LOG_DIR, "prompt_sources.jsonl")
TAG_CATALOG_CONFIG_FILE = os.path.join(USER_DATA_DIR, "tag_catalog.json")
BUNDLED_CATALOG_DIR = os.path.join(EXTENSION_ROOT, "data", "catalogs")
BUNDLED_CATALOG_PATH = os.path.join(BUNDLED_CATALOG_DIR, "danbooru_tags.csv")
USER_CATALOGS_DIR = os.path.join(USER_DATA_DIR, "catalogs")
os.makedirs(USER_CATALOGS_DIR, exist_ok=True)

REMOVAL_SYNONYM_GROUPS_RAW: Tuple[Set[str], ...] = (
    {"grayscale", "greyscale", "monochrome"},
    {"1girl", "1female", "1woman"},
)

# Ensure default files exist
for filename in ["tags_search.txt", "tags_remove.txt"]:
    dir_path = USER_SEARCH_DIR if "search" in filename else USER_REMOVE_DIR
    filepath = os.path.join(dir_path, filename)
    if not os.path.isfile(filepath):
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                pass
        except Exception as e:
            print(f"[Ranbooru] Error creating file {filepath}: {e}")

for ensured_path in (PERSONAL_REMOVE_FILE, FAVORITES_FILE, PROMPT_LOG_JSONL):
    parent = os.path.dirname(ensured_path)
    try:
        os.makedirs(parent, exist_ok=True)
        if not os.path.isfile(ensured_path):
            mode = "w"
            with open(ensured_path, mode, encoding="utf-8") as f:
                if ensured_path == PROMPT_LOG_JSONL:
                    pass
    except Exception as exc:
        print(f"[Ranbooru] Error ensuring file {ensured_path}: {exc}")

COLORED_BG = [
    "black_background",
    "aqua_background",
    "white_background",
    "colored_background",
    "gray_background",
    "blue_background",
    "green_background",
    "red_background",
    "brown_background",
    "purple_background",
    "yellow_background",
    "orange_background",
    "pink_background",
    "plain",
    "transparent_background",
    "simple_background",
    "two-tone_background",
    "grey_background",
]
ADD_BG = ["outdoors", "indoors"]
BW_BG = ["monochrome", "greyscale", "grayscale"]
POST_AMOUNT = 100
COUNT = 100
DEBUG = False
MAX_SOURCE_IMAGE_BYTES = 25 * 1024 * 1024
MAX_SOURCE_IMAGE_PIXELS = 50_000_000
MAX_SOURCE_IMAGE_FRAMES = 1

_ranbooru_logger = logging.getLogger("ranboorux")

RATING_TYPES = {
    "none": {"All": "All"},
    "full": {"All": "All", "Safe": "safe", "Questionable": "questionable", "Explicit": "explicit"},
    "single": {"All": "All", "Safe": "g", "Sensitive": "s", "Questionable": "q", "Explicit": "e"},
}

RATINGS = {
    "e621": RATING_TYPES["full"],
    "danbooru": RATING_TYPES["single"],
    "aibooru": RATING_TYPES["full"],
    "yande.re": RATING_TYPES["full"],
    "konachan": RATING_TYPES["full"],
    "safebooru": RATING_TYPES["none"],
    "rule34": RATING_TYPES["full"],
    "xbooru": RATING_TYPES["full"],
    "gelbooru": RATING_TYPES["single"],
    "gelbooru-compatible": RATING_TYPES["single"],
}

STRICT_IMG2IMG_EXTRA_ROUNDS = 2
STRICT_IMG2IMG_LOG_SAMPLE = 5
_TAG_SPLIT_RE = re.compile(r"[,\s]+")
_LORANADO_PONY_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(r"(?<![a-z0-9])pony(?![a-z0-9])"),
    re.compile(r"(?<![a-z0-9])pony[ _-]*xl(?![a-z0-9])"),
    re.compile(r"(?<![a-z0-9])pony[ _-]*diffusion(?:[ _-]*xl)?(?![a-z0-9])"),
    re.compile(r"(?<![a-z0-9])ponydiffusion(?:xl)?(?![a-z0-9])"),
    re.compile(r"(?<![a-z0-9])pdxl(?![a-z0-9])"),
    re.compile(r"(?<![a-z0-9])xlp(?![a-z0-9])"),
)
_LORANADO_PONY_METADATA_KEY_HINTS: Tuple[str, ...] = (
    "base_model",
    "base model",
    "sd_model",
    "modelspec.architecture",
    "modelspec.title",
    "modelspec.description",
    "architecture",
    "model_version",
)


def _log(message: object) -> None:
    if isinstance(message, str) and not message.startswith("[R]"):
        message = f"[R] {message}"
    print(message)


def _gr_component_update(component_or_class, **kwargs):
    """Gradio 3/4 compatibility helper for component updates."""
    update_method = getattr(component_or_class, "update", None)
    if callable(update_method):
        return update_method(**kwargs)
    return component_or_class(**kwargs)


def _gr_update(**kwargs):
    """Compatibility wrapper for gr.update() and fallback dict semantics."""
    update_fn = getattr(gr, "update", None)
    if callable(update_fn):
        return update_fn(**kwargs)
    return kwargs


def get_available_ratings(booru):
    choices = list(RATINGS.get(booru, RATING_TYPES["none"]).keys())
    return _gr_component_update(gr.Radio, choices=choices, value="All", visible=True)


def show_fringe_benefits(booru):
    return _gr_component_update(gr.Checkbox, visible=(booru == "gelbooru"), value=True)


def _sanitize_gelbooru_credential(value: Optional[str]) -> str:
    return rb_user_store.sanitize_credential(value)


def _sanitize_gelbooru_compat_base_url(value: Optional[str]) -> str:
    if not isinstance(value, str):
        return ""
    sanitized = value.strip()
    if not sanitized:
        return ""
    if not re.match(r"^https?://", sanitized, re.IGNORECASE):
        sanitized = f"https://{sanitized}"
    return sanitized.rstrip("/")


def _load_gelbooru_credentials_from_disk() -> Optional[Dict[str, str]]:
    try:
        return rb_user_store.load_gelbooru_credentials(GELBOORU_CREDENTIALS_FILE)
    except Exception as exc:
        _log(f"Warn: Failed to read Gelbooru credentials: {exc}")
    return None


def _save_gelbooru_credentials_to_disk(api_key: str, user_id: str) -> bool:
    try:
        rb_user_store.save_gelbooru_credentials(GELBOORU_CREDENTIALS_FILE, api_key, user_id)
        return True
    except Exception as exc:
        _log(f"Error: Unable to save Gelbooru credentials: {exc}")
        return False


def _clear_gelbooru_credentials_from_disk() -> bool:
    try:
        rb_user_store.clear_gelbooru_credentials(GELBOORU_CREDENTIALS_FILE)
        return True
    except Exception as exc:
        _log(f"Warn: Failed to clear Gelbooru credentials: {exc}")
        return False


POST_ID_UNSUPPORTED_ERRORS = {
    "konachan": "Konachan does not support post IDs",
    "yande.re": "Yande.re does not support post IDs",
    "e621": "e621 does not support post IDs",
}


def check_booru_exceptions(booru, post_id, tags):
    if post_id and booru in POST_ID_UNSUPPORTED_ERRORS:
        raise ValueError(POST_ID_UNSUPPORTED_ERRORS[booru])
    if booru == "danbooru" and tags and len([t for t in tags.split(",") if t.strip()]) > 1:
        raise ValueError("Danbooru API only supports one tag.")


def _split_tag_string(value: Optional[str]) -> List[str]:
    if not isinstance(value, str):
        return []
    return [tag for tag in _TAG_SPLIT_RE.split(value.strip()) if tag]


def _coerce_multiselect_values(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, (list, tuple, set)):
        values: List[str] = []
        for item in value:
            if item is None:
                continue
            cleaned = str(item).strip()
            if cleaned:
                values.append(cleaned)
        return values
    cleaned = str(value).strip()
    return [cleaned] if cleaned else []


def _split_tag_string_override(value: object) -> Optional[List[str]]:
    if value is None or not isinstance(value, str):
        return None
    return _split_tag_string(value)


POST_URL_TEMPLATES = {
    "danbooru": "https://danbooru.donmai.us/posts/{pid}",
    "gelbooru": "https://gelbooru.com/index.php?page=post&s=view&id={pid}",
    "safebooru": "https://safebooru.org/index.php?page=post&s=view&id={pid}",
    "rule34": "https://rule34.xxx/index.php?page=post&s=view&id={pid}",
    "xbooru": "https://xbooru.com/index.php?page=post&s=view&id={pid}",
    "konachan": "https://konachan.com/post/show/{pid}",
    "yandere": "https://yande.re/post/show/{pid}",
    "aibooru": "https://aibooru.online/posts/{pid}",
    "e621": "https://e621.net/posts/{pid}",
}


def get_original_post_url(post):
    try:
        booru = (post.get("booru_name") or "").lower()
        pid = post.get("id")
        if not pid:
            return None
        if booru == "gelbooru-compatible":
            base = (post.get("source_base_url") or "").strip()
            if base:
                return f"{base.rstrip('/')}/index.php?page=post&s=view&id={pid}"
            return None
        template = POST_URL_TEMPLATES.get(booru)
        if template:
            return template.format(pid=pid)
        return None
    except Exception:
        return None


def generate_chaos(pos_tags, neg_tags, chaos_amount):
    pos_tag_list = rb_tag_pipeline.split_prompt_tags(pos_tags)
    neg_tag_list = rb_tag_pipeline.split_prompt_tags(neg_tags)
    chaos_list = list(set(pos_tag_list + neg_tag_list))
    if not chaos_list:
        return pos_tags, neg_tags
    random.shuffle(chaos_list)
    len_list = round(len(chaos_list) * chaos_amount)
    neg_add = chaos_list[:len_list]
    pos_add = chaos_list[len_list:]
    final_pos = list(set(pos_tag_list) - set(neg_add)) + pos_add
    final_neg = list(set(neg_tag_list) - set(pos_add)) + neg_add
    return ",".join(rb_tag_pipeline.dedupe_keep_order(final_pos)), ",".join(
        rb_tag_pipeline.dedupe_keep_order(final_neg)
    )


class BooruError(Exception):
    pass


class TagCatalogProvider:
    """Interface for optional tag catalog backends."""

    def enabled(self) -> bool:
        return False

    def resolve_alias(self, tag: str) -> str:
        return tag if isinstance(tag, str) else ""

    def category(self, tag: str) -> Optional[int]:
        return None

    def is_textual(self, tag: str) -> bool:
        return False

    def is_hair(self, tag: str) -> bool:
        return False

    def is_eye(self, tag: str) -> bool:
        return False

    def canonical(self, tag: str) -> str:
        return self.resolve_alias(tag)

    def has(self, tag: str) -> bool:
        return False

    def suggestions(self, tag: str, limit: int = 3) -> List[str]:
        return []


class NoopCatalog(TagCatalogProvider):
    pass


class CsvCatalog(TagCatalogProvider):
    _TEXTUAL_SEED: Set[str] = {
        "text",
        "english_text",
        "japanese_text",
        "chinese_text",
        "korean_text",
        "translated",
        "translation",
        "commentary",
        "artist_commentary",
        "author_commentary",
        "publisher_commentary",
        "speech_bubble",
        "speech_bubbles",
        "dialogue",
        "dialog",
        "subtitle",
        "subtitles",
        "caption",
        "captions",
        "watermark",
        "logo",
        "signature",
        "url",
        "filename",
        "thought_bubble",
        "thought_balloon",
        "notice",
    }
    _TEXTUAL_KEYWORDS: Tuple[str, ...] = (
        "text",
        "commentary",
        "speech_bubble",
        "thought_bubble",
        "watermark",
        "logo",
        "subtitle",
        "caption",
        "dialog",
        "dialogue",
        "filename",
        "url",
        "signature",
        "credit",
    )
    _TEXTUAL_PREFIXES: Tuple[str, ...] = (
        "translated_",
        "translation_",
        "english_",
        "japanese_",
        "korean_",
        "chinese_",
    )
    _TEXTUAL_SUFFIXES: Tuple[str, ...] = (
        "_text",
        "_commentary",
        "_logo",
        "_watermark",
        "_subtitle",
        "_caption",
        "_speech",
        "_bubble",
    )
    _HAIR_SUFFIXES: Tuple[str, ...] = ("_hair",)
    _EYE_SUFFIXES: Tuple[str, ...] = ("_eyes", "_eye")

    def __init__(self, path: str):
        self._path = path
        self._mtime = 0.0
        self._aliases: Dict[str, str] = {}
        self._cats: Dict[str, int] = {}
        self._counts: Dict[str, int] = {}
        self._textual: Set[str] = set()
        self._hair: Set[str] = set()
        self._eyes: Set[str] = set()
        self._all_tags: Set[str] = set()
        self._load()

    @staticmethod
    def _normalize_name(value: str) -> str:
        if not isinstance(value, str):
            return ""
        cleaned = unicodedata.normalize("NFKC", value).strip().lower()
        if not cleaned:
            return ""
        cleaned = cleaned.replace("-", "_").replace(" ", "_")
        cleaned = re.sub(r"_+", "_", cleaned)
        return cleaned

    def _looks_textual(self, tag: str) -> bool:
        if not tag:
            return False
        if tag in self._TEXTUAL_SEED:
            return True
        if any(keyword in tag for keyword in self._TEXTUAL_KEYWORDS):
            return True
        if any(tag.startswith(prefix) for prefix in self._TEXTUAL_PREFIXES):
            return True
        if any(tag.endswith(suffix) for suffix in self._TEXTUAL_SUFFIXES):
            return True
        return False

    def _process_row(self, row: List[str], columns: Optional[Dict[str, int]] = None) -> None:
        def _safe_get(idx: Optional[int]) -> str:
            if idx is None:
                return ""
            if idx < 0 or idx >= len(row):
                return ""
            return row[idx]

        if columns:
            raw_name = _safe_get(columns.get("tag"))
            if not raw_name:
                raw_name = _safe_get(columns.get("name"))
            cat_val = _safe_get(columns.get("category"))
            count_val = _safe_get(columns.get("count"))
            alias_field = _safe_get(columns.get("alias"))
            if not alias_field:
                alias_field = _safe_get(columns.get("aliases"))
        else:
            raw_name = row[0] if len(row) > 0 else ""
            cat_val = row[1] if len(row) > 1 else ""
            count_val = row[2] if len(row) > 2 else ""
            alias_field = row[3] if len(row) > 3 else ""

        name = self._normalize_name(raw_name)
        if not name:
            return
        try:
            category = int(cat_val) if cat_val is not None and str(cat_val).strip() != "" else 0
        except Exception:
            category = 0
        try:
            count = int(count_val) if count_val is not None and str(count_val).strip() != "" else 0
        except Exception:
            count = 0
        self._cats[name] = category
        self._counts[name] = count
        self._all_tags.add(name)
        if category == 0:
            if any(name.endswith(suffix) for suffix in self._HAIR_SUFFIXES):
                self._hair.add(name)
            if any(name.endswith(suffix) for suffix in self._EYE_SUFFIXES):
                self._eyes.add(name)
        if self._looks_textual(name):
            self._textual.add(name)
        if alias_field:
            for alias_candidate in re.split(r"[\s,]+", alias_field):
                alias_name = self._normalize_name(alias_candidate)
                if not alias_name or alias_name == name:
                    continue
                self._aliases[alias_name] = name

    def _load(self) -> None:
        if not os.path.isfile(self._path):
            raise FileNotFoundError(self._path)
        self._mtime = os.path.getmtime(self._path)
        self._aliases.clear()
        self._cats.clear()
        self._counts.clear()
        self._textual = set(self._TEXTUAL_SEED)
        self._hair.clear()
        self._eyes.clear()
        self._all_tags.clear()
        with open(self._path, newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            first_row = next(reader, None)
            if first_row is None:
                raise ValueError("CSV file is empty")
            header_map: Optional[Dict[str, int]] = None
            lowered = [str(cell or "").strip().lower() for cell in first_row]
            if len(lowered) >= 3 and lowered[0] in ("tag", "name") and lowered[1] == "category":
                header_map = {name: idx for idx, name in enumerate(lowered)}
            else:
                self._process_row(first_row, None)
            for row in reader:
                self._process_row(row, header_map)
        # Include alias forms for hair/eye lookup convenience
        for alias, canonical in list(self._aliases.items()):
            if canonical in self._hair:
                self._hair.add(alias)
            if canonical in self._eyes:
                self._eyes.add(alias)

    def maybe_reload(self) -> None:
        try:
            current = os.path.getmtime(self._path)
        except OSError:
            return
        if current != self._mtime:
            self._load()

    def enabled(self) -> bool:
        return True

    def resolve_alias(self, tag: str) -> str:
        normalized = self._normalize_name(tag)
        if not normalized:
            return ""
        return self._aliases.get(normalized, normalized)

    def category(self, tag: str) -> Optional[int]:
        canonical = self.resolve_alias(tag)
        return self._cats.get(canonical)

    def is_textual(self, tag: str) -> bool:
        canonical = self.resolve_alias(tag)
        return canonical in self._textual or self._looks_textual(canonical)

    def is_hair(self, tag: str) -> bool:
        canonical = self.resolve_alias(tag)
        return canonical in self._hair

    def is_eye(self, tag: str) -> bool:
        canonical = self.resolve_alias(tag)
        return canonical in self._eyes

    def canonical(self, tag: str) -> str:
        return self.resolve_alias(tag)

    def has(self, tag: str) -> bool:
        canonical = self.resolve_alias(tag)
        return canonical in self._cats

    def suggestions(self, tag: str, limit: int = 3) -> List[str]:
        if limit <= 0 or not self._all_tags:
            return []
        normalized = self._normalize_name(tag)
        if not normalized:
            return []
        pool = list(self._all_tags)
        matches = difflib.get_close_matches(normalized, pool, n=max(limit * 4, limit), cutoff=0.6)
        if not matches:
            return []
        matches.sort(key=lambda name: (-self._counts.get(name, 0), name))
        return matches[:limit]


class Script(scripts.Script):
    def __init__(self):
        super().__init__()
        self._gelbooru_saved_credentials: Optional[Dict[str, str]] = (
            _load_gelbooru_credentials_from_disk()
        )
        self._gelbooru_compat_base_url: str = ""
        self._gelbooru_effective_credentials: Optional[Dict[str, str]] = None
        self._personal_remove_tags: Set[str] = set()
        self._favorite_tags: Set[str] = set()
        self._is_anima_model: bool = False
        self._removal_context: Dict[str, object] = {}
        self._tag_normal_cache: Dict[str, str] = {}
        self._synonym_groups: Tuple[Set[str], ...] = tuple()
        self._synonym_lookup: Dict[str, Set[str]] = {}
        try:
            norm = self._normalize_tag
            groups: List[Set[str]] = []
            for group in REMOVAL_SYNONYM_GROUPS_RAW:
                normalized_group = {norm(tag) for tag in group if norm(tag)}
                if normalized_group:
                    groups.append(normalized_group)
            self._synonym_groups = tuple(groups)
            lookup: Dict[str, Set[str]] = {}
            for group in self._synonym_groups:
                for entry in group:
                    lookup[entry] = group
            self._synonym_lookup = lookup
        except Exception:
            self._synonym_groups = tuple()
            self._synonym_lookup = {}
        self._adetailer_state = rb_adetailer_runtime.AdetailerRunState()
        self._adetailer_patches = rb_adetailer_runtime.PatchRegistry()
        self._host_scope = rb_mutation_scope.HostMutationScope()
        self._adetailer_orch = rb_adetailer_orch.AdetailerOrchestrator(self)
        self._strict_img2img_fetch: bool = True
        self._strict_img2img_active: bool = False
        self._strict_img2img_relaxed: bool = False
        self._strict_img2img_rejections: List[Dict[str, object]] = []
        self._strict_allowed_subjects: Set[str] = set()
        self._strict_initial_additions: str = ""
        self._use_tag_catalog: bool = True
        self._catalog_source: str = "bundled"
        self._tag_catalog_path: str = ""
        self._custom_catalog_path: str = ""
        self._catalog: TagCatalogProvider = NoopCatalog()
        self._tag_catalog_diag: Dict[str, object] = {}
        self._catalog_status_md = None
        self._tag_diag_md = None
        self._tag_catalog_status_text: str = "Catalog mode: ON - Bundled default"
        self._tag_catalog_linter_limit: int = 3
        self._catalog_subject_anchors = None
        self._loranado_scan_cache: Dict[str, Dict[str, object]] = {}
        self._http_client = rb_http_client.BooruSession(use_cache=False)
        self._load_tag_catalog_preferences()

    sorting_priority = 1  # Highest priority to run before ALL other extensions
    previous_loras = ""
    last_img = []
    real_steps = 0
    version = "1.8-Refactored"
    original_prompt = ""
    run_img2img_pass = False
    img2img_denoising = 0.75
    cache_installed_by_us = False
    _adetailer_support_enabled = False
    _post_adetailer_enabled = False
    _manual_adetailer_prev_enabled = False
    _DASH_UNDERSCORE_RE = re.compile(r"[_\-]+")
    _WHITESPACE_RE = re.compile(r"\s+")
    _LORANADO_MAX_HEADER_BYTES = 4 * 1024 * 1024
    _USER_LIST_PATHS = {
        "personal": PERSONAL_REMOVE_FILE,
        "favorites": FAVORITES_FILE,
    }

    @staticmethod
    def _canonicalize_raw_tag(tag: str) -> str:
        return rb_tag_pipeline.canonicalize_raw_tag(tag)

    @staticmethod
    def _normalize_tag(tag: str) -> str:
        return rb_tag_pipeline.normalize_tag(tag)

    def _ensure_user_file(self, path: str) -> None:
        try:
            rb_user_store.ensure_text_file(path)
        except Exception as exc:
            print(f"[R Files] Failed to ensure file {path}: {exc}")

    def _read_list_file(self, path: str) -> List[str]:
        try:
            return rb_user_store.read_list_file(path, normalize_fn=self._normalize_tag)
        except Exception as exc:
            print(f"[R Files] Failed to read list file {path}: {exc}")
            return []

    def _write_list_file(self, path: str, tags: Iterable[str]) -> None:
        try:
            rb_user_store.write_list_file(path, tags, normalize_fn=self._normalize_tag)
        except Exception as exc:
            print(f"[R Files] Failed to write list file {path}: {exc}")

    def _load_tag_catalog_preferences(self) -> None:
        """Load persisted catalog settings."""
        self._use_tag_catalog = True
        self._catalog_source = "bundled"
        self._custom_catalog_path = ""
        self._tag_catalog_path = ""
        try:
            data = rb_user_store.load_catalog_preferences(TAG_CATALOG_CONFIG_FILE)
            self._use_tag_catalog = bool(data.get("enabled", True))
            source = str(data.get("source", "bundled")).strip().lower()
            self._catalog_source = source if source in ("bundled", "custom") else "bundled"
            custom_path = data.get("custom_path", "")
            self._custom_catalog_path = custom_path.strip() if isinstance(custom_path, str) else ""
            self._tag_catalog_path = self._custom_catalog_path
        except Exception as exc:
            print(f"[Ranbooru] Warn: Failed to load tag catalog preferences: {exc}")
            self._use_tag_catalog = True
            self._catalog_source = "bundled"
            self._custom_catalog_path = ""
            self._tag_catalog_path = ""
        self._tag_catalog_status_text = self._format_catalog_status()

    def _save_tag_catalog_preferences(self) -> None:
        try:
            rb_user_store.save_catalog_preferences(
                TAG_CATALOG_CONFIG_FILE,
                enabled=bool(self._use_tag_catalog),
                source=self._catalog_source,
                custom_path=self._custom_catalog_path,
            )
        except Exception as exc:
            print(f"[Ranbooru] Warn: Failed to save tag catalog preferences: {exc}")

    def _update_catalog_status(self, message: Optional[str] = None) -> None:
        if message:
            self._tag_catalog_status_text = message
        else:
            self._tag_catalog_status_text = self._format_catalog_status()
        try:
            if self._catalog_status_md is not None:
                self._catalog_status_md.update(value=self._tag_catalog_status_text)
        except Exception:
            pass

    def _resolve_catalog_path(self) -> str:
        if self._catalog_source == "bundled":
            bundled_override = (self._tag_catalog_path or "").strip()
            if bundled_override and os.path.isfile(bundled_override):
                return bundled_override
            return BUNDLED_CATALOG_PATH
        if self._catalog_source == "custom":
            return (self._custom_catalog_path or "").strip()
        return ""

    def _set_catalog_source(self, source: str) -> str:
        source_value = (source or "").strip().lower()
        if source_value not in ("bundled", "custom"):
            source_value = "bundled"
        self._catalog_source = source_value
        if source_value == "bundled":
            self._tag_catalog_path = ""
        else:
            self._tag_catalog_path = self._custom_catalog_path
        self._save_tag_catalog_preferences()
        return self._catalog_source

    def _catalog_path_from_upload(self, uploaded: object) -> str:
        if isinstance(uploaded, str):
            return uploaded
        if isinstance(uploaded, dict):
            for key in ("name", "path", "orig_name"):
                value = uploaded.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    def _validate_csv_format(self, path: str) -> Tuple[bool, str]:
        return rb_catalog.validate_catalog_csv(path)

    def _import_custom_catalog(self, uploaded: object, path_hint: str = "") -> Tuple[bool, str]:
        source_path = (path_hint or "").strip() or self._catalog_path_from_upload(uploaded)
        ok, validation_message = self._validate_csv_format(source_path)
        if not ok:
            return False, f"Invalid CSV: {validation_message}"
        try:
            os.makedirs(USER_CATALOGS_DIR, exist_ok=True)
            source_name = os.path.basename(source_path) or "catalog.csv"
            safe_name = re.sub(r"[^\w\-.]", "_", source_name)
            destination = os.path.join(USER_CATALOGS_DIR, safe_name)
            shutil.copy2(source_path, destination)
            self._catalog_source = "custom"
            self._custom_catalog_path = destination
            self._tag_catalog_path = destination
            self._use_tag_catalog = True
            self._save_tag_catalog_preferences()
            loaded, load_message = self._load_tag_catalog()
            if loaded:
                return True, self._format_catalog_status()
            return False, load_message
        except Exception as exc:
            return False, f"Failed to import custom catalog: {exc}"

    def _format_catalog_status(self) -> str:
        if not self._use_tag_catalog:
            return "Catalog mode: ON - Bundled default"
        catalog = getattr(self, "_catalog", None)
        if not isinstance(catalog, CsvCatalog):
            selected = self._resolve_catalog_path()
            if not selected:
                return "Catalog mode: ON - No catalog selected"
            source_label = "Bundled" if self._catalog_source == "bundled" else "Custom"
            return f"Catalog mode: ON - {source_label}: {os.path.basename(selected)} (not loaded)"
        source_label = "Bundled" if self._catalog_source == "bundled" else "Custom"
        filename = os.path.basename(catalog._path)
        tag_count = len(getattr(catalog, "_all_tags", set()))
        alias_count = len(getattr(catalog, "_aliases", {}))
        return f"Catalog mode: ON - {source_label}: {filename}\nTags: {tag_count:,} | Aliases: {alias_count:,}"

    def _active_catalog(self) -> Optional[TagCatalogProvider]:
        if not self._use_tag_catalog and self._catalog_source != "bundled":
            self._set_catalog_source("bundled")
        if not self._resolve_catalog_path():
            return None
        catalog = getattr(self, "_catalog", None)
        if not isinstance(catalog, TagCatalogProvider) or not catalog.enabled():
            ok, msg = self._load_tag_catalog()
            self._update_catalog_status(msg)
            catalog = getattr(self, "_catalog", None)
            if not ok:
                if self._catalog_source == "custom":
                    self._set_catalog_source("bundled")
                    ok, msg = self._load_tag_catalog()
                    self._update_catalog_status(msg)
                    catalog = getattr(self, "_catalog", None)
                    if not ok:
                        return None
                else:
                    return None
        try:
            if hasattr(catalog, "maybe_reload"):
                catalog.maybe_reload()  # type: ignore[call-arg]
        except Exception:
            pass
        return catalog if isinstance(catalog, TagCatalogProvider) and catalog.enabled() else None

    def _load_tag_catalog(self) -> Tuple[bool, str]:
        path_value = self._resolve_catalog_path()
        if not path_value:
            self._set_catalog_source("bundled")
            path_value = self._resolve_catalog_path()
            if not path_value:
                self._catalog = NoopCatalog()
                return False, "Catalog load failed: bundled catalog path is not set"
        valid, validation_msg = self._validate_csv_format(path_value)
        if not valid:
            self._catalog = NoopCatalog()
            return False, f"Catalog load failed: {validation_msg}"
        try:
            self._catalog = CsvCatalog(path_value)
            self._tag_catalog_status_text = self._format_catalog_status()
            return True, self._tag_catalog_status_text
        except Exception as exc:
            self._catalog = NoopCatalog()
            return False, f"Catalog load failed: {exc}"

    def _render_tag_diag(self, diag: Dict[str, object]) -> str:
        if not diag:
            return "(run a search to populate)"
        mode = diag.get("mode", "catalog")
        rules = diag.get("rules") or {}
        kept = diag.get("kept") or []
        dropped = diag.get("dropped") or []
        normalized = diag.get("normalized") or []
        unknown = diag.get("unknown") or []
        lines = [f"**Mode:** {mode}"]
        if isinstance(rules, dict) and rules:
            active = [k for k, v in rules.items() if v]
            lines.append(f"Active rules: {', '.join(active) if active else 'none'}")
        lines.append(
            f"Kept: {len(kept)} | Dropped: {len(dropped)} | Normalized: {len(normalized)} | Unknown: {len(unknown)}"
        )
        if unknown:
            sample = []
            for entry in unknown[:3]:
                if isinstance(entry, dict):
                    tag = entry.get("tag") or entry.get("candidate")
                    suggestions = entry.get("suggestions") or []
                    if tag:
                        sample.append(
                            f"`{tag}` -> {', '.join(suggestions[:3]) if suggestions else 'no suggestions'}"
                        )
            if sample:
                lines.append("Hints:\n- " + "\n- ".join(sample))
        return "\n".join(lines)

    def _update_tag_diag(self) -> None:
        try:
            if self._tag_diag_md is not None:
                self._tag_diag_md.update(value=self._render_tag_diag(self._tag_catalog_diag))
        except Exception:
            pass

    def _log_patch_event(self, level: str, message: str) -> None:
        logger_fn = getattr(_ranbooru_logger, level, None)
        if callable(logger_fn):
            logger_fn(message)
        else:
            _ranbooru_logger.info(message)

    def _verify_patch_target(
        self, target: object, method_name: str, *, require_callable: bool = True
    ) -> bool:
        ok, message = rb_adetailer_integration.verify_patch_target(
            target, method_name, require_callable=require_callable
        )
        self._log_patch_event("info" if ok else "warning", message)
        return ok

    def _apply_optional_catalog(
        self,
        tags: List[str],
        *,
        keep_hair_eye: bool,
        drop_series: bool,
        drop_characters: bool,
        drop_textual: bool,
    ) -> Tuple[List[str], Dict[str, object]]:
        diag: Dict[str, object] = {
            "mode": "catalog",
            "rules": {
                "drop_series": bool(drop_series),
                "drop_characters": bool(drop_characters),
                "drop_textual": bool(drop_textual),
                "keep_hair_eye": bool(keep_hair_eye),
            },
            "kept": [],
            "dropped": [],
            "normalized": [],
            "unknown": [],
        }
        catalog = self._active_catalog()
        if not catalog:
            self._tag_catalog_diag = diag
            self._update_tag_diag()
            return list(tags), diag

        subject_anchors = getattr(self, "_catalog_subject_anchors", None)
        if subject_anchors is None:
            subject_anchors = {s.replace(" ", "_") for s in rb_tag_pipeline._SUBJECT_TAGS}
            self._catalog_subject_anchors = subject_anchors

        kept: List[str] = []
        seen: Set[str] = set()
        normalized_records: List[Dict[str, str]] = []
        dropped_records: List[Dict[str, str]] = []
        unknown_records: List[Dict[str, object]] = []
        preserved_hair_eye: Set[str] = set()
        original_subjects: List[str] = []

        for raw in tags:
            tag = (raw or "").strip()
            if not tag:
                continue
            negated = tag.startswith("-")
            base = tag[1:] if negated else tag
            base_compact = re.sub(r"\s+", "_", base.strip().lower())
            base_compact = re.sub(r"_+", "_", base_compact)
            if not base_compact:
                continue
            if ":" in base_compact:
                canonical = base_compact
            else:
                canonical = catalog.resolve_alias(base_compact) or base_compact
                if canonical != base_compact:
                    normalized_records.append({"from": base_compact, "to": canonical})
            final_tag = f"-{canonical}" if negated else canonical
            if final_tag in seen:
                continue
            seen.add(final_tag)

            category = catalog.category(canonical)
            is_hair = catalog.is_hair(canonical)
            is_eye = catalog.is_eye(canonical)
            if canonical in subject_anchors:
                original_subjects.append(canonical)

            reason: Optional[str] = None
            if drop_series and category == 3:
                reason = "series"
            elif drop_characters and category == 4:
                reason = "character"
            elif drop_textual and catalog.is_textual(canonical):
                reason = "textual"

            if reason and not (keep_hair_eye and (is_hair or is_eye)):
                dropped_records.append({"tag": final_tag, "reason": reason})
                continue

            if keep_hair_eye and (is_hair or is_eye):
                preserved_hair_eye.add(final_tag)

            if not catalog.has(canonical) and ":" not in canonical:
                suggestions = catalog.suggestions(canonical, self._tag_catalog_linter_limit)
                unknown_records.append({"tag": canonical, "suggestions": suggestions})

            kept.append(final_tag)

        if original_subjects and not any(t.lstrip("-") in subject_anchors for t in kept):
            kept.append(original_subjects[0])

        diag["kept"] = kept
        diag["dropped"] = dropped_records
        diag["normalized"] = normalized_records
        diag["unknown"] = unknown_records
        if preserved_hair_eye:
            diag["preserved"] = sorted(preserved_hair_eye)

        self._tag_catalog_diag = diag
        self._update_tag_diag()
        print(
            f"[TagCatalog] mode={diag['mode']} kept={len(kept)} dropped={len(dropped_records)} unknown={len(unknown_records)}"
        )
        return kept, diag

    def _load_personal_lists(self) -> Tuple[Set[str], Set[str]]:
        personal = set(self._read_list_file(PERSONAL_REMOVE_FILE))
        favorites = set(self._read_list_file(FAVORITES_FILE))
        self._personal_remove_tags = personal
        self._favorite_tags = favorites
        return personal, favorites

    def _normalize_cached(self, tag: str, cache: Dict[str, str]) -> str:
        if tag in cache:
            return cache[tag]
        normalized = self._normalize_tag(tag)
        if normalized:
            catalog = self._active_catalog()
            if catalog:
                catalog_token = normalized.replace(" ", "_")
                canonical = catalog.resolve_alias(catalog_token)
                if canonical and canonical != catalog_token:
                    normalized = canonical.replace("_", " ")
        cache[tag] = normalized
        return normalized

    def _expand_with_synonyms(self, normalized_tag: str, target_set: Set[str]) -> None:
        rb_tag_pipeline.expand_with_synonyms(normalized_tag, target_set, self._synonym_lookup)

    def _build_removal_context(
        self, removal_raw: Iterable[str], favorites_raw: Iterable[str]
    ) -> Dict[str, object]:
        return rb_tag_pipeline.build_removal_context(
            removal_raw,
            favorites_raw,
            self._synonym_lookup,
        )

    def _tag_matches_removal(
        self, normalized_tag: str, context: Optional[Dict[str, object]]
    ) -> bool:
        return rb_tag_pipeline.tag_matches_removal(normalized_tag, context)

    def _parse_user_tags(self, text: str) -> List[str]:
        if not text or not isinstance(text, str):
            return []
        segments = [seg.strip() for seg in re.split(r"[\n,]+", text) if seg and seg.strip()]
        if not segments:
            return []
        seen: Set[str] = set()
        ordered: List[str] = []
        for seg in segments:
            norm = self._normalize_tag(seg) or seg.casefold()
            if norm in seen:
                continue
            seen.add(norm)
            ordered.append(seg.strip())
        return ordered

    def _coerce_selection(self, selection: Optional[object]) -> List[str]:
        if selection is None:
            return []
        if isinstance(selection, str):
            return [selection]
        if isinstance(selection, (list, tuple)):
            return [item for item in selection if isinstance(item, str) and item.strip()]
        return []

    def _merge_tag_lists(self, base: List[str], additions: List[str]) -> List[str]:
        merged: List[str] = []
        seen: Set[str] = set()
        for tag in list(base) + list(additions):
            cleaned = (tag or "").strip()
            if not cleaned:
                continue
            key = self._normalize_tag(cleaned) or cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(cleaned)
        return merged

    def _apply_list_operation(
        self,
        list_key: str,
        *,
        additions: Optional[List[str]] = None,
        removals: Optional[List[str]] = None,
        imported: Optional[List[str]] = None,
        dedupe: bool = False,
    ) -> List[str]:
        path = self._USER_LIST_PATHS[list_key]
        existing = self._read_list_file(path)
        working = list(existing)
        combined_additions: List[str] = []
        if additions:
            combined_additions.extend(additions)
        if imported:
            combined_additions.extend(imported)
        if combined_additions:
            working = self._merge_tag_lists(working, combined_additions)
        if removals:
            removal_keys = {
                self._normalize_tag(tag) or tag.casefold()
                for tag in removals
                if isinstance(tag, str)
            }
            if removal_keys:
                working = [
                    tag
                    for tag in working
                    if (self._normalize_tag(tag) or tag.casefold()) not in removal_keys
                ]
        if dedupe:
            working = self._merge_tag_lists([], working)
        self._write_list_file(path, working)
        self._load_personal_lists()
        return working

    def _ui_add_personal_tags(self, tags_text: str, current_selection: Optional[object]):
        additions = self._parse_user_tags(tags_text)
        new_list = self._apply_list_operation("personal", additions=additions)
        selection = additions or self._coerce_selection(current_selection)
        selection = [tag for tag in selection if tag in new_list]
        return (
            _gr_component_update(gr.Dropdown, choices=new_list, value=selection),
            _gr_component_update(gr.Textbox, value=""),
        )

    def _ui_remove_personal_tags(self, selected: Optional[object]):
        removals = self._coerce_selection(selected)
        new_list = (
            self._apply_list_operation("personal", removals=removals)
            if removals
            else self._read_list_file(PERSONAL_REMOVE_FILE)
        )
        return _gr_component_update(gr.Dropdown, choices=new_list, value=[])

    def _ui_dedupe_personal_list(self):
        new_list = self._apply_list_operation("personal", dedupe=True)
        return _gr_component_update(gr.Dropdown, choices=new_list, value=new_list)

    def _ui_import_personal_list(self, uploaded_file: Optional[dict]):
        if not uploaded_file:
            current = self._read_list_file(PERSONAL_REMOVE_FILE)
            return _gr_component_update(
                gr.Dropdown, choices=current, value=current
            ), _gr_component_update(gr.File, value=None)
        data = uploaded_file.get("data") if isinstance(uploaded_file, dict) else None
        text = ""
        if isinstance(data, bytes):
            try:
                text = data.decode("utf-8", errors="ignore")
            except Exception as exc:
                print(f"[R Lists] Failed to decode personal import: {exc}")
        additions = self._parse_user_tags(text)
        new_list = self._apply_list_operation("personal", additions=additions)
        selection = [tag for tag in additions if tag in new_list]
        return _gr_component_update(
            gr.Dropdown, choices=new_list, value=selection
        ), _gr_component_update(gr.File, value=None)

    def _ui_export_personal_list(self):
        return PERSONAL_REMOVE_FILE

    def _ui_add_favorite_tags(self, tags_text: str, current_selection: Optional[object]):
        additions = self._parse_user_tags(tags_text)
        new_list = self._apply_list_operation("favorites", additions=additions)
        selection = additions or self._coerce_selection(current_selection)
        selection = [tag for tag in selection if tag in new_list]
        return (
            _gr_component_update(gr.Dropdown, choices=new_list, value=selection),
            _gr_component_update(gr.Textbox, value=""),
        )

    def _ui_remove_favorite_tags(self, selected: Optional[object]):
        removals = self._coerce_selection(selected)
        new_list = (
            self._apply_list_operation("favorites", removals=removals)
            if removals
            else self._read_list_file(FAVORITES_FILE)
        )
        return _gr_component_update(gr.Dropdown, choices=new_list, value=[])

    def _ui_dedupe_favorite_list(self):
        new_list = self._apply_list_operation("favorites", dedupe=True)
        return _gr_component_update(gr.Dropdown, choices=new_list, value=new_list)

    def _ui_import_favorite_list(self, uploaded_file: Optional[dict]):
        if not uploaded_file:
            current = self._read_list_file(FAVORITES_FILE)
            return _gr_component_update(
                gr.Dropdown, choices=current, value=current
            ), _gr_component_update(gr.File, value=None)
        data = uploaded_file.get("data") if isinstance(uploaded_file, dict) else None
        text = ""
        if isinstance(data, bytes):
            try:
                text = data.decode("utf-8", errors="ignore")
            except Exception as exc:
                print(f"[R Lists] Failed to decode favorites import: {exc}")
        additions = self._parse_user_tags(text)
        new_list = self._apply_list_operation("favorites", additions=additions)
        selection = [tag for tag in additions if tag in new_list]
        return _gr_component_update(
            gr.Dropdown, choices=new_list, value=selection
        ), _gr_component_update(gr.File, value=None)

    def _ui_export_favorite_list(self):
        return FAVORITES_FILE

    def _get_saved_gelbooru_credentials(self) -> Optional[Dict[str, str]]:
        creds = self._gelbooru_saved_credentials
        if isinstance(creds, dict):
            raw_api = creds.get("api_key")
            raw_uid = creds.get("user_id")
            api_key = _sanitize_gelbooru_credential(raw_api)
            user_id = _sanitize_gelbooru_credential(raw_uid)
            if (not api_key and isinstance(raw_uid, str)) or (
                not user_id and isinstance(raw_api, str)
            ):
                combined = f"{raw_api}&{raw_uid}"
                for seg in str(combined).split("&"):
                    segl = seg.lower().strip()
                    if segl.startswith("api_key=") and not api_key:
                        api_key = seg.split("=", 1)[1].strip()
                    if segl.startswith("user_id=") and not user_id:
                        user_id = seg.split("=", 1)[1].strip()
            api_key = _sanitize_gelbooru_credential(api_key)
            user_id = _sanitize_gelbooru_credential(user_id)
            if api_key and user_id:
                return {"api_key": api_key, "user_id": user_id}
        return None

    def _resolve_gelbooru_credentials(
        self, runtime_api_key: Optional[str], runtime_user_id: Optional[str]
    ) -> Optional[Dict[str, str]]:
        runtime_api_key = _sanitize_gelbooru_credential(runtime_api_key)
        runtime_user_id = _sanitize_gelbooru_credential(runtime_user_id)
        if (runtime_api_key and ("=" in runtime_api_key or "&" in runtime_api_key)) or (
            runtime_user_id and ("=" in runtime_user_id or "&" in runtime_user_id)
        ):
            combined = f"{runtime_api_key}&{runtime_user_id}"
            r_api = runtime_api_key
            r_uid = runtime_user_id
            for seg in str(combined).split("&"):
                segl = seg.lower().strip()
                if segl.startswith("api_key="):
                    r_api = seg.split("=", 1)[1].strip()
                elif segl.startswith("user_id="):
                    r_uid = seg.split("=", 1)[1].strip()
            runtime_api_key = _sanitize_gelbooru_credential(r_api)
            runtime_user_id = _sanitize_gelbooru_credential(r_uid)
        if runtime_api_key and runtime_user_id:
            return {"api_key": runtime_api_key, "user_id": runtime_user_id}
        saved = self._get_saved_gelbooru_credentials()
        if saved:
            return saved
        return None

    def _gelbooru_saved_message(self) -> str:
        return f"? Using saved Gelbooru credentials from `{GELBOORU_CREDENTIALS_FILE}`."

    def _ui_save_gelbooru_credentials(self, api_key: Optional[str], user_id: Optional[str]):
        api_key = _sanitize_gelbooru_credential(api_key)
        user_id = _sanitize_gelbooru_credential(user_id)
        if not api_key or not user_id:
            warn = "Please enter both API Key and User ID before saving."
            return (
                _gr_component_update(gr.Markdown, value=warn, visible=True),
                _gr_update(visible=True),
                _gr_component_update(gr.Button, visible=False),
                _gr_component_update(gr.Textbox, value=api_key),
                _gr_component_update(gr.Textbox, value=user_id),
            )
        if _save_gelbooru_credentials_to_disk(api_key, user_id):
            self._gelbooru_saved_credentials = {"api_key": api_key, "user_id": user_id}
            message = self._gelbooru_saved_message()
            return (
                _gr_component_update(gr.Markdown, value=message, visible=True),
                _gr_update(visible=False),
                _gr_component_update(gr.Button, visible=True),
                _gr_component_update(gr.Textbox, value=""),
                _gr_component_update(gr.Textbox, value=""),
            )
        error = "Failed to save Gelbooru credentials. Check console for details."
        return (
            _gr_component_update(gr.Markdown, value=error, visible=True),
            _gr_update(visible=True),
            _gr_component_update(gr.Button, visible=False),
            _gr_component_update(gr.Textbox, value=api_key),
            _gr_component_update(gr.Textbox, value=user_id),
        )

    def _ui_clear_gelbooru_credentials(self):
        if _clear_gelbooru_credentials_from_disk():
            self._gelbooru_saved_credentials = None
            return (
                _gr_component_update(
                    gr.Markdown, value="Saved Gelbooru credentials cleared.", visible=True
                ),
                _gr_update(visible=True),
                _gr_component_update(gr.Button, visible=False),
                _gr_component_update(gr.Textbox, value=""),
                _gr_component_update(gr.Textbox, value=""),
            )
        warn = "Gelbooru credentials file could not be removed."
        return (
            _gr_component_update(gr.Markdown, value=warn, visible=True),
            _gr_update(visible=False),
            _gr_component_update(gr.Button, visible=True),
            _gr_component_update(gr.Textbox, value=""),
            _gr_component_update(gr.Textbox, value=""),
        )

    def _update_gelbooru_ui_visibility(self, booru_name: Optional[str]):
        booru_name = (booru_name or "").strip().lower()
        has_saved = self._get_saved_gelbooru_credentials() is not None
        if booru_name == "gelbooru":
            if has_saved:
                message = self._gelbooru_saved_message()
                return (
                    _gr_update(visible=False),
                    _gr_component_update(gr.Markdown, value=message, visible=True),
                    _gr_component_update(gr.Button, visible=True),
                    _gr_component_update(gr.Textbox, value=""),
                    _gr_component_update(gr.Textbox, value=""),
                )
            return (
                _gr_update(visible=True),
                _gr_component_update(gr.Markdown, value="", visible=False),
                _gr_component_update(gr.Button, visible=False),
                _gr_component_update(gr.Textbox, value=""),
                _gr_component_update(gr.Textbox, value=""),
            )
        # Hide for non-Gelbooru selections
        return (
            _gr_update(visible=False),
            _gr_component_update(gr.Markdown, value="", visible=False),
            _gr_component_update(gr.Button, visible=False),
            _gr_component_update(gr.Textbox, value=""),
            _gr_component_update(gr.Textbox, value=""),
        )

    def _update_gelbooru_compat_visibility(self, booru_name: Optional[str]):
        booru_name = (booru_name or "").strip().lower()
        visible = booru_name == "gelbooru-compatible"
        return (
            _gr_update(visible=visible),
            _gr_component_update(
                gr.Textbox,
                value=self._gelbooru_compat_base_url if visible else self._gelbooru_compat_base_url,
            ),
        )

    def _ui_set_gelbooru_compat_base_url(self, base_url: Optional[str]):
        sanitized = _sanitize_gelbooru_compat_base_url(base_url)
        self._gelbooru_compat_base_url = sanitized
        return _gr_component_update(gr.Textbox, value=self._gelbooru_compat_base_url)

    def _extract_color_tags(self, text: str) -> tuple[set[str], set[str]]:
        hair_tags: set[str] = set()
        eye_tags: set[str] = set()
        if not text or not isinstance(text, str):
            return hair_tags, eye_tags
        catalog = self._active_catalog()
        tokens = [token.strip() for token in re.split(r"[\s,]+", text) if token.strip()]
        for token in tokens:
            normalized = (self._normalize_tag(token) or "").strip().lower()
            if not normalized:
                normalized = self._canonicalize_raw_tag(token)
            if not normalized:
                continue
            if catalog:
                token_key = normalized.replace(" ", "_")
                if catalog.is_hair(token_key):
                    canonical = catalog.resolve_alias(token_key)
                    hair_tags.add(canonical.replace("_", " ") if canonical else normalized)
                if catalog.is_eye(token_key):
                    canonical = catalog.resolve_alias(token_key)
                    eye_tags.add(canonical.replace("_", " ") if canonical else normalized)
            if normalized in rb_tag_pipeline._HAIR_COLOR_TAGS_NORMALIZED:
                hair_tags.add(normalized)
            if normalized in rb_tag_pipeline._EYE_COLOR_TAGS_NORMALIZED:
                eye_tags.add(normalized)
        return hair_tags, eye_tags

    def _extract_subject_tags(self, text: str) -> set:
        return rb_tag_pipeline.extract_subject_tags(text)

    def _normalize_post_tags(
        self, post: Optional[Dict[str, object]], cache: Dict[str, str]
    ) -> Tuple[Set[str], Dict[str, List[str]]]:
        catalog = self._active_catalog()
        return rb_tag_pipeline.normalize_post_tags(
            post,
            cache,
            catalog.resolve_alias if catalog else None,
        )

    def _post_rejected_by_filter(
        self,
        post: Optional[Dict[str, object]],
        *,
        filter_ctx: Optional[Dict[str, object]],
        toggles: Tuple[bool, bool, bool, bool, bool, bool, bool, bool, bool, bool],
        base_colors: Tuple[Set[str], Set[str]],
        allowed_subjects: Set[str],
        cache: Dict[str, str],
        favorites_guard: Set[str],
    ) -> Tuple[bool, Optional[Dict[str, object]]]:
        catalog = self._active_catalog()
        return rb_tag_pipeline.post_rejected_by_filter(
            post,
            filter_ctx=filter_ctx,
            toggles=toggles,
            base_colors=base_colors,
            allowed_subjects=allowed_subjects,
            cache=cache,
            favorites_guard=favorites_guard,
            catalog_resolve_alias_fn=catalog.resolve_alias if catalog else None,
            catalog_is_textual_fn=catalog.is_textual if catalog else None,
            catalog_is_hair_fn=catalog.is_hair if catalog else None,
            catalog_is_eye_fn=catalog.is_eye if catalog else None,
            catalog_category_fn=catalog.category if catalog else None,
        )

    def _apply_strict_img2img_prefilter(
        self,
        posts: List[Dict[str, object]],
        *,
        api: Booru,
        tags_query: str,
        post_id: Optional[str],
        num_images_needed: int,
        max_pages: int,
        filter_ctx: Optional[Dict[str, object]],
        toggles: Tuple[bool, bool, bool, bool, bool, bool, bool, bool, bool, bool],
        base_colors: Tuple[Set[str], Set[str]],
        allowed_subjects: Set[str],
    ) -> Tuple[List[Dict[str, object]], List[Dict[str, object]], bool, bool]:
        if not posts:
            return [], [], False, False

        if not getattr(self, "_strict_img2img_fetch", True):
            return list(posts), [], False, False

        cache = getattr(self, "_tag_normal_cache", {})
        if not isinstance(cache, dict):
            cache = {}
            self._tag_normal_cache = cache

        favorites_guard: Set[str] = set()
        if filter_ctx:
            favorites_guard = set(filter_ctx.get("favorites", frozenset()))  # type: ignore[arg-type]

        hair_colors, eye_colors = base_colors
        base_colors = (set(hair_colors or []), set(eye_colors or []))
        allowed_subjects = set(allowed_subjects or [])

        kept: List[Dict[str, object]] = []
        rejections: List[Dict[str, object]] = []
        seen_keys: Set[Tuple[Optional[str], Optional[str], Optional[str]]] = set()

        def _post_key(
            entry: Dict[str, object],
        ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
            return (
                str(entry.get("booru_name")).lower() if entry.get("booru_name") else None,
                entry.get("id"),
                entry.get("file_url"),
            )

        original_posts = list(posts)

        for post in original_posts:
            key = _post_key(post)
            seen_keys.add(key)
            rejected, reason = self._post_rejected_by_filter(
                post,
                filter_ctx=filter_ctx,
                toggles=toggles,
                base_colors=base_colors,
                allowed_subjects=allowed_subjects,
                cache=cache,
                favorites_guard=favorites_guard,
            )
            if rejected:
                reason_entry = {
                    "post_id": post.get("id"),
                    "booru": post.get("booru_name"),
                    "matched_tag": reason.get("tag") if reason else None,
                    "normalized_tag": reason.get("norm") if reason else None,
                    "rule_type": reason.get("rule") if reason else None,
                    "bucket": reason.get("bucket") if reason else None,
                }
                rejections.append(reason_entry)
            else:
                kept.append(post)

        if len(kept) >= num_images_needed or post_id:
            return kept, rejections, True, False

        relaxed = False
        rounds = max(0, int(STRICT_IMG2IMG_EXTRA_ROUNDS))
        for round_index in range(rounds):
            try:
                extra_posts = api.get_posts(
                    tags_query=tags_query, max_pages=max_pages, post_id=None
                )
            except Exception as exc:
                print(f"[R Strict] Warn: extra fetch round {round_index + 1} failed: {exc}")
                break
            if not extra_posts:
                continue
            for post in extra_posts:
                key = _post_key(post)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                rejected, reason = self._post_rejected_by_filter(
                    post,
                    filter_ctx=filter_ctx,
                    toggles=toggles,
                    base_colors=base_colors,
                    allowed_subjects=allowed_subjects,
                    cache=cache,
                    favorites_guard=favorites_guard,
                )
                if rejected:
                    reason_entry = {
                        "post_id": post.get("id"),
                        "booru": post.get("booru_name"),
                        "matched_tag": reason.get("tag") if reason else None,
                        "normalized_tag": reason.get("norm") if reason else None,
                        "rule_type": reason.get("rule") if reason else None,
                        "bucket": reason.get("bucket") if reason else None,
                        "extra_round": round_index + 1,
                    }
                    rejections.append(reason_entry)
                    continue
                kept.append(post)
                if len(kept) >= num_images_needed:
                    break
            if len(kept) >= num_images_needed:
                break

        if len(kept) < num_images_needed:
            print(
                "[R Strict] Img2Img strict pre-filter exhausted candidates; relaxing to prompt-level filtering"
            )
            relaxed = True
            kept = list(original_posts)

        return kept, rejections, True, relaxed

    def _log_generation_reference(self, p):
        if not getattr(self, "_log_prompt_sources", False):
            return
        try:
            prompts = list(getattr(self, "_final_prompts_snapshot", []))
            if not prompts:
                prompt_attr = getattr(p, "prompt", "")
                if isinstance(prompt_attr, list):
                    prompts = list(prompt_attr)
                elif isinstance(prompt_attr, str):
                    prompts = [prompt_attr]
            prompts = [pr for pr in prompts if isinstance(pr, str) and pr.strip()]
            if not prompts:
                return
            seeds = list(getattr(p, "all_seeds", []) or [])
            posts = list(getattr(self, "_posts_used_for_generation", []))
            post_urls = (
                list(getattr(self, "_last_post_urls", []))
                if hasattr(self, "_last_post_urls")
                else []
            )
            log_path = os.path.join(LOG_DIR, "prompt_sources.txt")
            booru = getattr(self, "_current_booru_name", "unknown")
            base_prompt = getattr(self, "original_prompt", getattr(p, "prompt", ""))
            negative_prompt = getattr(p, "negative_prompt", "")
            text_lines = [
                "---",
                (
                    f"{datetime.now().isoformat()} | booru={booru} | "
                    f"reuse_cached={getattr(self, '_reuse_cached_posts', False)}"
                ),
                f"base_prompt={base_prompt}",
            ]
            if isinstance(negative_prompt, str) and negative_prompt:
                text_lines.append(f"negative_prompt={negative_prompt}")
            for idx, prompt in enumerate(prompts):
                seed = seeds[idx] if idx < len(seeds) else getattr(p, "seed", None)
                text_lines.append(f"[{idx+1}] seed={seed}")
                text_lines.append(f"prompt={prompt}")
                post = posts[idx] if idx < len(posts) else None
                source_url = post_urls[idx] if idx < len(post_urls) else None
                if not source_url and post:
                    source_url = get_original_post_url(post)
                if not source_url and post and post.get("file_url"):
                    source_url = post.get("file_url")
                if source_url:
                    text_lines.append(f"source={source_url}")
                if post and post.get("id") is not None:
                    text_lines.append(f"post_id={post.get('id')}")
                text_lines.append("")
            rb_user_store.append_text_log(log_path, text_lines)
            try:
                json_payload = {
                    "timestamp": datetime.now().isoformat(),
                    "booru": booru,
                    "mode": (
                        "img2img" if bool(getattr(self, "_post_use_img2img", False)) else "txt2img"
                    ),
                    "strict_fetch_enabled": bool(getattr(self, "_strict_img2img_fetch", False)),
                    "strict_prefilter_active": bool(getattr(self, "_strict_img2img_active", False)),
                    "strict_prefilter_relaxed": bool(
                        getattr(self, "_strict_img2img_relaxed", False)
                    ),
                    "strict_rejections": list(getattr(self, "_strict_img2img_rejections", [])),
                    "kept_post_ids": [post.get("id") for post in posts if isinstance(post, dict)],
                    "prompts": prompts,
                    "negative_prompt": (
                        negative_prompt if isinstance(negative_prompt, str) else None
                    ),
                    "reuse_cached": bool(getattr(self, "_reuse_cached_posts", False)),
                }
                rb_user_store.append_prompt_log(PROMPT_LOG_JSONL, json_payload)
            except Exception as exc:
                print(f"[R Log] Failed to append JSONL prompt record: {exc}")
            self._posts_used_for_generation = []
            self._final_prompts_snapshot = []
            self._final_negative_prompts_snapshot = []
        except Exception as exc:
            print(f"[R Log] Failed to log prompt sources: {exc}")

    def _ensure_pil_images_in_processed(self, processed_obj):
        try:
            if hasattr(processed_obj, "images") and isinstance(processed_obj.images, list):
                for i, im in enumerate(list(processed_obj.images)):
                    pil_im = self._ensure_pil_image(im)
                    if pil_im is not None:
                        processed_obj.images[i] = pil_im
            # Ensure single image too
            if hasattr(processed_obj, "image"):
                processed_obj.image = self._ensure_pil_image(getattr(processed_obj, "image"))
        except Exception:
            pass

    def _ensure_pil_in_processing(self, p):
        try:
            if hasattr(p, "init_images") and isinstance(p.init_images, list) and p.init_images:
                for i, im in enumerate(list(p.init_images)):
                    pil_im = self._ensure_pil_image(im)
                    if pil_im is not None:
                        p.init_images[i] = pil_im
        except Exception:
            pass

    def _load_cn_external_code(self):
        return rb_controlnet_integration.load_external_code(EXTENSION_ROOT)

    def _render_platform_diagnostics(self) -> str:
        gradio_version = getattr(gr, "__version__", "unknown")
        input_accordion_source = "modules.ui_components.InputAccordion"
        if InputAccordion is gr.Accordion:
            input_accordion_source = "gr.Accordion fallback"
        controlnet_ok = False
        controlnet_error = ""
        try:
            self._load_cn_external_code()
            controlnet_ok = True
        except Exception as exc:
            controlnet_error = str(exc)
        try:
            adetailer_detected = bool(self._native_adetailer_detected())
        except Exception:
            adetailer_detected = False

        lines = [
            f"**Gradio Version:** {gradio_version}",
            f"**InputAccordion Source:** {input_accordion_source}",
            f"**ControlNet External Code:** {'available' if controlnet_ok else 'missing'}",
            f"**ADetailer Detected:** {'yes' if adetailer_detected else 'no'}",
            "**Optional Autotagger:** removed from RanbooruX",
        ]
        if controlnet_error:
            lines.append(f"**ControlNet Detail:** `{controlnet_error}`")
        return "\n\n".join(lines)

    def _toggle_platform_diagnostics(self, currently_visible: bool):
        new_visible = not bool(currently_visible)
        button_text = "Hide Platform Diagnostics" if new_visible else "Show Platform Diagnostics"
        body = self._render_platform_diagnostics() if new_visible else ""
        return (
            new_visible,
            _gr_component_update(gr.Markdown, value=body, visible=new_visible),
            _gr_component_update(gr.Button, value=button_text),
        )

    def get_files(self, path):
        files = []
        try:
            for file in os.listdir(path):
                if file.endswith(".txt"):
                    files.append(file)
        except FileNotFoundError:
            print(f"[R] Warn: Dir not found: {path}")
        return files

    def title(self):
        return "RanbooruX"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def refresh_ser(self):
        return _gr_update(choices=self.get_files(USER_SEARCH_DIR))

    def refresh_rem(self):
        return _gr_update(choices=self.get_files(USER_REMOVE_DIR))

    def _build_catalog_ui_section(self):
        """Tag catalog toggle, file picker, validation/import, and diagnostics.

        Creates the Danbooru Tag Catalog group (toggle, source, custom path, import,
        validation, reload, status) and the Platform Diagnostics toggle. Returns the
        two components that must appear in the script-args component list.

        Must be called inside ``gr.Group()`` that lives inside the Removal Filters
        accordion.
        """
        gr.Markdown("**Danbooru Tag Catalog**")

        use_tag_catalog = gr.Checkbox(
            label="Use Danbooru Tag Catalog",
            value=bool(self._use_tag_catalog),
            info="Enable category-aware filtering and alias resolution.",
        )

        catalog_source = gr.Radio(
            ["Bundled", "Custom file"],
            label="Catalog Source",
            value=("Custom file" if self._catalog_source == "custom" else "Bundled"),
            visible=bool(self._use_tag_catalog),
        )

        with gr.Group(
            visible=bool(self._use_tag_catalog and self._catalog_source == "custom")
        ) as custom_catalog_group:
            catalog_upload = gr.File(label="Upload CSV", file_types=[".csv"], file_count="single")
            catalog_path = gr.Textbox(
                label="Custom CSV Path",
                value=self._custom_catalog_path,
                placeholder="/path/to/custom_catalog.csv",
            )
            with gr.Row():
                catalog_import_btn = gr.Button("Import Custom Catalog")
                catalog_validate_btn = gr.Button("Validate CSV")

        reload_catalog = gr.Button("Reload Catalog", visible=bool(self._use_tag_catalog))
        catalog_status = gr.Markdown(self._tag_catalog_status_text or "Catalog mode: OFF")

        self._catalog_status_md = catalog_status
        self._tag_diag_md = None

        # --- inner event handlers ---------------------------------------------------

        def _ui_toggle_catalog(enabled: bool):
            self._use_tag_catalog = bool(enabled)
            if not self._use_tag_catalog:
                self._set_catalog_source("bundled")
            ok, message = self._load_tag_catalog()
            if not ok:
                self._catalog = NoopCatalog()
            self._tag_catalog_status_text = message
            self._save_tag_catalog_preferences()
            return (
                _gr_component_update(
                    gr.Radio,
                    visible=self._use_tag_catalog,
                    value=("Custom file" if self._catalog_source == "custom" else "Bundled"),
                ),
                _gr_component_update(
                    gr.Group,
                    visible=bool(self._use_tag_catalog and self._catalog_source == "custom"),
                ),
                _gr_component_update(
                    gr.Textbox,
                    visible=bool(self._use_tag_catalog and self._catalog_source == "custom"),
                    value=self._custom_catalog_path,
                ),
                _gr_component_update(gr.Button, visible=self._use_tag_catalog),
                _gr_component_update(gr.Markdown, value=self._tag_catalog_status_text),
            )

        def _ui_set_catalog_source(source_label: str):
            source = "custom" if (source_label or "") == "Custom file" else "bundled"
            self._set_catalog_source(source)
            if self._use_tag_catalog:
                ok, message = self._load_tag_catalog()
                if not ok:
                    self._catalog = NoopCatalog()
                    self._tag_catalog_status_text = message
                else:
                    self._tag_catalog_status_text = self._format_catalog_status()
            else:
                self._tag_catalog_status_text = self._format_catalog_status()
            self._save_tag_catalog_preferences()
            self._update_tag_diag()
            return (
                _gr_component_update(
                    gr.Group,
                    visible=bool(self._use_tag_catalog and self._catalog_source == "custom"),
                ),
                _gr_component_update(
                    gr.Textbox,
                    visible=bool(self._use_tag_catalog and self._catalog_source == "custom"),
                    value=self._custom_catalog_path,
                ),
                _gr_component_update(gr.Markdown, value=self._tag_catalog_status_text),
            )

        def _ui_set_catalog_path(path_value: str):
            self._custom_catalog_path = (path_value or "").strip()
            self._tag_catalog_path = self._custom_catalog_path
            if self._use_tag_catalog and self._catalog_source == "custom":
                if self._custom_catalog_path:
                    ok, message = self._load_tag_catalog()
                    if not ok:
                        self._catalog = NoopCatalog()
                        self._tag_catalog_status_text = message
                    else:
                        self._tag_catalog_status_text = self._format_catalog_status()
                else:
                    self._catalog = NoopCatalog()
                    self._tag_catalog_status_text = "Catalog mode: ON - No path set"
            else:
                self._tag_catalog_status_text = self._format_catalog_status()
            self._save_tag_catalog_preferences()
            self._update_tag_diag()
            return (
                _gr_component_update(
                    gr.Textbox,
                    value=self._custom_catalog_path,
                    visible=bool(self._use_tag_catalog and self._catalog_source == "custom"),
                ),
                _gr_component_update(gr.Markdown, value=self._tag_catalog_status_text),
            )

        def _ui_reload_catalog():
            if self._use_tag_catalog:
                ok, message = self._load_tag_catalog()
                if not ok:
                    self._catalog = NoopCatalog()
                    self._tag_catalog_status_text = message
                else:
                    self._tag_catalog_status_text = self._format_catalog_status()
            else:
                self._tag_catalog_status_text = self._format_catalog_status()
            self._save_tag_catalog_preferences()
            self._update_tag_diag()
            return _gr_component_update(gr.Markdown, value=self._tag_catalog_status_text)

        def _ui_catalog_upload(uploaded):
            guessed_path = self._catalog_path_from_upload(uploaded)
            if guessed_path:
                self._custom_catalog_path = guessed_path
                self._tag_catalog_path = guessed_path
                self._save_tag_catalog_preferences()
                msg = f"Selected custom catalog file: {os.path.basename(guessed_path)}"
            else:
                msg = self._tag_catalog_status_text
            return (
                _gr_component_update(
                    gr.Textbox,
                    value=self._custom_catalog_path,
                    visible=bool(self._use_tag_catalog and self._catalog_source == "custom"),
                ),
                _gr_component_update(gr.Markdown, value=msg),
            )

        def _ui_validate_catalog(path_value, uploaded):
            candidate = (path_value or "").strip() or self._catalog_path_from_upload(uploaded)
            ok, message = self._validate_csv_format(candidate)
            status = f"Validation passed: {message}" if ok else f"Validation failed: {message}"
            return _gr_component_update(gr.Markdown, value=status)

        def _ui_import_custom_catalog(uploaded, path_value):
            ok, message = self._import_custom_catalog(uploaded, path_hint=path_value)
            if not ok:
                return (
                    _gr_component_update(
                        gr.Radio,
                        value=("Custom file" if self._catalog_source == "custom" else "Bundled"),
                    ),
                    _gr_component_update(
                        gr.Group,
                        visible=bool(self._use_tag_catalog and self._catalog_source == "custom"),
                    ),
                    _gr_component_update(
                        gr.Textbox,
                        value=self._custom_catalog_path,
                        visible=bool(self._use_tag_catalog and self._catalog_source == "custom"),
                    ),
                    _gr_component_update(gr.Markdown, value=message),
                )
            self._tag_catalog_status_text = self._format_catalog_status()
            self._update_tag_diag()
            return (
                _gr_component_update(gr.Radio, value="Custom file"),
                _gr_component_update(gr.Group, visible=True),
                _gr_component_update(gr.Textbox, value=self._custom_catalog_path, visible=True),
                _gr_component_update(gr.Markdown, value=self._tag_catalog_status_text),
            )

        # --- event wiring -----------------------------------------------------------

        use_tag_catalog.change(
            fn=_ui_toggle_catalog,
            inputs=[use_tag_catalog],
            outputs=[
                catalog_source,
                custom_catalog_group,
                catalog_path,
                reload_catalog,
                catalog_status,
            ],
            queue=False,
        )
        catalog_source.change(
            fn=_ui_set_catalog_source,
            inputs=[catalog_source],
            outputs=[custom_catalog_group, catalog_path, catalog_status],
            queue=False,
        )
        catalog_path.change(
            fn=_ui_set_catalog_path,
            inputs=[catalog_path],
            outputs=[catalog_path, catalog_status],
            queue=False,
        )
        catalog_upload.upload(
            fn=_ui_catalog_upload,
            inputs=[catalog_upload],
            outputs=[catalog_path, catalog_status],
            queue=False,
        )
        catalog_validate_btn.click(
            fn=_ui_validate_catalog,
            inputs=[catalog_path, catalog_upload],
            outputs=[catalog_status],
            queue=False,
        )
        catalog_import_btn.click(
            fn=_ui_import_custom_catalog,
            inputs=[catalog_upload, catalog_path],
            outputs=[catalog_source, custom_catalog_group, catalog_path, catalog_status],
            queue=False,
        )
        reload_catalog.click(
            fn=_ui_reload_catalog,
            inputs=None,
            outputs=[catalog_status],
            queue=False,
        )

        # --- Platform Diagnostics ---------------------------------------------------

        diagnostics_visible_state = gr.State(False)
        diagnostics_toggle_btn = gr.Button("Show Platform Diagnostics")
        diagnostics_md = gr.Markdown("", visible=False)
        diagnostics_toggle_btn.click(
            fn=self._toggle_platform_diagnostics,
            inputs=[diagnostics_visible_state],
            outputs=[diagnostics_visible_state, diagnostics_md, diagnostics_toggle_btn],
            queue=False,
        )

        return use_tag_catalog, catalog_path

    def _build_lora_ui_section(self):
        """LoRAnado controls, auto-detect, detected LoRAs, and blacklist.

        Performs the initial LoRA scan, creates all LoRAnado widgets inside
        ``InputAccordion``, and wires up the change/click events. Returns the
        components that must appear in the script-args component list.
        """
        initial_lora_scan = self._scan_loranado_candidates("")
        initial_lora_choices = (
            initial_lora_scan.get("detected_names") or initial_lora_scan.get("all_names") or []
        )
        initial_lora_status = initial_lora_scan.get("message", "No LoRAs found.")
        if initial_lora_scan.get("all_names"):
            if initial_lora_scan.get("detected_names"):
                initial_lora_status = (
                    f"Detected {len(initial_lora_scan['detected_names'])} PonyXL-compatible LoRAs."
                )
            else:
                initial_lora_status = f"No PonyXL markers detected; using all {len(initial_lora_scan['all_names'])} LoRAs."

        with InputAccordion(
            False, label="LoRAnado", elem_id=self.elem_id("lo_enable")
        ) as lora_enabled:
            with gr.Box():
                lora_lock_prev = gr.Checkbox(label="Lock previous LoRAs", value=False)
                lora_folder = gr.Textbox(
                    lines=1, label="LoRAs Subfolder", placeholder="e.g., 'Characters' or empty"
                )
                lora_amount = gr.Slider(
                    value=1, label="LoRAs Amount", minimum=1, maximum=10, step=1
                )
            with gr.Box():
                lora_min = gr.Slider(
                    value=0.6, label="Min LoRAs Weight", minimum=-1.0, maximum=1.5, step=0.1
                )
                lora_max = gr.Slider(
                    value=1.0, label="Max LoRAs Weight", minimum=-1.0, maximum=1.5, step=0.1
                )
                lora_custom_weights = gr.Textbox(
                    lines=1, label="Custom Weights (optional)", placeholder="e.g., 0.8, 0.5, 1.0"
                )
            with gr.Box():
                lora_auto_detect_pony = gr.Checkbox(
                    label="Auto-detect PonyXL-compatible LoRAs",
                    value=True,
                    info="Scans LoRA filenames and safetensors metadata for PonyXL markers.",
                )
                with gr.Row():
                    lora_scan_btn = gr.Button("Scan LoRAs")
                    lora_select_all_btn = gr.Button("Select All Compatible")
                lora_detected_loras = gr.Dropdown(
                    choices=initial_lora_choices,
                    value=initial_lora_choices,
                    multiselect=True,
                    label="Detected LoRAs (toggle enabled)",
                    info="Only selected entries are eligible for LoRAnado when auto-detect is enabled.",
                )
                lora_blacklist = gr.Dropdown(
                    choices=initial_lora_choices,
                    value=[],
                    multiselect=True,
                    label="LoRAnado blacklist",
                    info="Blacklisted LoRAs are excluded from random selection.",
                )
                lora_detect_status = gr.Markdown(initial_lora_status)

        # --- LoRA event wiring ----------------------------------------------------

        lora_folder.change(
            fn=self._ui_refresh_loranado_controls,
            inputs=[lora_folder, lora_auto_detect_pony, lora_detected_loras, lora_blacklist],
            outputs=[lora_detected_loras, lora_blacklist, lora_detect_status],
            queue=False,
        )
        lora_auto_detect_pony.change(
            fn=self._ui_refresh_loranado_controls,
            inputs=[lora_folder, lora_auto_detect_pony, lora_detected_loras, lora_blacklist],
            outputs=[lora_detected_loras, lora_blacklist, lora_detect_status],
            queue=False,
        )
        lora_scan_btn.click(
            fn=self._ui_refresh_loranado_controls,
            inputs=[lora_folder, lora_auto_detect_pony, lora_detected_loras, lora_blacklist],
            outputs=[lora_detected_loras, lora_blacklist, lora_detect_status],
            queue=False,
        )
        lora_select_all_btn.click(
            fn=self._ui_select_all_loranado,
            inputs=[lora_folder, lora_auto_detect_pony, lora_blacklist],
            outputs=[lora_detected_loras, lora_detect_status],
            queue=False,
        )

        return (
            lora_enabled,
            lora_folder,
            lora_amount,
            lora_min,
            lora_max,
            lora_custom_weights,
            lora_lock_prev,
            lora_auto_detect_pony,
            lora_detected_loras,
            lora_blacklist,
        )

    def _build_filter_ui_section(self):
        """Removal toggle checkboxes, presets, and Quick Strip.

        Creates the Quick Presets buttons and all removal-filter checkboxes
        (Text & Metadata, Characters & Series, Clothing, Furry & Headwear,
        Girl Suffix, Colors & Traits, Subject Constraints). Wires up the
        preset click events. Must be called inside ``gr.Accordion("Removal Filters")``
        after the catalog section. Returns the 11 filter components that
        appear in the script-args component list.
        """
        gr.Markdown("**Quick Presets**: apply common filter combinations with one click.")

        with gr.Row():
            preset_strip_series = gr.Button("Strip Series/Character")
            preset_remove_text = gr.Button("Remove Text-like Tags")
            preset_preserve_colors = gr.Button("Preserve Base Colors")
            preset_quick_strip = gr.Button("Quick Strip")
        with gr.Group():
            gr.Markdown("**Text & Metadata**")
            remove_bad_tags = gr.Checkbox(
                label="Remove common 'bad' tags",
                value=True,
                info="Cull frequent watermark, commentary, and UI text tags from prompts.",
            )
            remove_text_tags = gr.Checkbox(
                label="Remove tag/text/commentary metadata",
                value=True,
                info="Strip speech bubbles, watermark text, and similar metadata from fetched prompts.",
            )
        with gr.Group():
            gr.Markdown("**Characters & Series**")
            remove_artist_tags = gr.Checkbox(
                label="Remove artist tags",
                value=False,
                info="Drop artist credits drawn from the source post.",
            )
            remove_character_tags = gr.Checkbox(
                label="Remove character tags",
                value=False,
                info="Filter character/franchise tags sourced from metadata.",
            )
            remove_series_tags = gr.Checkbox(
                label="Remove series / franchise tags",
                value=False,
                info="Ignore franchise/game/anime tags to keep prompts generic.",
            )
        with gr.Group():
            gr.Markdown("**Clothing & Accessories**")
            remove_clothing_tags = gr.Checkbox(
                label="Remove clothing tags",
                value=False,
                info="Omit apparel/accessory tags introduced by the booru.",
            )
        with gr.Group():
            gr.Markdown("**Furry & Headwear**")
            remove_furry_tags = gr.Checkbox(
                label="Filter furry/pokemon tags",
                value=False,
                info="Remove furry, pokemon, and animal trait tags.",
            )
            remove_headwear_tags = gr.Checkbox(
                label="Filter headwear / halo tags",
                value=False,
                info="Strip hats, halos, and similar head accessories.",
            )
        with gr.Group():
            gr.Markdown("**Girl Suffix**")
            remove_girl_suffix_tags = gr.Checkbox(
                label="Filter _girl suffix tags",
                value=False,
                info="Remove demon_girl, cat_girl, angel_girl and similar *_girl tags (keeps 1girl, 2girls, etc.).",
            )
        with gr.Group():

            gr.Markdown("**Colors & Traits**")
            preserve_hair_eye_colors = gr.Checkbox(
                label="Preserve base hair & eye colors",
                value=False,
                info="Keep your prompt's hair/eye colors while removing conflicting imports.",
            )
        with gr.Group():
            gr.Markdown("**Subject Constraints**")
            restrict_subject_tags = gr.Checkbox(
                label="Keep only subject counts",
                value=False,
                info="Maintain your subject count (e.g., solo/1girl) by removing mismatched tags.",
            )

        # --- preset wiring ---------------------------------------------------------

        preset_strip_series.click(
            fn=lambda: (
                _gr_component_update(gr.Checkbox, value=True),
                _gr_component_update(gr.Checkbox, value=True),
                _gr_component_update(gr.Checkbox, value=True),
            ),
            inputs=[],
            outputs=[remove_series_tags, remove_character_tags, remove_artist_tags],
            queue=False,
        )
        preset_remove_text.click(
            fn=lambda: (
                _gr_component_update(gr.Checkbox, value=True),
                _gr_component_update(gr.Checkbox, value=True),
            ),
            inputs=[],
            outputs=[remove_text_tags, remove_bad_tags],
            queue=False,
        )
        preset_preserve_colors.click(
            fn=lambda: _gr_component_update(gr.Checkbox, value=True),
            inputs=[],
            outputs=[preserve_hair_eye_colors],
            queue=False,
        )
        preset_quick_strip.click(
            fn=lambda: tuple(_gr_component_update(gr.Checkbox, value=True) for _ in range(11)),
            inputs=[],
            outputs=[
                remove_bad_tags,
                remove_text_tags,
                remove_artist_tags,
                remove_character_tags,
                remove_series_tags,
                remove_clothing_tags,
                remove_furry_tags,
                remove_headwear_tags,
                remove_girl_suffix_tags,
                preserve_hair_eye_colors,
                restrict_subject_tags,
            ],
            queue=False,
        )

        return (
            remove_bad_tags,
            remove_text_tags,
            remove_artist_tags,
            remove_character_tags,
            remove_series_tags,
            remove_clothing_tags,
            remove_furry_tags,
            remove_headwear_tags,
            remove_girl_suffix_tags,
            preserve_hair_eye_colors,
            restrict_subject_tags,
        )

    def _build_personal_lists_ui_section(self):
        """Search/remove file management with refresh buttons (File Tags accordion).

        Creates the File Tags accordion containing search-file and remove-file
        dropdowns with Refresh buttons. Wires the refresh click events. Returns
        the six components needed in the script-args list.
        """
        with gr.Accordion("File Tags", open=False):
            use_search_txt = gr.Checkbox(label="Add line from Search File", value=False)
            choose_search_txt = gr.Dropdown(
                self.get_files(USER_SEARCH_DIR),
                label="Choose Search File",
                value="",
                info=f"in '{USER_SEARCH_DIR}'",
            )
            search_refresh_btn = gr.Button("Refresh")
            use_remove_txt = gr.Checkbox(label="Add tags from Remove File", value=False)
            choose_remove_txt = gr.Dropdown(
                self.get_files(USER_REMOVE_DIR),
                label="Choose Remove File",
                value="",
                info=f"in '{USER_REMOVE_DIR}'",
            )
            remove_refresh_btn = gr.Button("Refresh")

        search_refresh_btn.click(fn=self.refresh_ser, inputs=[], outputs=[choose_search_txt])
        remove_refresh_btn.click(fn=self.refresh_rem, inputs=[], outputs=[choose_remove_txt])

        return (
            use_search_txt,
            use_remove_txt,
            choose_search_txt,
            choose_remove_txt,
            search_refresh_btn,
            remove_refresh_btn,
        )

    def ui(self, is_img2img):
        with InputAccordion(False, label="RanbooruX", elem_id=self.elem_id("ra_enable")) as enabled:
            booru_list = [
                "danbooru",
                "gelbooru",
                "gelbooru-compatible",
                "xbooru",
                "rule34",
                "safebooru",
                "konachan",
                "yande.re",
                "aibooru",
                "e621",
            ]
            booru = gr.Dropdown(booru_list, label="Booru", value="danbooru")
            with gr.Group(visible=False) as gelbooru_credentials_group:
                gelbooru_api_key = gr.Textbox(
                    label="Gelbooru API Key",
                    type="password",
                    placeholder="Enter your Gelbooru API key",
                )
                gelbooru_user_id = gr.Textbox(
                    label="Gelbooru User ID", placeholder="Enter your Gelbooru user ID"
                )
                gelbooru_save_button = gr.Button("Save Credentials to Disk", variant="primary")
            gelbooru_saved_message = gr.Markdown("", visible=False)
            gelbooru_clear_button = gr.Button("Clear Saved Credentials", visible=False)
            with gr.Group(visible=False) as gelbooru_compat_group:
                gelbooru_compat_base_url = gr.Textbox(
                    label="Gelbooru-compatible Base URL",
                    placeholder="https://realbooru.com",
                    value=self._gelbooru_compat_base_url,
                )
            max_pages = gr.Slider(
                label="Max Pages (tag search)", minimum=1, maximum=100, value=10, step=1
            )
            gr.Markdown("""## Post""")
            post_id = gr.Textbox(lines=1, label="Post ID (Overrides tags/pages)")
            gr.Markdown("""## Tags""")
            tags = gr.Textbox(lines=1, label="Tags to Search (Pre)")
            remove_tags = gr.Textbox(lines=1, label="Tags to Remove (Post)")
            mature_rating = gr.Radio(
                list(RATINGS.get("gelbooru", RATING_TYPES["none"])),
                label="Mature Rating",
                value="All",
            )
            with gr.Accordion("Removal Filters", open=False):
                with gr.Group():
                    use_tag_catalog, catalog_path = self._build_catalog_ui_section()

                (
                    remove_bad_tags,
                    remove_text_tags,
                    remove_artist_tags,
                    remove_character_tags,
                    remove_series_tags,
                    remove_clothing_tags,
                    remove_furry_tags,
                    remove_headwear_tags,
                    remove_girl_suffix_tags,
                    preserve_hair_eye_colors,
                    restrict_subject_tags,
                ) = self._build_filter_ui_section()
            personal_choices = self._read_list_file(PERSONAL_REMOVE_FILE)
            favorite_choices = self._read_list_file(FAVORITES_FILE)
            with gr.Accordion("Personal Lists", open=False):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("**Personal Removal List**")
                        personal_remove_dropdown = gr.Dropdown(
                            choices=personal_choices,
                            value=personal_choices,
                            multiselect=True,
                            label="Removal Tags",
                            allow_custom_value=False,
                        )
                        personal_remove_input = gr.Textbox(
                            label="Add tags", placeholder="comma or newline separated"
                        )
                        with gr.Row():
                            personal_add_btn = gr.Button("Add", variant="primary")
                            personal_remove_btn = gr.Button("Remove Selected")
                            personal_dedupe_btn = gr.Button("De-duplicate")
                        with gr.Row():
                            personal_import_file = gr.File(
                                label="Import CSV/TXT", file_types=[".txt", ".csv"], visible=True
                            )
                            personal_export_btn = gr.DownloadButton("Export")
                    with gr.Column():
                        gr.Markdown("**Favorites List**")
                        favorites_dropdown = gr.Dropdown(
                            choices=favorite_choices,
                            value=favorite_choices,
                            multiselect=True,
                            label="Favorite Tags",
                            allow_custom_value=False,
                        )
                        favorites_input = gr.Textbox(
                            label="Add favorites", placeholder="comma or newline separated"
                        )
                        with gr.Row():
                            favorites_add_btn = gr.Button("Add", variant="primary")
                            favorites_remove_btn = gr.Button("Remove Selected")
                            favorites_dedupe_btn = gr.Button("De-duplicate")
                        with gr.Row():
                            favorites_import_file = gr.File(
                                label="Import CSV/TXT", file_types=[".txt", ".csv"], visible=True
                            )
                            favorites_export_btn = gr.DownloadButton("Export")
            shuffle_tags = gr.Checkbox(label="Shuffle tags", value=True)
            change_dash = gr.Checkbox(label='Convert "_" to spaces', value=False)
            anima_auto_detect = gr.Checkbox(
                label="Auto-detect Anima model",
                value=True,
                info="Automatically enable space-separated tags when an Anima model is loaded",
            )
            anima_tune_img2img = gr.Checkbox(
                label="Auto-tune Img2Img parameters for Anima",
                value=True,
                info="Automatically optimize steps, CFG scale, and denoising for Anima flow-matching",
            )
            same_prompt = gr.Checkbox(label="Use same prompt for batch", value=False)
            fringe_benefits = gr.Checkbox(
                label="Gelbooru: Fringe Benefits", value=True, visible=False
            )
            limit_tags = gr.Slider(
                value=1.0, label="Limit tags by %", minimum=0.05, maximum=1.0, step=0.05
            )
            max_tags = gr.Slider(
                value=0, label="Max tags (0=disabled)", minimum=0, maximum=300, step=1
            )
            change_background = gr.Radio(
                ["Don't Change", "Add Detail", "Force Simple", "Force Transparent/White"],
                label="Change Background",
                value="Don't Change",
            )
            change_color = gr.Radio(
                ["Don't Change", "Force Color", "Force Monochrome"],
                label="Change Color",
                value="Don't Change",
            )
            sorting_order = gr.Radio(
                ["Random", "Score Descending", "Score Ascending"],
                label="Sort Order (tag search)",
                value="Random",
            )
            booru.change(get_available_ratings, booru, mature_rating)
            booru.change(show_fringe_benefits, booru, fringe_benefits)
            booru.change(
                self._update_gelbooru_ui_visibility,
                inputs=[booru],
                outputs=[
                    gelbooru_credentials_group,
                    gelbooru_saved_message,
                    gelbooru_clear_button,
                    gelbooru_api_key,
                    gelbooru_user_id,
                ],
                queue=False,
            )
            booru.change(
                self._update_gelbooru_compat_visibility,
                inputs=[booru],
                outputs=[gelbooru_compat_group, gelbooru_compat_base_url],
                queue=False,
            )
            gelbooru_compat_base_url.change(
                fn=self._ui_set_gelbooru_compat_base_url,
                inputs=[gelbooru_compat_base_url],
                outputs=[gelbooru_compat_base_url],
                queue=False,
            )
            gelbooru_save_button.click(
                fn=self._ui_save_gelbooru_credentials,
                inputs=[gelbooru_api_key, gelbooru_user_id],
                outputs=[
                    gelbooru_saved_message,
                    gelbooru_credentials_group,
                    gelbooru_clear_button,
                    gelbooru_api_key,
                    gelbooru_user_id,
                ],
                queue=False,
            )
            gelbooru_clear_button.click(
                fn=self._ui_clear_gelbooru_credentials,
                inputs=[],
                outputs=[
                    gelbooru_saved_message,
                    gelbooru_credentials_group,
                    gelbooru_clear_button,
                    gelbooru_api_key,
                    gelbooru_user_id,
                ],
                queue=False,
            )

            gr.Markdown("""\n---\n""")
            with gr.Group():
                with gr.Accordion("Img2Img / ControlNet", open=False):
                    use_img2img = gr.Checkbox(label="Use Image for Img2Img", value=False)
                    use_ip = gr.Checkbox(label="Use Image for ControlNet (Unit 0)", value=False)
                    denoising = gr.Slider(
                        value=0.75,
                        label="Img2Img Denoising / CN Weight",
                        minimum=0.0,
                        maximum=1.0,
                        step=0.05,
                    )
                    use_last_img = gr.Checkbox(label="Use same image for batch", value=False)
                    crop_center = gr.Checkbox(label="Crop image to fit target", value=False)
                    enable_adetailer_support = gr.Checkbox(
                        label="Enable RanbooruX ADetailer support",
                        value=False,
                        info="Run RanbooruX's manual ADetailer integration after img2img when enabled.",
                    )
                    reuse_cached_posts = gr.Checkbox(
                        label="Reuse cached booru posts",
                        value=False,
                        info="Leave disabled to fetch fresh images every generation. Enable when you want RanbooruX to reuse the previously cached posts.",
                    )
            with gr.Group():
                (
                    use_search_txt,
                    use_remove_txt,
                    choose_search_txt,
                    choose_remove_txt,
                    search_refresh_btn,
                    remove_refresh_btn,
                ) = self._build_personal_lists_ui_section()
            with gr.Group():
                with gr.Accordion("Extra Prompt Modes", open=False):
                    with gr.Box():
                        mix_prompt = gr.Checkbox(label="Mix tags from multiple posts", value=False)
                        mix_amount = gr.Slider(
                            value=2, label="Posts to mix", minimum=2, maximum=10, step=1
                        )
                    with gr.Box():
                        chaos_mode = gr.Radio(
                            ["None", "Shuffle All", "Shuffle Negative"],
                            label="Tag Shuffling (Chaos)",
                            value="None",
                        )
                        chaos_amount = gr.Slider(
                            value=0.5, label="Chaos Amount %", minimum=0.1, maximum=1.0, step=0.05
                        )
                    with gr.Box():
                        use_same_seed = gr.Checkbox(label="Use same seed for batch", value=False)
                        use_cache = gr.Checkbox(label="Cache Booru API requests", value=True)
                        log_prompt_sources = gr.Checkbox(
                            label="Log image sources/prompts to txt",
                            value=False,
                            info="When enabled, RanbooruX appends a log entry mapping seeds and prompts to the source posts.",
                        )
        (
            lora_enabled,
            lora_folder,
            lora_amount,
            lora_min,
            lora_max,
            lora_custom_weights,
            lora_lock_prev,
            lora_auto_detect_pony,
            lora_detected_loras,
            lora_blacklist,
        ) = self._build_lora_ui_section()
        personal_add_btn.click(
            fn=self._ui_add_personal_tags,
            inputs=[personal_remove_input, personal_remove_dropdown],
            outputs=[personal_remove_dropdown, personal_remove_input],
            queue=False,
        )
        personal_remove_btn.click(
            fn=self._ui_remove_personal_tags,
            inputs=[personal_remove_dropdown],
            outputs=[personal_remove_dropdown],
            queue=False,
        )
        personal_dedupe_btn.click(
            fn=self._ui_dedupe_personal_list,
            inputs=[],
            outputs=[personal_remove_dropdown],
            queue=False,
        )
        personal_import_file.upload(
            fn=self._ui_import_personal_list,
            inputs=[personal_import_file],
            outputs=[personal_remove_dropdown, personal_import_file],
            queue=False,
        )
        personal_export_btn.click(
            fn=self._ui_export_personal_list, inputs=[], outputs=None, queue=False
        )

        favorites_add_btn.click(
            fn=self._ui_add_favorite_tags,
            inputs=[favorites_input, favorites_dropdown],
            outputs=[favorites_dropdown, favorites_input],
            queue=False,
        )
        favorites_remove_btn.click(
            fn=self._ui_remove_favorite_tags,
            inputs=[favorites_dropdown],
            outputs=[favorites_dropdown],
            queue=False,
        )
        favorites_dedupe_btn.click(
            fn=self._ui_dedupe_favorite_list, inputs=[], outputs=[favorites_dropdown], queue=False
        )
        favorites_import_file.upload(
            fn=self._ui_import_favorite_list,
            inputs=[favorites_import_file],
            outputs=[favorites_dropdown, favorites_import_file],
            queue=False,
        )
        favorites_export_btn.click(
            fn=self._ui_export_favorite_list, inputs=[], outputs=None, queue=False
        )

        components = [
            enabled,
            tags,
            booru,
            gelbooru_api_key,
            gelbooru_user_id,
            gelbooru_compat_base_url,
            remove_bad_tags,
            max_pages,
            change_dash,
            same_prompt,
            fringe_benefits,
            remove_tags,
            use_img2img,
            denoising,
            use_last_img,
            change_background,
            change_color,
            shuffle_tags,
            post_id,
            mix_prompt,
            mix_amount,
            chaos_mode,
            chaos_amount,
            limit_tags,
            max_tags,
            sorting_order,
            mature_rating,
            lora_folder,
            lora_amount,
            lora_min,
            lora_max,
            lora_enabled,
            lora_custom_weights,
            lora_lock_prev,
            use_ip,
            use_search_txt,
            use_remove_txt,
            choose_search_txt,
            choose_remove_txt,
            search_refresh_btn,
            remove_refresh_btn,
            crop_center,
            enable_adetailer_support,
            use_same_seed,
            reuse_cached_posts,
            use_cache,
            log_prompt_sources,
            remove_artist_tags,
            remove_character_tags,
            remove_clothing_tags,
            remove_text_tags,
            restrict_subject_tags,
            remove_furry_tags,
            remove_headwear_tags,
            remove_girl_suffix_tags,
            preserve_hair_eye_colors,
            remove_series_tags,
            use_tag_catalog,
            catalog_path,
            lora_auto_detect_pony,
            lora_detected_loras,
            lora_blacklist,
            anima_auto_detect,
            anima_tune_img2img,
        ]
        return rb_run_options.RunComponents.from_sequence(components).script_args()

    def _normalize_lora_name(self, value: object) -> str:
        return rb_loranado.normalize_lora_name(value)

    def _get_lora_base_dir(self) -> str:
        cmd_opts = getattr(shared, "cmd_opts", None)
        base_dir = getattr(cmd_opts, "lora_dir", "") if cmd_opts is not None else ""
        if not isinstance(base_dir, str):
            base_dir = str(base_dir) if base_dir is not None else ""
        return base_dir

    def _resolve_lora_target_folder(self, lora_folder: Optional[str]) -> str:
        lora_dir = self._get_lora_base_dir()
        folder = (lora_folder or "").strip()
        return os.path.join(lora_dir, folder) if folder else lora_dir

    def _read_safetensors_metadata(self, file_path: str) -> Dict[str, object]:
        try:
            with open(file_path, "rb") as handle:
                header_len_raw = handle.read(8)
                if len(header_len_raw) != 8:
                    return {}
                header_len = int.from_bytes(header_len_raw, "little", signed=False)
                if header_len <= 2 or header_len > self._LORANADO_MAX_HEADER_BYTES:
                    return {}
                header_blob = handle.read(header_len)
                if len(header_blob) != header_len:
                    return {}
            header_data = json.loads(header_blob.decode("utf-8", errors="ignore"))
            metadata = header_data.get("__metadata__", {}) if isinstance(header_data, dict) else {}
            return metadata if isinstance(metadata, dict) else {}
        except Exception:
            return {}

    def _matches_ponyxl_marker(self, text: object) -> bool:
        if text is None:
            return False
        haystack = str(text).strip().lower()
        if not haystack:
            return False
        return any(pattern.search(haystack) for pattern in _LORANADO_PONY_PATTERNS)

    def _is_relevant_pony_metadata_key(self, key: object) -> bool:
        if key is None:
            return False
        normalized = str(key).strip().lower()
        if not normalized:
            return False
        return any(hint in normalized for hint in _LORANADO_PONY_METADATA_KEY_HINTS)

    def _iter_metadata_values(self, value: object) -> Iterable[str]:
        pending: List[object] = [value]
        while pending:
            current = pending.pop()
            if current is None:
                continue
            if isinstance(current, (str, int, float, bool)):
                normalized = str(current).strip().lower()
                if normalized:
                    yield normalized
                continue
            if isinstance(current, dict):
                pending.extend(current.values())
                continue
            if isinstance(current, (list, tuple, set)):
                pending.extend(current)

    def _is_ponyxl_lora(self, file_name: str, metadata: Dict[str, object]) -> bool:
        stem = os.path.splitext(file_name or "")[0]
        if self._matches_ponyxl_marker(stem):
            return True
        if not isinstance(metadata, dict):
            return False

        for key, value in metadata.items():
            if not self._is_relevant_pony_metadata_key(key):
                continue
            for text in self._iter_metadata_values(value):
                if self._matches_ponyxl_marker(text):
                    return True
        return False

    def _scan_loranado_candidates(self, lora_folder: Optional[str]) -> Dict[str, object]:
        target_folder = self._resolve_lora_target_folder(lora_folder)
        if not target_folder:
            return {
                "target_folder": "",
                "all_files": [],
                "all_names": [],
                "detected_files": [],
                "detected_names": [],
                "message": "LoRA directory is not configured.",
            }
        if not os.path.isdir(target_folder):
            return {
                "target_folder": target_folder,
                "all_files": [],
                "all_names": [],
                "detected_files": [],
                "detected_names": [],
                "message": f"LoRA folder not found: {target_folder}",
            }
        try:
            all_files = sorted(
                file_name
                for file_name in os.listdir(target_folder)
                if file_name.lower().endswith(".safetensors")
            )
        except Exception as exc:
            return {
                "target_folder": target_folder,
                "all_files": [],
                "all_names": [],
                "detected_files": [],
                "detected_names": [],
                "message": f"Could not scan LoRA folder: {exc}",
            }

        if not all_files:
            return {
                "target_folder": target_folder,
                "all_files": [],
                "all_names": [],
                "detected_files": [],
                "detected_names": [],
                "message": f"No .safetensors files found in {target_folder}",
            }

        snapshot: List[Tuple[str, float, int]] = []
        for file_name in all_files:
            full_path = os.path.join(target_folder, file_name)
            try:
                stat = os.stat(full_path)
                snapshot.append((file_name, stat.st_mtime, stat.st_size))
            except OSError:
                snapshot.append((file_name, 0.0, 0))
        snapshot_key = tuple(snapshot)

        cached = self._loranado_scan_cache.get(target_folder)
        if cached and cached.get("snapshot") == snapshot_key:
            result = cached.get("result")
            if isinstance(result, dict):
                return dict(result)

        detected_files: List[str] = []
        for file_name in all_files:
            metadata = self._read_safetensors_metadata(os.path.join(target_folder, file_name))
            if self._is_ponyxl_lora(file_name, metadata):
                detected_files.append(file_name)

        result = {
            "target_folder": target_folder,
            "all_files": all_files,
            "all_names": [os.path.splitext(file_name)[0] for file_name in all_files],
            "detected_files": detected_files,
            "detected_names": [os.path.splitext(file_name)[0] for file_name in detected_files],
            "message": f"Scanned {len(all_files)} LoRA(s) in {target_folder}",
        }
        self._loranado_scan_cache[target_folder] = {
            "snapshot": snapshot_key,
            "result": dict(result),
        }
        return result

    def _prepare_loranado_choice_state(
        self,
        lora_folder: Optional[str],
        auto_detect_pony: bool,
        enabled_loras: object,
        blacklist_loras: object,
    ) -> Tuple[List[str], List[str], str]:
        scan = self._scan_loranado_candidates(lora_folder)
        all_names = list(scan.get("all_names") or [])
        detected_names = list(scan.get("detected_names") or [])
        if auto_detect_pony:
            choice_names = detected_names or all_names
            if detected_names:
                status = f"Detected {len(detected_names)} PonyXL-compatible LoRAs in `{scan.get('target_folder', '')}`."
            elif all_names:
                status = (
                    f"No PonyXL markers detected in `{scan.get('target_folder', '')}`. "
                    f"Falling back to all {len(all_names)} LoRAs."
                )
            else:
                status = scan.get("message") or "No LoRAs found."
        else:
            choice_names = all_names
            if all_names:
                status = f"Auto-detect disabled. {len(all_names)} LoRAs available in `{scan.get('target_folder', '')}`."
            else:
                status = scan.get("message") or "No LoRAs found."

        chosen = [
            name for name in _coerce_multiselect_values(enabled_loras) if name in choice_names
        ]
        blacklisted = [
            name for name in _coerce_multiselect_values(blacklist_loras) if name in choice_names
        ]
        blacklisted_set = set(blacklisted)

        if not chosen and choice_names:
            chosen = list(choice_names)
        if blacklisted_set:
            chosen = [name for name in chosen if name not in blacklisted_set]
        if not chosen and choice_names:
            chosen = [name for name in choice_names if name not in blacklisted_set]

        if choice_names:
            status = f"{status}\nEnabled: {len(chosen)} | Blacklisted: {len(blacklisted)}"
        return choice_names, chosen, status

    def _ui_refresh_loranado_controls(
        self,
        lora_folder: Optional[str],
        auto_detect_pony: bool,
        enabled_loras: object,
        blacklist_loras: object,
    ):
        choices, enabled_values, status = self._prepare_loranado_choice_state(
            lora_folder=lora_folder,
            auto_detect_pony=bool(auto_detect_pony),
            enabled_loras=enabled_loras,
            blacklist_loras=blacklist_loras,
        )
        blacklisted = [
            name for name in _coerce_multiselect_values(blacklist_loras) if name in choices
        ]
        return (
            _gr_component_update(gr.Dropdown, choices=choices, value=enabled_values),
            _gr_component_update(gr.Dropdown, choices=choices, value=blacklisted),
            _gr_component_update(gr.Markdown, value=status),
        )

    def _ui_select_all_loranado(
        self,
        lora_folder: Optional[str],
        auto_detect_pony: bool,
        blacklist_loras: object,
    ):
        choices, enabled_values, status = self._prepare_loranado_choice_state(
            lora_folder=lora_folder,
            auto_detect_pony=bool(auto_detect_pony),
            enabled_loras=[],
            blacklist_loras=blacklist_loras,
        )
        return (
            _gr_component_update(gr.Dropdown, choices=choices, value=enabled_values),
            _gr_component_update(gr.Markdown, value=status),
        )

    def check_orientation(self, img):
        if img is None:
            print("[R Orientation] No image provided, defaulting to 1024x1024")
            return [1024, 1024]
        x, y = img.size
        aspect_ratio = x / y

        print(f"[R Orientation] Original: {x}x{y}, aspect_ratio: {aspect_ratio:.3f}")

        # Calculate dimensions that maintain aspect ratio while staying within reasonable bounds
        # Target around 1024 pixels for the longer dimension, minimum 512 for shorter
        if aspect_ratio > 1.33:  # Wide image
            # Landscape - width is longer
            target_width = 1152
            target_height = int(target_width / aspect_ratio)
            # Ensure minimum height
            if target_height < 512:
                target_height = 512
                target_width = int(target_height * aspect_ratio)

            # Round to multiples of 8 for better compatibility
            target_width = (target_width // 8) * 8
            target_height = (target_height // 8) * 8

            result = [target_width, target_height]
            print(f"[R Orientation] Wide image -> {result[0]}x{result[1]} (rounded to 8px)")
            return result
        elif aspect_ratio < 0.75:  # Tall image
            # Portrait - height is longer
            target_height = 1152
            target_width = int(target_height * aspect_ratio)
            # Ensure minimum width
            if target_width < 512:
                target_width = 512
                target_height = int(target_width / aspect_ratio)

            # Round to multiples of 8 for better compatibility
            target_width = (target_width // 8) * 8
            target_height = (target_height // 8) * 8

            result = [target_width, target_height]
            print(f"[R Orientation] Tall image -> {result[0]}x{result[1]} (rounded to 8px)")
            return result
        else:
            # Square-ish - use balanced dimensions based on original size
            # Scale to reasonable size while maintaining square aspect
            max_dim = max(x, y)
            if max_dim > 1024:
                result = [1024, 1024]
            elif max_dim < 512:
                result = [512, 512]
            else:
                # Use original dimensions if they're reasonable, rounded to 8px
                max_dim = (max_dim // 8) * 8
                result = [max_dim, max_dim]
            print(f"[R Orientation] Square-ish image -> {result[0]}x{result[1]} (rounded to 8px)")
            return result

    def _setup_cache(self, use_cache):
        old_client = getattr(self, "_http_client", None)
        if old_client is not None:
            try:
                old_client.close()
            except Exception as exc:
                print(f"[R] Warn: Failed to close previous booru session: {exc}")
        self._http_client = rb_http_client.BooruSession(use_cache=bool(use_cache))
        print(f"[R] Booru request cache {'enabled' if use_cache else 'disabled'} for this run.")
        return False

    def _prepare_tags(
        self,
        ui_tags,
        ui_remove_tags,
        use_remove_file,
        remove_file,
        change_background,
        change_color,
        use_search_file,
        search_file,
        remove_default_bad,
    ):
        bad_tags = set()
        if remove_default_bad:
            bad_tags.update(
                [
                    "mixed-language_text",
                    "watermark",
                    "text",
                    "english_text",
                    "speech_bubble",
                    "signature",
                    "artist_name",
                    "censored",
                    "bar_censor",
                    "translation",
                    "twitter_username",
                    "twitter_logo",
                    "patreon_username",
                    "commentary_request",
                    "tagme",
                    "commentary",
                    "character_name",
                    "mosaic_censoring",
                    "instagram_username",
                    "text_focus",
                    "english_commentary",
                    "comic",
                    "translation_request",
                    "fake_text",
                    "translated",
                    "paid_reward_available",
                    "thought_bubble",
                    "multiple_views",
                    "silent_comic",
                    "out-of-frame_censoring",
                    "symbol-only_commentary",
                    "3koma",
                    "2koma",
                    "character_watermark",
                    "spoken_question_mark",
                    "japanese_text",
                    "spanish_text",
                    "language_text",
                    "fanbox_username",
                    "commission",
                    "original",
                    "ai_generated",
                    "stable_diffusion",
                    "tagme_(artist)",
                    "text_bubble",
                    "qr_code",
                    "chinese_commentary",
                    "korean_text",
                    "partial_commentary",
                    "chinese_text",
                    "copyright_request",
                    "heart_censor",
                    "censored_nipples",
                    "page_number",
                    "scan",
                    "fake_magazine_cover",
                    "korean_commentary",
                ]
            )
        if ui_remove_tags:
            bad_tags.update([t.strip() for t in ui_remove_tags.split(",") if t.strip()])
        if use_remove_file and remove_file:
            try:
                filepath = os.path.join(USER_REMOVE_DIR, remove_file)
                print(f"[R] Reading remove tags: {filepath}")
                with open(filepath, "r", encoding="utf-8") as f:
                    read_tags = [t.strip() for t in f.read().split(",") if t.strip()]
                    print(f"[R] Tags read: {read_tags}")
                    bad_tags.update(read_tags)
            except Exception as e:
                print(f"[R] Warn: Read remove file failed {remove_file}: {e}")
        initial_additions = []
        bg_remove = set()
        color_remove = set()
        if change_background == "Add Detail":
            initial_additions.append(random.choice(["outdoors", "indoors", "detailed_background"]))
            bg_remove.update(
                COLORED_BG + ["simple_background", "plain_background", "transparent_background"]
            )
        elif change_background == "Force Simple":
            initial_additions.append(
                random.choice(["simple_background", "plain_background"] + COLORED_BG)
            )
            bg_remove.update(ADD_BG + ["detailed_background"])
        elif change_background == "Force Transparent/White":
            initial_additions.append(
                random.choice(["transparent_background", "white_background", "plain_background"])
            )
            bg_remove.update(ADD_BG + COLORED_BG + ["detailed_background", "simple_background"])
        if change_color == "Force Color":
            color_remove.update(BW_BG + ["limited_palette"])
        elif change_color == "Force Monochrome":
            initial_additions.append(random.choice(BW_BG))
            color_remove.update(["colored_background", "limited_palette"])
        bad_tags.update(bg_remove)
        bad_tags.update(color_remove)
        initial_additions_str = ",".join(initial_additions)
        search_tags = ui_tags
        if use_search_file and search_file:
            try:
                filepath = os.path.join(USER_SEARCH_DIR, search_file)
                print(f"[R] Reading search tags: {filepath}")
                with open(filepath, "r", encoding="utf-8") as f:
                    search_lines = [line.strip() for line in f.readlines() if line.strip()]
                    if search_lines:
                        selected_file_tags = random.choice(search_lines)
                        search_tags = (
                            f"{search_tags},{selected_file_tags}"
                            if search_tags
                            else selected_file_tags
                        )
                        print(f"[R] Added file tags: {selected_file_tags}")
                    else:
                        print(f"[R] Warn: Search file empty: '{search_file}'")
            except Exception as e:
                print(f"[R] Warn: Read search file failed {search_file}: {e}")
        return search_tags, bad_tags, initial_additions_str

    def _get_booru_api(
        self, booru_name, fringe_benefits, gelbooru_credentials: Optional[Dict[str, str]] = None
    ):
        from ranboorux.boorus.gelbooru import Gelbooru, GelbooruCompatible
        from ranboorux.boorus.simple import (
            AIBooru,
            Danbooru,
            Konachan,
            Rule34,
            Safebooru,
            XBooru,
            Yandere,
            e621,
        )

        booru_name = (booru_name or "").strip().lower()
        if booru_name == "gelbooru-compatible":
            base_url = _sanitize_gelbooru_compat_base_url(
                getattr(self, "_gelbooru_compat_base_url", "")
            )
            if not base_url:
                raise ValueError(
                    "Please enter a Gelbooru-compatible Base URL (e.g., https://realbooru.com)."
                )
            self._gelbooru_compat_base_url = base_url
            api = GelbooruCompatible(base_url)
            api.http = self._http_client
            return api

        booru_apis = {
            "gelbooru": Gelbooru(fringe_benefits, gelbooru_credentials),
            "danbooru": Danbooru(),
            "xbooru": XBooru(),
            "rule34": Rule34(),
            "safebooru": Safebooru(),
            "konachan": Konachan(),
            "yande.re": Yandere(),
            "aibooru": AIBooru(),
            "e621": e621(),
        }
        if booru_name not in booru_apis:
            raise ValueError(f"Booru '{booru_name}' not implemented.")
        api = booru_apis.get(booru_name)
        if api is not None:
            api.http = self._http_client
        return api

    def _fetch_booru_posts(self, api, search_tags, mature_rating, max_pages, post_id):
        add_tags_list = []
        # Don't add search_tags to tags_query when using post_id - causes API confusion
        if search_tags and not post_id:
            add_tags_list.extend([t.strip() for t in search_tags.split(",") if t.strip()])
        booru_name = api.booru_name.lower()
        if (
            mature_rating != "All"
            and booru_name in RATINGS
            and mature_rating in RATINGS[booru_name]
        ):
            rating_tag = RATINGS[booru_name][mature_rating]
            if rating_tag != "All":
                add_tags_list.append(f"rating:{rating_tag}")
        add_tags_list.append("-animated")
        if add_tags_list:
            add_tags_list, _ = self._apply_optional_catalog(
                add_tags_list,
                keep_hair_eye=bool(getattr(self, "_preserve_hair_eye_colors", False)),
                drop_series=bool(getattr(self, "_remove_series_tags", False)),
                drop_characters=bool(getattr(self, "_remove_character_tags", False)),
                drop_textual=bool(getattr(self, "_remove_text_tags", False)),
            )
        tags_query = f"&tags={'+'.join(add_tags_list)}" if add_tags_list else ""
        print(f"[R] Query Tags: '{tags_query}' (post_id={post_id})")
        try:
            all_posts = api.get_posts(tags_query=tags_query, max_pages=max_pages, post_id=post_id)
            if not all_posts:
                raise ValueError("No valid posts found matching criteria after fetching.")
            return all_posts, tags_query
        except BooruError as e:
            print(f"[R] Error fetching from {api.booru_name}: {e}")
            raise
        except Exception as e:
            print(f"[R] Unexpected error during fetch: {e}")
            raise BooruError(f"Unexpected fetch error: {e}") from e

    def _select_posts(self, all_posts, sorting_order, num_images_needed, post_id, same_prompt):
        if not all_posts:
            return []
        sort_key_map = {"Score Descending": "score", "Score Ascending": "score"}
        reverse_map = {"Score Descending": True, "Score Ascending": False}
        if not post_id and sorting_order != "Random":
            sort_key = sort_key_map.get(sorting_order)
            reverse = reverse_map.get(sorting_order, False)
            if sort_key:
                print(f"[R] Sorting {len(all_posts)} by {sort_key} {'Desc' if reverse else 'Asc'}")
                all_posts = sorted(
                    all_posts,
                    key=lambda k: (
                        k.get(sort_key, 0) if isinstance(k.get(sort_key, 0), (int, float)) else 0
                    ),
                    reverse=reverse,
                )
        available_count = len(all_posts)
        selected_indices = []
        if post_id:
            selected_indices = [0] * num_images_needed
        elif same_prompt:
            chosen_index = random.randrange(available_count) if sorting_order == "Random" else 0
            selected_indices = [chosen_index] * num_images_needed
        else:
            if sorting_order == "Random":
                selected_indices = random.choices(range(available_count), k=num_images_needed)
            else:
                indices_to_use = list(range(min(available_count, num_images_needed)))
                selected_indices = indices_to_use + [indices_to_use[-1]] * (
                    num_images_needed - len(indices_to_use)
                )
        print(f"[R] Selected indices: {selected_indices}")
        return [all_posts[i] for i in selected_indices]

    def _validate_source_image(self, image) -> None:
        width, height = getattr(image, "size", (0, 0))
        if width <= 0 or height <= 0:
            raise ValueError("downloaded image has invalid dimensions")
        if width * height > MAX_SOURCE_IMAGE_PIXELS:
            raise ValueError(
                f"downloaded image exceeds {MAX_SOURCE_IMAGE_PIXELS} pixels ({width}x{height})"
            )
        frame_count = int(getattr(image, "n_frames", 1) or 1)
        if frame_count > MAX_SOURCE_IMAGE_FRAMES:
            raise ValueError(
                f"downloaded image has {frame_count} frames; maximum is {MAX_SOURCE_IMAGE_FRAMES}"
            )

    def _fetch_images(self, posts_to_fetch, use_same_image, booru_name, fringe_benefits):
        print("[R] Fetching images...")
        fetched_images = []
        image_urls = [post.get("file_url") for post in posts_to_fetch]
        if not any(url for url in image_urls if url):
            print("[R] Warn: No valid file_urls found.")
            return []
        first_valid_url = None
        if use_same_image:
            first_valid_url = next((url for url in image_urls if url), None)
            if not first_valid_url:
                print("[R] Warn: Cannot use same image, first URL invalid.")
                return []
            image_urls = [first_valid_url] * len(posts_to_fetch)
        try:
            api = self._get_booru_api(
                booru_name, fringe_benefits, getattr(self, "_gelbooru_effective_credentials", None)
            )
        except ValueError as e:
            print(f"[R] Error getting API for image fetch: {e}")
            return []
        fetched_count = 0
        for i, img_url in enumerate(image_urls):
            img_to_append = None
            try:
                if img_url and img_url.startswith(("http://", "https://")):
                    safe_url = rb_http_client.redact_url(img_url)
                    print(f"[R] Fetching {i+1}/{len(image_urls)}: {safe_url[:80]}...")
                    content = self._http_client.get_bytes(
                        img_url,
                        headers=self._get_image_fetch_headers(api, img_url),
                        timeout=30,
                        max_bytes=MAX_SOURCE_IMAGE_BYTES,
                    )
                    img_data = BytesIO(content)
                    source_image = Image.open(img_data)
                    try:
                        self._validate_source_image(source_image)
                        img_to_append = source_image.convert("RGB")
                    finally:
                        close = getattr(source_image, "close", None)
                        if callable(close) and img_to_append is not source_image:
                            close()
                    fetched_count += 1
                    print(f"[R] Successfully fetched image {i+1}: {img_to_append.size}")
                elif img_url:
                    if any(
                        site in img_url.lower()
                        for site in ["pixiv.net", "pximg.net", "twitter.com", "x.com"]
                    ):
                        print(
                            f"[R] Skipped external site URL {i+1}: {rb_http_client.redact_url(img_url)[:80]} (not a direct image)"
                        )
                    else:
                        print(
                            f"[R] Invalid URL protocol {i+1}: {rb_http_client.redact_url(img_url)[:80]}"
                        )
                else:
                    print(f"[R] No URL available for image {i+1}")
            except Exception as e:
                safe_msg = rb_http_client.safe_exception_message("Image fetch", img_url, e)
                print(f"[R] Error fetching image {i+1}: {safe_msg}")
            fetched_images.append(img_to_append)
        print(f"[R] Fetched {fetched_count} images.")
        if None in fetched_images:
            print("[R] Warn: Some images failed.")
        return fetched_images

    def _get_image_fetch_headers(self, api, img_url: str) -> dict:
        base = dict(api.headers)
        if "gelbooru" in img_url.lower() or "img4.gelbooru.com" in img_url.lower():
            base.update(
                {
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "referer": "https://gelbooru.com/",
                    "accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                    "accept-language": "en-US,en;q=0.9",
                }
            )
        return base

    def _process_single_prompt(
        self, index, raw_prompt, base_positive, base_negative, initial_additions, settings
    ):
        (
            shuffle_tags,
            chaos_mode,
            chaos_amount,
            limit_tags_pct,
            max_tags_count,
            change_dash,
            remove_artist_tags,
            remove_character_tags,
            remove_clothing_tags,
            remove_text_tags,
            restrict_subject_tags,
            remove_furry_tags,
            remove_headwear_tags,
            preserve_hair_eye_colors,
            remove_series_tags,
        ) = settings
        current_prompt = f"{initial_additions},{raw_prompt}" if initial_additions else raw_prompt
        prompt_tags = [tag.strip() for tag in re.split(r"[\,\t\s]+", current_prompt) if tag.strip()]
        base_hair_colors = set(getattr(self, "_base_hair_color_tags", set()) or [])
        base_eye_colors = set(getattr(self, "_base_eye_color_tags", set()) or [])
        # If removal flags are set, remove tags coming from selected post's artist/character lists
        try:
            post_meta = (
                self._selected_posts[index]
                if hasattr(self, "_selected_posts") and index < len(self._selected_posts)
                else {}
            )
            artist_tags_meta = (
                post_meta.get("artist_tags", []) if isinstance(post_meta, dict) else []
            )
            character_tags_meta = (
                post_meta.get("character_tags", []) if isinstance(post_meta, dict) else []
            )
            norm = self._normalize_tag
            artist_norm = {norm(t) for t in artist_tags_meta if isinstance(t, str)}
            char_norm = {norm(t) for t in character_tags_meta if isinstance(t, str)}
            if isinstance(post_meta, dict):
                copyright_tags_meta = post_meta.get("copyright_tags") or []
                if remove_character_tags and copyright_tags_meta:
                    char_norm.update({norm(t) for t in copyright_tags_meta if isinstance(t, str)})
                    char_norm.update(
                        {
                            (t or "").strip().lower()
                            for t in copyright_tags_meta
                            if isinstance(t, str)
                        }
                    )
            artist_norm.update(
                {(t or "").strip().lower() for t in artist_tags_meta if isinstance(t, str)}
            )
            char_norm.update(
                {(t or "").strip().lower() for t in character_tags_meta if isinstance(t, str)}
            )
            general_tags = []
            if isinstance(post_meta, dict):
                raw_all_tags = post_meta.get("tags") or ""
                if isinstance(raw_all_tags, str):
                    general_tags = [
                        t.strip() for t in re.split(r"[\s,]+", raw_all_tags) if t.strip()
                    ]
            if remove_character_tags and general_tags:
                for tag in general_tags:
                    tag_norm = norm(tag)
                    if ("(" in tag and ")" in tag and not tag.strip().startswith("(")) or any(
                        tag_norm.endswith(suffix)
                        for suffix in (" series", " franchise", " character", " characters")
                    ):
                        char_norm.add(tag_norm)
                        char_norm.add(tag.strip().lower())
            if remove_artist_tags and general_tags:
                for tag in general_tags:
                    tag_norm = norm(tag)
                    if (
                        tag_norm.startswith("artist:")
                        or tag_norm.endswith(" artist")
                        or " drawn by" in tag_norm
                    ):
                        artist_norm.add(tag_norm)
                        artist_norm.add(tag.strip().lower())
            allowed_subjects = set()
            if restrict_subject_tags:
                allowed_subjects.update(self._extract_subject_tags(base_positive))
                allowed_subjects.update(self._extract_subject_tags(initial_additions))
                allowed_subjects.update(
                    self._extract_subject_tags(getattr(self, "original_prompt", ""))
                )
            filter_ctx = getattr(self, "_removal_context", None)
            favorites_guard: Set[str] = set()
            if filter_ctx:
                favorites_guard = set(filter_ctx.get("favorites", frozenset()))  # type: ignore[arg-type]
            catalog = self._active_catalog()
            norm_cache = getattr(self, "_tag_normal_cache", {})
            if not isinstance(norm_cache, dict):
                norm_cache = {}
                self._tag_normal_cache = norm_cache
            filtered_prompt_tags = []
            primary_subject = None
            for t in prompt_tags:
                t_norm = self._normalize_cached(t, norm_cache)
                canonical_tag = t_norm or self._canonicalize_raw_tag(t)
                t_orig = (t or "").strip().lower()
                is_favorite = bool(t_norm and t_norm in favorites_guard)
                if is_favorite:
                    filtered_prompt_tags.append(t)
                    continue
                should_remove = False
                if remove_artist_tags and (
                    t_norm in artist_norm
                    or t_orig in artist_norm
                    or (t_norm and t_norm.endswith(" artist"))
                ):
                    should_remove = True
                elif remove_character_tags and (
                    t_norm in char_norm
                    or t_orig in char_norm
                    or ("(" in t and ")" in t and not t.strip().startswith("("))
                    or (t_norm and (t_norm.endswith(" series") or t_norm.endswith(" franchise")))
                ):
                    should_remove = True
                if (
                    not should_remove
                    and remove_clothing_tags
                    and rb_tag_pipeline.is_clothing_tag(t)
                ):
                    should_remove = True
                if (
                    not should_remove
                    and remove_text_tags
                    and rb_tag_pipeline.is_textual_tag(t, catalog.is_textual if catalog else None)
                ):
                    should_remove = True
                if not should_remove and remove_furry_tags and rb_tag_pipeline.is_furry_tag(t):
                    should_remove = True
                if (
                    not should_remove
                    and remove_headwear_tags
                    and rb_tag_pipeline.is_headwear_tag(t)
                ):
                    should_remove = True
                if (
                    not should_remove
                    and remove_series_tags
                    and rb_tag_pipeline.is_series_tag(t, catalog.category if catalog else None)
                ):
                    should_remove = True
                if not should_remove and preserve_hair_eye_colors:
                    if base_hair_colors and canonical_tag in base_hair_colors:
                        pass
                    elif base_eye_colors and canonical_tag in base_eye_colors:
                        pass
                    elif (
                        base_hair_colors
                        and rb_tag_pipeline.is_hair_color_tag(
                            t, catalog.is_hair if catalog else None
                        )
                        and canonical_tag not in base_hair_colors
                    ):
                        should_remove = True
                    elif (
                        base_eye_colors
                        and rb_tag_pipeline.is_eye_color_tag(t, catalog.is_eye if catalog else None)
                        and canonical_tag not in base_eye_colors
                    ):
                        should_remove = True
                if (
                    not should_remove
                    and restrict_subject_tags
                    and rb_tag_pipeline.is_subject_tag(t)
                ):
                    subject_norm = t_norm
                    if allowed_subjects:
                        if subject_norm not in allowed_subjects:
                            should_remove = True
                    else:
                        if primary_subject is None:
                            primary_subject = subject_norm
                        elif subject_norm != primary_subject:
                            should_remove = True
                if not should_remove and filter_ctx and t_norm:
                    should_remove = self._tag_matches_removal(t_norm, filter_ctx)
                if not should_remove:
                    filtered_prompt_tags.append(t)
            prompt_tags = filtered_prompt_tags
        except Exception:
            # fallback: ignore removal if anything goes wrong
            pass
        current_prompt = ",".join(prompt_tags)
        if shuffle_tags:
            tags_list = [t.strip() for t in current_prompt.split(",") if t.strip()]
            random.shuffle(tags_list)
            current_prompt = ",".join(tags_list)
        current_negative = base_negative
        if chaos_mode == "Shuffle All":
            current_prompt, current_negative = generate_chaos(
                current_prompt, current_negative, chaos_amount
            )
        elif chaos_mode == "Shuffle Negative":
            _, current_negative = generate_chaos("", current_negative, chaos_amount)
        if limit_tags_pct < 1.0:
            current_prompt = rb_tag_pipeline.limit_prompt_tags(
                current_prompt, limit_tags_pct, "Limit"
            )
        if max_tags_count > 0:
            current_prompt = rb_tag_pipeline.limit_prompt_tags(
                current_prompt, max_tags_count, "Max"
            )
        if change_dash:
            current_prompt = current_prompt.replace("_", " ")
            current_negative = current_negative.replace("_", " ")
        if base_positive:
            current_prompt = (
                f"{base_positive}, {current_prompt}" if current_prompt else base_positive
            )
        current_prompt = rb_tag_pipeline.remove_repeated_tags(current_prompt)
        current_negative = rb_tag_pipeline.remove_repeated_tags(current_negative)
        return current_prompt, current_negative

    def _apply_loranado(
        self,
        p,
        lora_enabled,
        lora_folder,
        lora_amount,
        lora_min,
        lora_max,
        lora_custom_weights,
        lora_lock_prev,
        lora_auto_detect_pony,
        lora_detected_loras,
        lora_blacklist,
    ):
        lora_prompt = ""
        if not lora_enabled:
            return p
        if lora_lock_prev and self.previous_loras:
            lora_prompt = self.previous_loras
            print(f"[R] Using locked LoRAs: {lora_prompt}")
        else:
            scan = self._scan_loranado_candidates(lora_folder)
            target_folder = str(
                scan.get("target_folder") or self._resolve_lora_target_folder(lora_folder)
            )
            all_loras = list(scan.get("all_files") or [])
            if not all_loras:
                print(
                    f"[R] {scan.get('message') or f'No .safetensors LoRAs found: {target_folder}'}"
                )
                self.previous_loras = ""
                return p

            if lora_auto_detect_pony:
                detected_loras = list(scan.get("detected_files") or [])
                if detected_loras:
                    candidate_loras = detected_loras
                    print(f"[R] LoRAnado: using {len(candidate_loras)} PonyXL-detected LoRAs.")
                else:
                    candidate_loras = all_loras
                    print(
                        f"[R] LoRAnado: no PonyXL markers detected in {target_folder}; falling back to all LoRAs."
                    )
            else:
                candidate_loras = all_loras
                print(
                    f"[R] LoRAnado: auto-detect disabled; using all {len(candidate_loras)} LoRAs."
                )

            before_filter_count = len(candidate_loras)
            before_blacklist_count = len(candidate_loras)
            enabled_values = _coerce_multiselect_values(lora_detected_loras)
            blacklist_values = _coerce_multiselect_values(lora_blacklist)
            if blacklist_values:
                enabled_filtered = rb_loranado.filter_candidates(
                    candidate_loras,
                    enabled_values,
                    [],
                )
                before_blacklist_count = len(enabled_filtered)
            candidate_loras = rb_loranado.filter_candidates(
                candidate_loras,
                enabled_values,
                blacklist_values,
            )
            if blacklist_values:
                print(
                    f"[R] LoRAnado: blacklist removed {before_blacklist_count - len(candidate_loras)} LoRAs."
                )
            if enabled_values and before_filter_count != before_blacklist_count:
                print(
                    f"[R] LoRAnado: enabled list kept {before_blacklist_count}/{before_filter_count} LoRAs."
                )

            if not candidate_loras:
                print("[R] LoRAnado: no LoRAs remain after enabled/blacklist filtering.")
                self.previous_loras = ""
                return p

            custom_weights = rb_loranado.parse_custom_weights(lora_custom_weights)
            if lora_custom_weights and not custom_weights:
                print(f"[R] Warn: Invalid custom LoRA weights: '{lora_custom_weights}'")
            selected_loras = rb_loranado.select_loras(
                candidate_loras,
                int(lora_amount),
                float(lora_min),
                float(lora_max),
                custom_weights,
                random,
            )
            num_to_select = len(selected_loras)
            lora_prompt = rb_loranado.format_lora_prompt(selected_loras)
            self.previous_loras = lora_prompt
            print(f"[R] LoRAnado pool size={len(candidate_loras)} | selected={num_to_select}")
            print(f"[R] Applying LoRAs: {lora_prompt}")
        if lora_prompt:
            if isinstance(p.prompt, list):
                p.prompt = [f"{lora_prompt} {pr}" for pr in p.prompt]
            else:
                p.prompt = f"{lora_prompt} {p.prompt}"
        return p

    def _prepare_img2img_pass(self, p, use_img2img, use_ip):
        self.run_img2img_pass = False
        if use_img2img:
            initial_steps = max(5, min(10, p.steps // 3))  # Use 1/3 of total steps, min 5
            print(
                f"[R] Prep Img2Img pass (steps={initial_steps}) - ControlNet {'enabled' if use_ip else 'disabled'}."
            )
            print("[R] Using higher quality initial pass to prevent distortion")
            self.real_steps = p.steps

            # Preserve the user's prompt for the initial pass. ADetailer is explicitly blocked
            # during this phase, so we no longer need an abstract placeholder prompt.
            self.original_full_prompt = p.prompt
            print(
                "[R] Keeping original prompt for initial pass; ADetailer remains blocked by guards"
            )

            self._host_scope.set_attr(p, "steps", initial_steps)

            # CRITICAL FIX: Don't reduce CFG too much - maintain image coherence
            self.original_cfg = p.cfg_scale
            self._host_scope.set_attr(
                p,
                "cfg_scale",
                max(4.0, min(p.cfg_scale, 8.0)),
            )

            # CRITICAL FIX: Reduce denoising strength to prevent over-processing
            self.original_denoising = self.img2img_denoising
            self.img2img_denoising = min(
                0.6, self.img2img_denoising
            )  # Cap at 0.6 to prevent distortion

            # Anima-specific img2img overrides
            options = getattr(self, "options", None)
            if getattr(self, "_is_anima_model", False) and getattr(
                options, "anima_tune_img2img", getattr(options, "anima_auto_detect", True)
            ):
                self.img2img_denoising = min(0.5, self.img2img_denoising)
                initial_steps = max(8, min(15, p.steps // 3))
                self._host_scope.set_attr(p, "steps", initial_steps)
                p.cfg_scale = max(3.0, min(p.cfg_scale, 6.0))
                print(
                    f"[R] Anima: using flow-matching optimized parameters "
                    f"(denoise={self.img2img_denoising}, steps={initial_steps}, cfg={p.cfg_scale})"
                )

            self.run_img2img_pass = True

            self._img2img_final_outpath_samples = getattr(p, "outpath_samples", None)
            self._img2img_final_batch_size = getattr(p, "batch_size", 1)

            print(
                "[R Save Prevention] Initial save state: "
                f"do_not_save_samples={getattr(p, 'do_not_save_samples', False)}, "
                f"outpath='{self._img2img_final_outpath_samples}'"
            )

            import tempfile

            temp_dir = tempfile.mkdtemp(prefix="ranbooru_temp_")
            self._host_scope.context.own_temp_path(temp_dir)
            self._prevent_all_image_saving(p, temp_dir)

            # Set batch size to 1 and disable extensions for initial pass
            self._host_scope.set_attr(p, "batch_size", 1)

            # LIGHTER APPROACH: Just mark that we're in initial pass - don't completely disable ADetailer
            self._mark_initial_pass(p)

            # Hide intermediary previews from pass 1 / img2img so UI only reflects final results.
            try:
                self._install_preview_guard()
                self._set_preview_guard(True, block_all=True)
            except Exception as guard_error:
                print(f"[R UI] Warn: Could not enable early preview guard: {guard_error}")

            print("[R] AGGRESSIVE: Disabled all saving, minimized batch for initial pass")
            print(
                f"[R] Optimized settings: steps={initial_steps}, cfg={p.cfg_scale}, denoising={self.img2img_denoising}"
            )

    def _cleanup_after_run(self, use_cache):
        # Don't clear self.last_img or cached data - keep them for reuse
        self.real_steps = 0
        self.run_img2img_pass = False
        try:
            self._host_scope.restore()
            if self._host_scope.context.cleanup_errors:
                print(
                    "[R Cleanup] Host cleanup warnings: "
                    + "; ".join(self._host_scope.context.cleanup_errors)
                )
        except Exception as exc:
            print(f"[R Cleanup] Host mutation restore failed: {exc}")
        self._host_scope = rb_mutation_scope.HostMutationScope()

        # Clean up stored original values
        if hasattr(self, "original_full_prompt"):
            delattr(self, "original_full_prompt")
        if hasattr(self, "_adetailer_script_args_snapshot"):
            delattr(self, "_adetailer_script_args_snapshot")
        if hasattr(self, "_current_processing_object"):
            delattr(self, "_current_processing_object")
        if hasattr(self, "original_cfg"):
            delattr(self, "original_cfg")
        if hasattr(self, "original_denoising"):
            # Restore original denoising value
            self.img2img_denoising = self.original_denoising
            delattr(self, "original_denoising")
        for attr in ("_img2img_final_outpath_samples", "_img2img_final_batch_size"):
            if hasattr(self, attr):
                delattr(self, attr)

        # Clean up processing state flags
        if hasattr(self, "_ranbooru_processing_complete"):
            delattr(self, "_ranbooru_processing_complete")
        if hasattr(self, "_ranbooru_intermediate_results"):
            delattr(self, "_ranbooru_intermediate_results")

        if hasattr(self, "_native_adetailer_fallback_used"):
            delattr(self, "_native_adetailer_fallback_used")

        # Clean up ADetailer state
        if hasattr(self, "_ranbooru_initial_pass"):
            self._ranbooru_initial_pass = False
            print("[R Cleanup] Cleared initial pass flag")
        if hasattr(self, "_initial_pass_p"):
            delattr(self, "_initial_pass_p")

        # Clean up early protection state
        if hasattr(self, "_temp_disabled_adetailer"):
            # Force restore if cleanup is called early
            self._restore_early_adetailer_protection(getattr(self, "_initial_pass_p", None))

        # Ensure any manual patches are removed once we're finished.
        self._unpatch_manual_adetailer_overrides()
        patch_errors = self._adetailer_patches.uninstall_all()
        if patch_errors:
            print("[R Cleanup] ADetailer patch restore warnings: " + "; ".join(patch_errors))

        # Ensure preview suppression never leaks into the next generation.
        try:
            self._set_preview_guard(False)
        except Exception:
            pass
        self._adetailer_state.reset()

        http_client = getattr(self, "_http_client", None)
        if http_client is not None:
            try:
                http_client.close()
            except Exception as exc:
                print(f"[R Post] Warn: Failed to close booru session: {exc}")
        self._http_client = rb_http_client.BooruSession(use_cache=False)
        if hasattr(self, "cache_installed_by_us"):
            try:
                del self.cache_installed_by_us
            except AttributeError:
                pass

    def _force_release_processing_guards(self, reason, attempt_cleanup=True, processing_obj=None):
        """Aggressively clear processing locks when a previous job ended abruptly."""
        try:
            print(f"[R Guard] Forcing release of RanbooruX processing lock: {reason}")
        except Exception:
            pass

        released = False
        if attempt_cleanup:
            try:
                use_cache = getattr(self, "_post_use_cache", True)
                self._cleanup_after_run(use_cache)
            except Exception as exc:
                print(f"[R Guard] Cleanup while releasing lock failed: {exc}")

        try:
            if hasattr(self, "_current_processing_key"):
                processing_key = self._current_processing_key
                if hasattr(self, processing_key):
                    delattr(self, processing_key)
                delattr(self, "_current_processing_key")
            released = True
        except Exception as exc:
            print(f"[R Guard] Failed clearing instance processing key: {exc}")

        try:
            setattr(self.__class__, "_ranbooru_global_processing", False)
        except Exception as exc:
            print(f"[R Guard] Failed clearing global processing flag: {exc}")
            released = False

        if hasattr(self, "_current_processing_object"):
            try:
                delattr(self, "_current_processing_object")
            except Exception as exc:
                print(f"[R Guard] Failed clearing processing object reference: {exc}")
                released = False
        if processing_obj is not None and hasattr(processing_obj, "_ranbooru_already_processing"):
            try:
                delattr(processing_obj, "_ranbooru_already_processing")
            except Exception:
                try:
                    setattr(processing_obj, "_ranbooru_already_processing", False)
                except Exception as exc:
                    print(f"[R Guard] Failed clearing processing object guard: {exc}")
                    released = False

        # Ensure ADetailer hooks are restored so future generations run normally
        try:
            self._restore_early_adetailer_protection(processing_obj)
        except Exception as exc:
            print(f"[R Guard] Failed restoring ADetailer protection: {exc}")
            released = False

        return released

    def _clear_processing_guards(self, p=None, prefix="[R Post]") -> None:
        if hasattr(self, "_current_processing_key"):
            processing_key = self._current_processing_key
            if hasattr(self, processing_key):
                delattr(self, processing_key)
                print(f"{prefix} Cleared processing guard for request {processing_key}")
            delattr(self, "_current_processing_key")
        setattr(self.__class__, "_ranbooru_global_processing", False)
        if hasattr(self, "_current_processing_object"):
            try:
                delattr(self, "_current_processing_object")
            except Exception:
                pass
        if p is not None:
            try:
                setattr(p, "_ranbooru_finalized", True)
            except Exception:
                pass
            if hasattr(p, "_ranbooru_already_processing"):
                try:
                    delattr(p, "_ranbooru_already_processing")
                except Exception:
                    try:
                        setattr(p, "_ranbooru_already_processing", False)
                    except Exception:
                        pass

    def _abort_before_process_run(self, reason: str, p=None) -> None:
        """Abort a before_process run after guards were acquired."""
        try:
            print(f"[R Before] Aborting RanbooruX run: {reason}")
        except Exception:
            pass
        processing_obj = p or getattr(self, "_current_processing_object", None)
        self._force_release_processing_guards(
            reason, attempt_cleanup=True, processing_obj=processing_obj
        )

    def _maybe_release_stale_guards(self, new_processing_obj):
        """Detect and release stale locks left behind by interrupted runs."""
        guard_active = getattr(self.__class__, "_ranbooru_global_processing", False)
        if not guard_active:
            return

        previous_obj = getattr(self, "_current_processing_object", None)
        if previous_obj is new_processing_obj:
            return

        state_interrupted = False
        state_processing = False
        try:
            state = getattr(shared, "state", None)
            if state is not None:
                state_interrupted = getattr(state, "interrupted", False) or getattr(
                    state, "stopping_job", False
                )
                state_processing = getattr(state, "processing", False)
        except Exception:
            state_processing = False

        previous_finalized = False
        if previous_obj is not None:
            previous_finalized = getattr(previous_obj, "_ranbooru_finalized", False)

        # Release when the WebUI is idle, interrupted, or the previous object was already finalized.
        if not state_processing or state_interrupted or previous_finalized or previous_obj is None:
            reason_bits = []
            if not state_processing:
                reason_bits.append("WebUI idle")
            if state_interrupted:
                reason_bits.append("interrupted flag set")
            if previous_finalized:
                reason_bits.append("previous job finalized")
            if previous_obj is None:
                reason_bits.append("no tracked processing object")
            reason = "; ".join(reason_bits) if reason_bits else "stale lock detected"
            self._force_release_processing_guards(reason, processing_obj=new_processing_obj)
        else:
            # New processing object arrived while guard is still active - treat as stale lock.
            self._force_release_processing_guards(
                "new processing request detected while guard active",
                processing_obj=new_processing_obj,
            )

    @staticmethod
    def _anima_quality_prefix() -> str:
        """Return Anima's recommended positive quality prefix."""
        return "masterpiece, best quality, score_7, safe, "

    @staticmethod
    def _anima_negative_default() -> str:
        """Return Anima's recommended negative prompt."""
        return "worst quality, low quality, score_1, score_2, score_3, artist name, blurry, jpeg artifacts, chromatic aberration"

    @staticmethod
    def _has_quality_prefix(prompt: str) -> bool:
        """Check if prompt already has quality tokens (case-insensitive)."""
        if not prompt:
            return False
        quality_tokens = {
            "masterpiece",
            "best quality",
            "high quality",
            "score_7",
            "score_8",
            "score_9",
            "safe",
        }
        first_10 = [t.strip().lower() for t in prompt.split(",")[:10]]
        return any(token in tag for token in quality_tokens for tag in first_10)

    def before_process(self, p: StableDiffusionProcessing, *args):
        try:
            # Fast-path for our own internal img2img calls: initialize seeds and exit
            if getattr(p, "_ranbooru_internal_img2img", False):
                try:
                    # Minimal seeds init to satisfy WebUI expectations
                    base_seed = getattr(p, "seed", -1)
                    if base_seed == -1:
                        base_seed = random.randint(0, 2**32 - 1)
                        p.seed = base_seed
                    batch_count = max(1, getattr(p, "n_iter", 1))
                    batch_size = max(1, getattr(p, "batch_size", 1))
                    total_images = batch_count * batch_size
                    p.all_seeds = [base_seed + i for i in range(total_images)]
                    base_subseed = getattr(p, "subseed", -1)
                    if base_subseed == -1:
                        base_subseed = random.randint(0, 2**32 - 1)
                        p.subseed = base_subseed
                    p.all_subseeds = [base_subseed + i for i in range(total_images)]
                    # Mirror common aliases expected by some codepaths
                    p.seeds = list(p.all_seeds)
                    p.subseeds = list(p.all_subseeds)
                    print(
                        f"[R Before] Internal img2img fast-path: seeds={len(p.all_seeds)} from {base_seed}, subseeds from {base_subseed}"
                    )
                except Exception as _e:
                    print(f"[R Before] WARN: Internal img2img seed init failed: {_e}")
                return

            # Ensure leftover guards from interrupted jobs don't block new generations
            self._maybe_release_stale_guards(p)

            # CRITICAL: Ultra-strict processing guard to prevent any duplicate runs
            processing_key = f"_ranbooru_processing_{id(p)}"

            # Check multiple levels of guards
            if (
                hasattr(self, processing_key)
                or getattr(self.__class__, "_ranbooru_global_processing", False)
                or hasattr(p, "_ranbooru_already_processing")
            ):
                print("[R Before] RanbooruX already processing - BLOCKING duplicate run")
                # Ensure seeds exist to prevent IndexError in core pipeline
                try:
                    base_seed = getattr(p, "seed", -1)
                    if base_seed == -1:
                        base_seed = random.randint(0, 2**32 - 1)
                        p.seed = base_seed
                    batch_count = max(1, getattr(p, "n_iter", 1))
                    batch_size = max(1, getattr(p, "batch_size", 1))
                    total_images = batch_count * batch_size
                    if not getattr(p, "all_seeds", None):
                        p.all_seeds = [base_seed + i for i in range(total_images)]
                    base_subseed = getattr(p, "subseed", -1)
                    if base_subseed == -1:
                        base_subseed = random.randint(0, 2**32 - 1)
                        p.subseed = base_subseed
                    if not getattr(p, "all_subseeds", None):
                        p.all_subseeds = [base_subseed + i for i in range(total_images)]
                except Exception as _e:
                    print(f"[R Before] WARN: Seed safety init failed on duplicate: {_e}")
                return

            # Set triple-level guards: instance, class, and processing object
            setattr(self, processing_key, True)
            setattr(self.__class__, "_ranbooru_global_processing", True)
            setattr(p, "_ranbooru_already_processing", True)
            print(f"[R Before] Started RanbooruX processing for request {id(p)}")
            self._current_processing_object = p
            try:
                self._host_scope.restore()
            except Exception as exc:
                print(f"[R Before] Warn: stale host-scope cleanup failed: {exc}")
            self._host_scope = rb_mutation_scope.HostMutationScope()
            script_args_source = getattr(p, "script_args", None)
            if isinstance(script_args_source, (list, tuple)):
                self._adetailer_script_args_snapshot = list(script_args_source)
            else:
                self._adetailer_script_args_snapshot = None

            # Store the processing key for cleanup
            self._current_processing_key = processing_key

            options = rb_run_options.RunOptions.from_script_args(args)
            enabled = options.enabled
            tags = options.tags
            booru = options.booru
            gelbooru_api_key_ui = options.gelbooru_api_key
            gelbooru_user_id_ui = options.gelbooru_user_id
            gelbooru_compat_base_url_ui = options.gelbooru_compat_base_url
            remove_bad_tags_ui = options.remove_bad_tags
            max_pages = options.max_pages
            change_dash = options.change_dash
            same_prompt = options.same_prompt
            fringe_benefits = options.fringe_benefits
            remove_tags_ui = options.remove_tags
            use_img2img = options.use_img2img
            denoising = options.denoising
            use_last_img = options.use_last_img
            change_background = options.change_background
            change_color = options.change_color
            shuffle_tags = options.shuffle_tags
            post_id = options.post_id
            mix_prompt = options.mix_prompt
            mix_amount = options.mix_amount
            chaos_mode = options.chaos_mode
            chaos_amount = options.chaos_amount
            limit_tags_pct = options.limit_tags
            max_tags_count = options.max_tags
            sorting_order = options.sorting_order
            mature_rating = options.mature_rating
            lora_folder = options.lora_folder
            lora_amount = options.lora_amount
            lora_min = options.lora_min
            lora_max = options.lora_max
            lora_enabled = options.lora_enabled
            lora_custom_weights = options.lora_custom_weights
            lora_lock_prev = options.lora_lock_prev
            use_ip = options.use_ip
            use_search_txt = options.use_search_txt
            use_remove_txt = options.use_remove_txt
            choose_search_txt = options.choose_search_txt
            choose_remove_txt = options.choose_remove_txt
            crop_center = options.crop_center
            enable_adetailer_support = options.enable_adetailer_support
            use_same_seed = options.use_same_seed
            reuse_cached_posts = options.reuse_cached_posts
            use_cache = options.use_cache
            log_prompt_sources_ui = options.log_prompt_sources
            remove_artist_tags_ui = options.remove_artist_tags
            remove_character_tags_ui = options.remove_character_tags
            remove_clothing_tags_ui = options.remove_clothing_tags
            remove_text_tags_ui = options.remove_text_tags
            restrict_subject_tags_ui = options.restrict_subject_tags
            remove_furry_tags_ui = options.remove_furry_tags
            remove_headwear_tags_ui = options.remove_headwear_tags
            remove_girl_suffix_tags_ui = options.remove_girl_suffix_tags
            preserve_hair_eye_colors_ui = options.preserve_hair_eye_colors
            remove_series_tags_ui = options.remove_series_tags
            use_tag_catalog_ui = options.use_tag_catalog
            tag_catalog_path_ui = options.catalog_path
            lora_auto_detect_pony_ui = options.lora_auto_detect_pony
            lora_detected_loras_ui = options.lora_detected_loras
            lora_blacklist_ui = options.lora_blacklist
        except Exception as e:
            print(f"[R Before] CRITICAL Error unpack args: {e}. Aborting.")
            traceback.print_exc()
            self._abort_before_process_run("script argument parsing failed", p)
            return

        # denoising may come through as an empty string from the UI in some contexts; parse defensively
        try:
            self.img2img_denoising = float(denoising)
        except Exception:
            # fall back to previous default and warn
            self.img2img_denoising = float(getattr(self, "img2img_denoising", 0.75))
            print(
                f"[R Before] Warn: invalid denoising value '{denoising}', falling back to {self.img2img_denoising}"
            )

        # Persist values needed for postprocess to avoid fragile unpacking there
        self._post_enabled = bool(enabled)
        self._post_use_img2img = bool(use_img2img)
        self._post_use_ip = bool(use_ip)
        self._post_use_last_img = bool(use_last_img)
        self._post_crop_center = bool(crop_center)
        self._post_use_cache = bool(use_cache)
        self._reuse_cached_posts = bool(reuse_cached_posts)
        self._adetailer_support_enabled = bool(enable_adetailer_support)
        self._post_adetailer_enabled = self._adetailer_support_enabled
        prev_manual_state = getattr(self, "_manual_adetailer_prev_enabled", False)
        self._handle_adetailer_toggle_change(prev_manual_state, self._adetailer_support_enabled, p)
        self._manual_adetailer_prev_enabled = self._adetailer_support_enabled
        self._log_prompt_sources = bool(log_prompt_sources_ui)

        # Anima model detection
        try:
            info = get_anima_model_info(shared.sd_model)
            self._is_anima_model = info["detected"]
            if self._is_anima_model:
                anima_auto_detect = getattr(options, "anima_auto_detect", True)
                if anima_auto_detect:
                    change_dash = True
                    print(
                        f"[R] Anima model detected ({info['model_name']}) - auto-enabling space-separated tags"
                    )
        except Exception:
            self._is_anima_model = False

        self._current_booru_name = booru
        if booru == "gelbooru":
            self._gelbooru_effective_credentials = self._resolve_gelbooru_credentials(
                gelbooru_api_key_ui, gelbooru_user_id_ui
            )
        else:
            self._gelbooru_effective_credentials = None
        if booru == "gelbooru-compatible":
            sanitized_base = _sanitize_gelbooru_compat_base_url(gelbooru_compat_base_url_ui)
            if sanitized_base:
                self._gelbooru_compat_base_url = sanitized_base
            elif not self._gelbooru_compat_base_url:
                print(
                    "[R Before] Warn: Gelbooru-compatible base URL is empty. Set a base URL in the UI before running."
                )
        if not self._reuse_cached_posts:
            self._last_post_urls = []
        self._posts_used_for_generation = []
        self._final_prompts_snapshot = []
        self._final_negative_prompts_snapshot = []

        if lora_enabled:
            p = self._apply_loranado(
                p,
                lora_enabled,
                lora_folder,
                lora_amount,
                lora_min,
                lora_max,
                lora_custom_weights,
                lora_lock_prev,
                lora_auto_detect_pony_ui,
                lora_detected_loras_ui,
                lora_blacklist_ui,
            )

        # CRITICAL: Ensure seeds are properly initialized to prevent IndexError
        # This must happen EVERY time, not just when they're empty
        if hasattr(p, "seed"):
            base_seed = p.seed if p.seed != -1 else random.randint(0, 2**32 - 1)
        else:
            base_seed = random.randint(0, 2**32 - 1)
            p.seed = base_seed

        # Calculate batch size - be more defensive about this
        batch_count = max(1, getattr(p, "n_iter", 1))
        batch_size = max(1, getattr(p, "batch_size", 1))
        total_images = batch_count * batch_size

        # ALWAYS reinitialize seeds to prevent index errors
        p.all_seeds = [base_seed + i for i in range(total_images)]
        print(
            f"[R Before] Initialized p.all_seeds with {len(p.all_seeds)} seeds starting from {base_seed}"
        )

        # Also reinitialize all_subseeds
        base_subseed = getattr(p, "subseed", -1)
        if base_subseed == -1:
            base_subseed = random.randint(0, 2**32 - 1)
        p.all_subseeds = [base_subseed + i for i in range(total_images)]
        print(
            f"[R Before] Initialized p.all_subseeds with {len(p.all_subseeds)} subseeds starting from {base_subseed}"
        )

        # ADDITIONAL: Ensure other seed-related attributes exist
        if not hasattr(p, "seeds"):
            p.seeds = p.all_seeds.copy()
        if not hasattr(p, "subseeds"):
            p.subseeds = p.all_subseeds.copy()

        self._reset_adetailer_state_for_run(p)

        if not enabled:
            print("[R] RanbooruX is DISABLED - skipping image fetch")
            self._adetailer_support_enabled = False
            self._post_adetailer_enabled = False
            self._abort_before_process_run("extension disabled for this run", p)
            return

        self._reset_script_runner_guards()
        if self._is_adetailer_enabled():
            print("[R Before] Resetting ADetailer blocking flags for new generation")
        else:
            print(
                "[R Before] Manual ADetailer support disabled - ensuring native ADetailer remains available"
            )

        # Clear notification that extension is active
        print("[R Before] RanbooruX IS ENABLED AND RUNNING")
        print(
            f"[R Before] Search tags: '{tags}' | Booru: {booru} | Img2Img: {use_img2img} | ControlNet: {use_ip}"
        )

        # Check if we should reuse existing images or fetch new ones
        reuse_cached_posts = bool(getattr(self, "_reuse_cached_posts", False))

        # Special handling: if tags contain "!refresh", force fetch new images
        force_refresh = "!refresh" in (tags or "")
        if force_refresh:
            original_tags = tags
            tags = tags.replace("!refresh", "").replace(",,", ",").strip(",")
            print("[R Before] Detected !refresh command - forcing new image fetch")
            print(f"[R Before] Original tags: '{original_tags}' -> Cleaned: '{tags}'")

        self._use_tag_catalog = bool(use_tag_catalog_ui)
        if self._catalog_source == "custom":
            incoming_custom_path = (tag_catalog_path_ui or "").strip()
            if incoming_custom_path:
                self._custom_catalog_path = incoming_custom_path
            self._tag_catalog_path = self._custom_catalog_path
        else:
            self._tag_catalog_path = ""
        if not self._use_tag_catalog:
            self._set_catalog_source("bundled")
        ok, message = self._load_tag_catalog()
        if not ok:
            self._catalog = NoopCatalog()
        self._tag_catalog_status_text = message
        self._save_tag_catalog_preferences()
        self._update_catalog_status(message)

        personal_remove_tags, favorites_tags = self._load_personal_lists()

        current_search_key = f"{booru}_{tags}_{post_id}_{mature_rating}_{sorting_order}"
        if not reuse_cached_posts:
            should_fetch_new = True
        else:
            should_fetch_new = (
                force_refresh
                or not hasattr(self, "_last_search_key")
                or self._last_search_key != current_search_key
                or not hasattr(self, "_cached_posts")
                or not self._cached_posts
                or not hasattr(self, "last_img")
                or not self.last_img
            )

        if not reuse_cached_posts:
            self._cached_posts = []
            self._cached_search_tags = ""
            self._cached_bad_tags = set()
            self._cached_initial_additions = ""
            self._cached_strict_rejections = []
            self._cached_strict_active = False
            self._cached_strict_relaxed = False

        if should_fetch_new:
            if force_refresh:
                print("[R Before] Fetching new images (!refresh command used)")
            else:
                print(
                    "[R Before] Fetching new images (search parameters changed or caching disabled)"
                )
        else:
            if reuse_cached_posts:
                print(
                    f"[R Before] Reusing cached images ({len(self.last_img)} images) from previous search"
                )
                print("[R Before] TIP: Add '!refresh' to your tags to force fetch new images")

        self.original_prompt = (
            p.prompt
            if isinstance(p.prompt, str)
            else (p.prompt[0] if isinstance(p.prompt, list) and p.prompt else "")
        )

        # Anima: apply default prompts
        if self._is_anima_model and getattr(options, "anima_auto_detect", True):
            if not self._has_quality_prefix(self.original_prompt):
                self.original_prompt = f"{self._anima_quality_prefix()}{self.original_prompt}"
                print("[R] Anima: applied default quality tags")
            if not isinstance(p.negative_prompt, str) or not p.negative_prompt.strip():
                p.negative_prompt = self._anima_negative_default()

        base_hair_colors, base_eye_colors = self._extract_color_tags(self.original_prompt)
        self._base_hair_color_tags = base_hair_colors
        self._base_eye_color_tags = base_eye_colors
        self._strict_img2img_active = False
        self._strict_img2img_relaxed = False
        self._strict_img2img_rejections = []
        self._strict_initial_additions = ""
        self._strict_allowed_subjects = set(self._extract_subject_tags(self.original_prompt))
        base_subjects = set(self._strict_allowed_subjects)

        if not should_fetch_new:
            # Skip the fetching process but continue with cached images
            selected_posts = self._cached_posts
            print(f"[R Before] Using {len(selected_posts)} cached posts")
        else:
            self.last_img = []

        try:
            self.cache_installed_by_us = self._setup_cache(use_cache)

            # Always calculate num_images_needed - needed for both new and cached images
            num_images_needed = p.batch_size * p.n_iter
            filter_ctx: Optional[Dict[str, object]] = None
            if should_fetch_new:
                search_tags, bad_tags, initial_additions = self._prepare_tags(
                    tags,
                    remove_tags_ui,
                    use_remove_txt,
                    choose_remove_txt,
                    change_background,
                    change_color,
                    use_search_txt,
                    choose_search_txt,
                    remove_bad_tags_ui,
                )
                bad_tags = set(bad_tags)
                bad_tags.update(personal_remove_tags)
                self._strict_initial_additions = initial_additions

                allowed_subjects = set()
                if bool(restrict_subject_tags_ui):
                    allowed_subjects = set(base_subjects)
                    allowed_subjects.update(self._extract_subject_tags(initial_additions))
                    self._strict_allowed_subjects = set(allowed_subjects)
                else:
                    self._strict_allowed_subjects = set()

                filter_ctx = self._build_removal_context(bad_tags, favorites_tags)
                self._removal_context = filter_ctx

                toggles_tuple = (
                    bool(remove_artist_tags_ui),
                    bool(remove_character_tags_ui),
                    bool(remove_clothing_tags_ui),
                    bool(remove_text_tags_ui),
                    bool(restrict_subject_tags_ui),
                    bool(remove_furry_tags_ui),
                    bool(remove_headwear_tags_ui),
                    bool(remove_girl_suffix_tags_ui),
                    bool(preserve_hair_eye_colors_ui),
                    bool(remove_series_tags_ui),
                )
                self._remove_series_tags = bool(remove_series_tags_ui)
                self._remove_character_tags = bool(remove_character_tags_ui)
                self._remove_text_tags = bool(remove_text_tags_ui)
                self._preserve_hair_eye_colors = bool(preserve_hair_eye_colors_ui)
                base_colors_tuple = (set(base_hair_colors), set(base_eye_colors))

                api = self._get_booru_api(
                    booru, fringe_benefits, getattr(self, "_gelbooru_effective_credentials", None)
                )
                all_posts, tags_query = self._fetch_booru_posts(
                    api, search_tags, mature_rating, max_pages, post_id
                )

                filtered_posts = list(all_posts)
                strict_rejections: List[Dict[str, object]] = []
                strict_active = False
                strict_relaxed = False

                strict_enabled_for_run = bool(use_img2img and not post_id)

                if strict_enabled_for_run:
                    filtered_posts, strict_rejections, strict_active, strict_relaxed = (
                        self._apply_strict_img2img_prefilter(
                            list(all_posts),
                            api=api,
                            tags_query=tags_query,
                            post_id=post_id,
                            num_images_needed=num_images_needed,
                            max_pages=max_pages,
                            filter_ctx=filter_ctx,
                            toggles=toggles_tuple,
                            base_colors=base_colors_tuple,
                            allowed_subjects=allowed_subjects,
                        )
                    )
                    self._strict_img2img_active = strict_active
                    self._strict_img2img_relaxed = strict_relaxed
                    self._strict_img2img_rejections = list(strict_rejections)
                    self._last_rejections = list(self._strict_img2img_rejections)
                    if strict_active:
                        if strict_rejections:
                            print(
                                f"[R Strict] Img2Img strict pre-filter rejected {len(strict_rejections)} candidate(s) before download"
                            )
                            preview = strict_rejections[:STRICT_IMG2IMG_LOG_SAMPLE]
                            for entry in preview:
                                print(
                                    f"[R Strict] - {entry.get('booru')} post {entry.get('post_id')} rejected by {entry.get('rule_type')} (tag: {entry.get('matched_tag')})"
                                )
                            if len(strict_rejections) > STRICT_IMG2IMG_LOG_SAMPLE:
                                print(
                                    f"[R Strict] - ... {len(strict_rejections) - STRICT_IMG2IMG_LOG_SAMPLE} more"
                                )
                        print(
                            f"[R Strict] {len(filtered_posts)} candidate(s) available after strict filtering (need {num_images_needed})"
                        )
                else:
                    self._strict_img2img_active = False
                    self._strict_img2img_relaxed = False
                    self._strict_img2img_rejections = []
                    self._last_rejections = []

                all_posts = filtered_posts
                selected_posts = self._select_posts(
                    filtered_posts, sorting_order, num_images_needed, post_id, same_prompt
                )

                # Cache the results for future use
                self._cached_posts = selected_posts
                self._last_search_key = current_search_key
                self._cached_search_tags = search_tags
                self._cached_bad_tags = set(bad_tags)
                self._cached_initial_additions = initial_additions
                self._cached_strict_rejections = list(self._strict_img2img_rejections)
                self._cached_strict_active = self._strict_img2img_active
                self._cached_strict_relaxed = self._strict_img2img_relaxed

                post_urls = []
                try:
                    for idx, post in enumerate(selected_posts):
                        post_url = get_original_post_url(post)
                        if post_url:
                            post_urls.append(post_url)
                            print(f"[R] Original post {idx+1}/{len(selected_posts)}: {post_url}")
                except Exception as e:
                    print(f"[R] Warn: Failed to compute original post URLs: {e}")
                self._last_post_urls = post_urls

                if use_img2img or use_ip:
                    self.last_img = self._fetch_images(
                        selected_posts, use_last_img, booru, fringe_benefits
                    )
            else:
                # Use cached values
                search_tags = getattr(self, "_cached_search_tags", "")
                bad_tags = set(getattr(self, "_cached_bad_tags", set()))
                bad_tags.update(personal_remove_tags)
                initial_additions = getattr(self, "_cached_initial_additions", "")
                self._cached_bad_tags = set(bad_tags)
                self._strict_initial_additions = initial_additions
                all_posts = list(getattr(self, "_cached_posts", []))

                if bool(restrict_subject_tags_ui):
                    allowed_subjects = set(base_subjects)
                    allowed_subjects.update(self._extract_subject_tags(initial_additions))
                    self._strict_allowed_subjects = set(allowed_subjects)
                else:
                    self._strict_allowed_subjects = set()

                filter_ctx = getattr(self, "_removal_context", None)
                if filter_ctx is None:
                    filter_ctx = self._build_removal_context(bad_tags, favorites_tags)
                self._strict_img2img_active = bool(getattr(self, "_cached_strict_active", False))
                self._strict_img2img_relaxed = bool(getattr(self, "_cached_strict_relaxed", False))
                cached_rejections = getattr(self, "_cached_strict_rejections", [])
                self._strict_img2img_rejections = (
                    list(cached_rejections) if cached_rejections else []
                )
                self._last_rejections = list(self._strict_img2img_rejections)

            if filter_ctx is None:
                filter_ctx = self._build_removal_context(bad_tags, favorites_tags)
            self._removal_context = filter_ctx
            self._tag_normal_cache = {}

            # persist selected posts and removal flags so prompt processing can access them
            self._selected_posts = selected_posts
            self._remove_artist_tags = bool(remove_artist_tags_ui)
            self._remove_character_tags = bool(remove_character_tags_ui)
            self._remove_clothing_tags = bool(remove_clothing_tags_ui)
            self._remove_text_tags = bool(remove_text_tags_ui)
            self._restrict_subject_tags = bool(restrict_subject_tags_ui)
            self._remove_furry_tags = bool(remove_furry_tags_ui)
            self._remove_headwear_tags = bool(remove_headwear_tags_ui)
            self._preserve_hair_eye_colors = bool(preserve_hair_eye_colors_ui)
            self._remove_series_tags = bool(remove_series_tags_ui)

            # Preview UI removed by request

            base_negative = getattr(p, "negative_prompt", "") or ""
            final_prompts = []
            final_negative_prompts = [base_negative] * num_images_needed
            prompt_processing_settings = (
                shuffle_tags,
                chaos_mode,
                chaos_amount,
                limit_tags_pct,
                max_tags_count,
                change_dash,
                self._remove_artist_tags,
                self._remove_character_tags,
                self._remove_clothing_tags,
                self._remove_text_tags,
                self._restrict_subject_tags,
                self._remove_furry_tags,
                self._remove_headwear_tags,
                self._preserve_hair_eye_colors,
                self._remove_series_tags,
            )

            # Ensure we only use the number of posts that match the current generation request
            posts_to_use = (
                selected_posts[:num_images_needed]
                if len(selected_posts) > num_images_needed
                else selected_posts
            )
            # If we need more images than available posts, repeat the last post
            while len(posts_to_use) < num_images_needed:
                posts_to_use.append(posts_to_use[-1] if posts_to_use else selected_posts[0])
            self._posts_used_for_generation = list(posts_to_use)

            # Also align cached images with current generation request
            if not should_fetch_new and hasattr(self, "last_img") and self.last_img:
                # Adjust cached images to match current request
                if len(self.last_img) > num_images_needed:
                    self.last_img = self.last_img[:num_images_needed]
                elif len(self.last_img) < num_images_needed:
                    # Repeat images to fill the requirement
                    while len(self.last_img) < num_images_needed:
                        self.last_img.append(self.last_img[-1] if self.last_img else None)
                print(
                    f"[R] Aligned cached images: {len(self.last_img)} images for {num_images_needed} requested"
                )

            raw_prompts = [post.get("tags", "") for post in posts_to_use]
            print(
                f"[R] Using {len(posts_to_use)} posts for {num_images_needed} images (from {len(selected_posts)} cached)"
            )

            if mix_prompt and not post_id and not same_prompt:
                print(f"[R] Mixing tags from {mix_amount} posts...")
                mixed_prompts = []
                original_indices_map = {i: post for i in range(len(all_posts))}
                for _ in range(num_images_needed):
                    mix_indices = random.sample(
                        list(original_indices_map.keys()),
                        min(mix_amount, len(original_indices_map)),
                    )
                    combined_tags = set()
                    for mix_idx in mix_indices:
                        combined_tags.update(
                            [
                                t.strip()
                                for t in all_posts[mix_idx].get("tags", "").split(" ")
                                if t.strip()
                            ]
                        )
                    final_mix_tags = list(combined_tags)
                    random.shuffle(final_mix_tags)
                    if max_tags_count > 0:
                        final_mix_tags = final_mix_tags[:max_tags_count]
                    mixed_prompts.append(",".join(final_mix_tags))
                raw_prompts = mixed_prompts

            for i, rp in enumerate(raw_prompts):
                processed_prompt, processed_negative = self._process_single_prompt(
                    i,
                    rp,
                    self.original_prompt,
                    base_negative,
                    initial_additions,
                    prompt_processing_settings,
                )
                final_prompts.append(processed_prompt)
                final_negative_prompts[i] = processed_negative

            valid_final_prompts = [s for s in final_prompts if s and not s.isspace()]
            if not valid_final_prompts:
                p.prompt = " "
                p.negative_prompt = "" if num_images_needed == 1 else [""] * num_images_needed
                print("[R] Warn: No valid prompts generated.")
            elif num_images_needed == 1:
                p.prompt = valid_final_prompts[0]
                p.negative_prompt = final_negative_prompts[0] if final_negative_prompts else ""
            else:
                p.prompt = valid_final_prompts
                p.negative_prompt = final_negative_prompts
            self._final_prompts_snapshot = list(valid_final_prompts)
            self._final_negative_prompts_snapshot = list(final_negative_prompts)
            # Debug print removed per user request

            if use_same_seed:
                p.seed = p.seed if p.seed != -1 else random.randint(0, 2**32 - 1)
                print(f"[R] Using same seed: {p.seed}")

            if use_ip and self.last_img and self.last_img[0] is not None:
                cn_configured = False
                # Forge Neo direct: find ControlNet script in alwayson_scripts
                try:
                    scripts_runner = getattr(p, "scripts", None)
                    cn_script = None
                    if scripts_runner is not None:
                        for s in getattr(scripts_runner, "alwayson_scripts", []):
                            filename = getattr(s, "filename", "") or ""
                            title = getattr(s, "title", lambda: "")()
                            if "controlnet" in filename.lower() or "controlnet" in title.lower():
                                cn_script = s
                                break

                    if cn_script is not None:
                        start = getattr(cn_script, "args_from", None)
                        end = getattr(cn_script, "args_to", None)
                        if isinstance(start, int) and isinstance(end, int) and 0 <= start < end:
                            full_args = (
                                list(p.script_args)
                                if isinstance(p.script_args, tuple)
                                else list(p.script_args or [])
                            )
                            if end <= len(full_args):
                                unit = full_args[start]
                                img_for_cn = (
                                    self.last_img[0].convert("RGB")
                                    if self.last_img[0].mode != "RGB"
                                    else self.last_img[0]
                                )
                                cn_image = {"image": np.array(img_for_cn), "mask": None}

                                if isinstance(unit, dict):
                                    unit["enabled"] = True
                                    unit["weight"] = float(self.img2img_denoising)
                                    unit["image"] = cn_image
                                elif hasattr(unit, "enabled"):
                                    unit.enabled = True
                                    unit.weight = float(self.img2img_denoising)
                                    unit.image = cn_image

                                setattr(p, "resize_mode", 1)
                                p.script_args = tuple(full_args)
                                cn_configured = True
                                print(
                                    "[R Before] ControlNet configured via Forge Neo direct (p.script_args slice)."
                                )
                except Exception as e:
                    print(f"[R Before] ControlNet config error: {e}")

                if not cn_configured and use_ip:
                    if not hasattr(p, "resize_mode"):
                        setattr(p, "resize_mode", 1)
                    print("[R Before] ControlNet script not found; p.resize_mode safeguard set.")

            self._prepare_img2img_pass(p, use_img2img, use_ip)

        except Exception as e:
            print(f"[Ranbooru BeforeProcess] UNEXPECTED ERROR: {e}")
            traceback.print_exc()
            self._abort_before_process_run("before_process failed", p)
            return

        print("[Ranbooru BeforeProcess] Finished.")

    def _reset_adetailer_state_for_run(self, p):
        """Clear RanbooruX-managed ADetailer flags before a generation begins."""
        self._adetailer_state.reset()
        patch_errors = self._adetailer_patches.uninstall_all()
        if patch_errors:
            print("[R Before] ADetailer stale patch restore warnings: " + "; ".join(patch_errors))
        self._unpatch_manual_adetailer_overrides()
        setattr(self.__class__, "_ranbooru_block_all_adetailer", False)
        setattr(self.__class__, "_adetailer_global_guard_active", False)
        setattr(self.__class__, "_adetailer_pipeline_blocked", False)
        setattr(self.__class__, "_ranbooru_manual_adetailer_active", False)
        cleanup_attrs = (
            "_ranbooru_manual_adetailer_complete",
            "_ad_disabled",
            "_ranbooru_skip_initial_adetailer",
            "_ranbooru_suppress_all_processing",
            "_ranbooru_adetailer_already_processed",
        )
        for attr in cleanup_attrs:
            if hasattr(p, attr):
                try:
                    delattr(p, attr)
                except Exception:
                    setattr(p, attr, False)

        # Ensure any global guard we installed is cleared before the next generation begins
        try:
            self._set_adetailer_block(False)
        except Exception as exc:
            print(f"[R Before] Warn: Could not clear ADetailer global guard: {exc}")

        # If a previous manual run removed or disabled ADetailer scripts, restore them now so
        # disabling the manual toggle returns control back to Forge's native behaviour.
        restore_needed = hasattr(self, "_stored_adetailer_scripts") or hasattr(
            self, "disabled_adetailer_scripts"
        )
        if restore_needed:
            try:
                self._restore_early_adetailer_protection(p)
            except Exception as exc:
                print(f"[R Before] Warn: Failed to restore ADetailer pipeline state: {exc}")
        if not getattr(self, "_adetailer_support_enabled", False):
            try:
                self._restore_native_adetailer_scripts(p)
            except Exception as exc:
                print(f"[R Before] Warn: Failed to restore native ADetailer state: {exc}")

    def _restore_native_adetailer_scripts(self, p):
        """Ensure native ADetailer scripts resume running when manual support is disabled."""
        self._adetailer_orch._restore_native_adetailer_scripts(p)

    def _force_enable_adetailer_scripts(self, processing_obj=None):
        """Return the count of ADetailer scripts restored to their original behaviour."""
        return self._adetailer_orch._force_enable_adetailer_scripts(processing_obj)

    def _ensure_native_adetailer_enable_flags(self, processing_obj):
        self._adetailer_orch._ensure_native_adetailer_enable_flags(processing_obj)

    def _force_native_adetailer_execution(self, p, processed):
        if getattr(self, "_adetailer_support_enabled", False):
            return False
        if not self._native_adetailer_requested(p):
            return False
        try:
            if getattr(self, "_native_adetailer_fallback_used", False):
                return False
            if not processed or not getattr(processed, "images", None):
                print("[R Before] Native fallback: processed has no images; skipping ADetailer run")
                return False
            image_list = [img for img in processed.images if img is not None]
            if not image_list:
                print("[R Before] Native fallback: no valid images available for ADetailer")
                return False
            if not self._native_adetailer_detected():
                print(
                    "[R Before] Native fallback: no native ADetailer scripts detected; skipping fallback"
                )
                return False
            print(
                f"[R Before] Native fallback: running manual ADetailer on {len(image_list)} txt2img result(s)"
            )
            self._prepare_processing_for_manual_adetailer(p, processed, image_list)
            self._native_adetailer_fallback_used = True
            original_support = getattr(self, "_adetailer_support_enabled", False)
            original_post_support = getattr(self, "_post_adetailer_enabled", False)
            original_prev_manual = getattr(self, "_manual_adetailer_prev_enabled", False)
            try:
                self._adetailer_support_enabled = True
                self._post_adetailer_enabled = True
                self._manual_adetailer_prev_enabled = True
                ran = self._execute_manual_adetailer(p, processed, image_list)
            finally:
                self._adetailer_support_enabled = original_support
                self._post_adetailer_enabled = original_post_support
                self._manual_adetailer_prev_enabled = original_prev_manual
            if ran:
                print("[R Before] Native fallback: manual ADetailer execution complete")
            else:
                print("[R Before] Native fallback: manual ADetailer execution reported failure")
            return bool(ran)
        except Exception as exc:
            print(f"[R Before] Native fallback: error running manual ADetailer: {exc}")
            return False

    def _native_adetailer_requested(self, processing_obj):
        try:
            args = getattr(processing_obj, "script_args", None)
        except Exception:
            return False
        if not isinstance(args, (list, tuple)) or not args:
            return False
        args_list = list(args)
        runners = []
        runner = getattr(processing_obj, "scripts", None)
        if runner is not None:
            runners.append(runner)
        try:
            import modules.scripts as scripts_module

            for attr in ("scripts_txt2img", "scripts_img2img"):
                global_runner = getattr(scripts_module, attr, None)
                if global_runner is not None and global_runner not in runners:
                    runners.append(global_runner)
        except Exception:
            pass
        candidates = []
        for r in runners:
            for list_attr in ("alwayson_scripts", "scripts"):
                script_list = getattr(r, list_attr, None)
                if script_list:
                    candidates.extend(script_list)
        for script in candidates:
            if not self._is_adetailer_script(script):
                continue
            extracted = self._extract_adetailer_script_args(script, processing_obj)
            sanitized = list(extracted.get("args") or [])
            if sanitized and isinstance(sanitized[0], bool):
                return sanitized[0]
        # Fallback: try first bool in original args
        for value in args_list:
            if isinstance(value, bool):
                return value
        return False

    def _native_adetailer_detected(self):
        try:
            import modules.scripts as scripts_module
        except Exception:
            return False
        for runner_attr in ("scripts_txt2img", "scripts_img2img"):
            runner = getattr(scripts_module, runner_attr, None)
            if not runner:
                continue
            for list_attr in ("alwayson_scripts", "scripts"):
                script_list = getattr(runner, list_attr, None)
                if not script_list:
                    continue
                for script in script_list:
                    if self._is_adetailer_script(script):
                        return True
        return False

    def _handle_adetailer_toggle_change(self, previous_enabled, current_enabled, p):
        if previous_enabled and not current_enabled:
            try:
                self._restore_native_adetailer_scripts(p)
            except Exception as exc:
                print(f"[R Before] Warn: Failed handling ADetailer toggle change: {exc}")

    def postprocess(self, p: StableDiffusionProcessing, processed, *args):
        try:
            # If this generation already finalized, avoid looping
            if getattr(p, "_ranbooru_finalized", False):
                print("[R Post] Already finalized this generation; skipping repeat postprocess")
                return
            # If this call is re-entered during our manual ADetailer run, skip to avoid loops
            if getattr(self.__class__, "_ranbooru_manual_adetailer_active", False):
                print("[R Post] Skipping RanbooruX postprocess during manual ADetailer run")
                return
            # Prevent duplicate img2img runs within the same generation
            if getattr(p, "_ranbooru_img2img_started", False):
                print(
                    "[R Post] Img2Img already started for this generation; skipping duplicate postprocess entry"
                )
                return
            enabled = getattr(self, "_post_enabled", False)
            use_img2img = getattr(self, "_post_use_img2img", False)
            getattr(self, "_post_use_last_img", False)
            crop_center = getattr(self, "_post_crop_center", False)
            use_cache = getattr(self, "_post_use_cache", True)
            use_adetailer = (
                getattr(self, "_post_adetailer_enabled", False) and self._is_adetailer_enabled()
            )

            # Validate essential objects
            if not processed or not hasattr(processed, "images"):
                print("[R Post] Error: Invalid processed object, skipping img2img")
                self._cleanup_after_run(use_cache)
                self._clear_processing_guards(p)
                return

            if not enabled:
                print("[R Post] RanbooruX disabled, skipping img2img")
                self._cleanup_after_run(use_cache)
                self._clear_processing_guards(p)
                return

            if not (
                getattr(self, "run_img2img_pass", False)
                and hasattr(self, "last_img")
                and self.last_img
                and use_img2img
            ):
                fallback_ran = False
                if not use_adetailer and not getattr(self, "_adetailer_support_enabled", False):
                    fallback_ran = self._force_native_adetailer_execution(p, processed)
                if fallback_ran:
                    self._cleanup_after_run(use_cache)
                    self._clear_processing_guards(p)
                    return
                print("[R Post] Img2Img conditions not met, skipping")
                self._cleanup_after_run(use_cache)
                self._clear_processing_guards(p)
                return

        except Exception as e:
            print(f"[R Post] Error in postprocess validation: {e}")
            self._cleanup_after_run(getattr(self, "_post_use_cache", True))
            self._clear_processing_guards(p)
            return

        # Main img2img processing block
        try:
            # Mark as started to avoid re-entrant img2img runs
            try:
                setattr(p, "_ranbooru_img2img_started", True)
            except Exception:
                pass

            if use_adetailer:
                # EARLY PROTECTION: Restore ADetailer scripts that were temporarily disabled during initial pass
                self._restore_early_adetailer_protection(p)
                # CRITICAL: Prepare ADetailer for img2img so it can process the final results
                self._prepare_adetailer_for_img2img(p)
            else:
                print(
                    "[R Post] Manual ADetailer support disabled; skipping ADetailer preparation steps"
                )

            print("[R Post] Starting separate Img2Img run...")
            valid_images = [img for img in self.last_img if img is not None]
            if not valid_images:
                print("[R Post] No valid images for Img2Img.")
                self._cleanup_after_run(use_cache)
                self._clear_processing_guards(p)
                return
            if len(valid_images) < len(self.last_img):
                print(
                    f"[R Post] Warn: Only {len(valid_images)}/{len(self.last_img)} valid. Filling gaps."
                )
                if valid_images:
                    self.last_img = [
                        (img if img is not None else valid_images[0]) for img in self.last_img
                    ]
                else:
                    print("[R Post] No valid images left.")
                    self._cleanup_after_run(use_cache)
                    self._clear_processing_guards(p)
                    return
            target_w, target_h = (
                (p.width, p.height) if crop_center else self.check_orientation(self.last_img[0])
            )
            print(
                f"[R Post] Preparing {len(self.last_img)} images ({'Crop' if crop_center else 'Resize'}) to {target_w}x{target_h} for Img2Img."
            )
            prepared_images = [
                rb_image_ops.resize_image(img, target_w, target_h, cropping=crop_center)
                for img in self.last_img
                if img is not None
            ]
            if not prepared_images:
                print("[R Post] No images left after resize.")
                self._cleanup_after_run(use_cache)
                self._clear_processing_guards(p)
                return
            # Use the original RanbooruX-generated prompts, not the simplified initial prompts
            if hasattr(self, "original_full_prompt") and self.original_full_prompt:
                print(
                    "[R Post] Using original RanbooruX prompts for img2img (not simplified initial prompts)"
                )
                final_prompts = self.original_full_prompt
            else:
                final_prompts = processed.prompt
            final_negative_prompts = processed.negative_prompt
            num_imgs = len(prepared_images)
            final_prompts = rb_img2img_lifecycle.repeat_to_length(final_prompts, num_imgs)
            final_negative_prompts = rb_img2img_lifecycle.repeat_to_length(
                final_negative_prompts,
                num_imgs,
            )
            img2img_width, img2img_height = prepared_images[0].size
            # Process images in batches that match WebUI expectations
            # Use batch_size=1 to ensure compatibility with all configurations
            print(
                f"[R] Processing {len(prepared_images)} images individually to ensure compatibility"
            )

            # Process all prepared images (do not limit by original txt2img batch size)

            print(
                f"[R] Running Img2Img ({len(prepared_images)} images) steps={self.real_steps}, Denoise={self.img2img_denoising}"
            )

            # Process images individually to avoid batch size issues
            all_img2img_results = []
            all_infotexts = []
            last_seed = processed.seed
            last_subseed = processed.subseed

            for i, img in enumerate(prepared_images):
                current_prompt = final_prompts[i] if i < len(final_prompts) else final_prompts[0]
                current_negative = (
                    final_negative_prompts[i]
                    if i < len(final_negative_prompts)
                    else final_negative_prompts[0]
                )

                p_img2img = StableDiffusionProcessingImg2Img(
                    sd_model=shared.sd_model,
                    outpath_samples=shared.opts.outdir_samples
                    or shared.opts.outdir_img2img_samples,
                    outpath_grids=shared.opts.outdir_grids or shared.opts.outdir_img2img_grids,
                    prompt=current_prompt,
                    negative_prompt=current_negative,
                    seed=processed.seed + i,
                    subseed=processed.subseed + i,
                    sampler_name=p.sampler_name,
                    scheduler=getattr(p, "scheduler", None),
                    batch_size=1,
                    n_iter=1,
                    steps=self.real_steps,
                    cfg_scale=p.cfg_scale,
                    width=img2img_width,
                    height=img2img_height,
                    init_images=[img],
                    denoising_strength=self.img2img_denoising,
                )
                # Mark as internal so our before_process performs a minimal seed init instead of blocking
                try:
                    setattr(p_img2img, "_ranbooru_internal_img2img", True)
                except Exception:
                    pass

                # CRITICAL: Explicitly enable saving for img2img pass (was disabled for initial pass)
                p_img2img.do_not_save_samples = False  # Always enable saving for final results
                p_img2img.do_not_save_grid = False  # Always enable grid saving for final results

                # Ensure correct output path for img2img results
                final_outpath = getattr(self, "_img2img_final_outpath_samples", None)
                if final_outpath:
                    p_img2img.outpath_samples = final_outpath
                    print(f"[R Save] Saving img2img result {i+1} to: {final_outpath}")
                else:
                    # Fallback to default img2img output directory
                    p_img2img.outpath_samples = (
                        shared.opts.outdir_img2img_samples or shared.opts.outdir_samples
                    )
                    print(
                        f"[R Save] Saving img2img result {i+1} to default: {p_img2img.outpath_samples}"
                    )

                # Restore original batch size
                final_batch_size = getattr(self, "_img2img_final_batch_size", None)
                if final_batch_size:
                    p_img2img.batch_size = final_batch_size

                print(f"[R] Processing image {i+1}/{len(prepared_images)} individually")
                single_result = process_images(p_img2img)
                all_img2img_results.extend(single_result.images)
                all_infotexts.extend(single_result.infotexts)
                last_seed = single_result.seed
                last_subseed = single_result.subseed

            # CRITICAL: Complete replacement of processed object to force all extensions to see new results
            print(
                "[R Post] Performing COMPLETE processed object replacement for extension compatibility"
            )

            rb_img2img_lifecycle.replace_processed_results(
                processed,
                images=all_img2img_results,
                prompts=final_prompts,
                negative_prompts=final_negative_prompts,
                infotexts=all_infotexts,
                seed=last_seed,
                subseed=last_subseed,
                width=img2img_width,
                height=img2img_height,
            )

            # Force update the main processing result references
            if hasattr(p, "processed_result"):
                p.processed_result = processed
            if hasattr(p, "_processed"):
                p._processed = processed

            adetailer_ran_successfully = False
            if use_adetailer:
                print("[R Post] Attempting manual ADetailer run on img2img results...")
                # Ensure processing object is aligned to our img2img result for ADetailer
                self._prepare_processing_for_manual_adetailer(p, processed, all_img2img_results)
                try:
                    self._set_adetailer_block(False)
                    setattr(self.__class__, "_ranbooru_block_all_adetailer", False)
                    setattr(p, "_ranbooru_skip_initial_adetailer", False)
                    print("[R Post] Unblocked ADetailer guard for manual run")
                except Exception:
                    pass
                try:
                    final_dims = (
                        all_img2img_results[0].size
                        if all_img2img_results and hasattr(all_img2img_results[0], "size")
                        else None
                    )
                    self._install_preview_guard()
                    self._set_preview_guard(True, final_dims, block_all=True)
                except Exception:
                    pass
                adetailer_ran_successfully = self._execute_manual_adetailer(
                    p, processed, all_img2img_results
                )
                if adetailer_ran_successfully:
                    print("[R Post] SUCCESS: ADetailer processed img2img results")
                    all_img2img_results = processed.images.copy()
                    try:
                        setattr(p, "_ranbooru_manual_adetailer_complete", True)
                    except Exception:
                        pass
                else:
                    print(
                        "[R Post] WARN: ADetailer manual run failed - img2img results will be unprocessed by ADetailer"
                    )
            else:
                adetailer_ran_successfully = False
                print(
                    "[R Post] Manual ADetailer support disabled; skipping manual ADetailer execution"
                )

            # Mark processing as complete for other extensions and UI
            setattr(self, "_ranbooru_processing_complete", True)
            if hasattr(self, "_ranbooru_intermediate_results"):
                delattr(self, "_ranbooru_intermediate_results")

            print("[R Post] Img2Img finished.")
            print(
                f"[R Post] Updated processed object with {len(all_img2img_results)} img2img results"
            )
            # DEBUG: Add comprehensive logging to trace what ADetailer will see
            # CRITICAL: Force UI to display our final results
            self._force_ui_update(p, processed, all_img2img_results)

            print(
                "[R Post] RanbooruX processing complete - final results ready for UI and other extensions"
            )
            print(
                f"[R Post DEBUG] Final processed.images count: {len(processed.images) if hasattr(processed, 'images') else 'NO IMAGES ATTR'}"
            )
            if hasattr(processed, "images") and processed.images:
                for i, img in enumerate(processed.images[:3]):  # Show first 3 images
                    if img:
                        print(
                            f"[R Post DEBUG] Image {i}: {type(img)} size={getattr(img, 'size', 'unknown')}"
                        )
                    else:
                        print(f"[R Post DEBUG] Image {i}: None")
            else:
                print("[R Post DEBUG] WARNING: No images in processed.images!")

            # DEBUG: Check all image attributes
            debug_attrs = [
                "images",
                "images_list",
                "output_images",
                "_cached_images",
                "cached_images",
            ]
            for attr in debug_attrs:
                if hasattr(processed, attr):
                    val = getattr(processed, attr)
                    if isinstance(val, list):
                        print(f"[R Post DEBUG] {attr}: list with {len(val)} items")
                    else:
                        print(f"[R Post DEBUG] {attr}: {type(val)}")
                else:
                    print(f"[R Post DEBUG] {attr}: not present")

        except Exception as e:
            print(f"[R Post] Critical error during img2img processing: {e}")
            import traceback

            traceback.print_exc()
            try:
                # Attempt to preserve original images if img2img fails
                if hasattr(self, "last_img") and self.last_img:
                    print("[R Post] Attempting to fallback to original txt2img results")
                else:
                    print("[R Post] No fallback images available")
            except Exception as fallback_error:
                _ranbooru_logger.warning(
                    "Fallback handling failed in postprocess: %s", fallback_error
                )
                print("[R Post] Fallback failed")

        finally:
            if getattr(self, "_log_prompt_sources", False):
                self._log_generation_reference(p)
            # Always cleanup regardless of success or failure
            self._cleanup_after_run(use_cache)
            self._clear_processing_guards(p)

    def _is_adetailer_enabled(self):
        return self._adetailer_orch.is_adetailer_enabled()

    def _set_adetailer_block(self, should_block: bool):
        """Toggle the global guard on patched ADetailer classes"""
        self._adetailer_state.block_all = bool(should_block)
        setattr(self.__class__, "_ranbooru_block_all_adetailer", bool(should_block))
        try:
            if hasattr(self, "_adetailer_classes"):
                for Cls in self._adetailer_classes:
                    try:
                        setattr(Cls, "_ranbooru_should_block", bool(should_block))
                    except Exception:
                        pass
                print(f"[R Post] ADetailer global guard set to {should_block}")
        except Exception as e:
            print(f"[R Post] Error toggling ADetailer global guard: {e}")

    def _reset_script_runner_guards(self):
        """Reset ScriptRunner guards to ensure ADetailer is available for each generation"""
        try:
            print("[R Before] Resetting ScriptRunner guards for new generation")

            # Reset the guard installation flag so guards can be reinstalled if needed
            import modules.scripts

            for runner in [modules.scripts.scripts_txt2img, modules.scripts.scripts_img2img]:
                if hasattr(runner, "_ranbooru_guard_installed"):
                    delattr(runner, "_ranbooru_guard_installed")

            # Clear any cached ADetailer classes
            if hasattr(self, "_adetailer_classes"):
                delattr(self, "_adetailer_classes")

            print("[R Before] ScriptRunner guards reset complete")
        except Exception as e:
            print(f"[R Before] Error resetting ScriptRunner guards: {e}")

    def _extract_adetailer_script_args(self, script, processing_obj):
        """Return sanitized ADetailer arguments derived from the processing object."""

        def _normalize(args):
            if args is None:
                return []
            if isinstance(args, tuple):
                return list(args)
            if isinstance(args, list):
                return list(args)
            return [args]

        def _contains_ad_dict(seq):
            for item in seq:
                if isinstance(item, dict) and any(
                    str(key).startswith("ad_") for key in item.keys()
                ):
                    return True
            return False

        def _extract_ad_dicts(seq):
            return [
                item
                for item in seq
                if isinstance(item, dict) and any(str(key).startswith("ad_") for key in item.keys())
            ]

        all_args = _normalize(getattr(processing_obj, "script_args", None))
        snapshot = getattr(self, "_adetailer_script_args_snapshot", None)

        used_snapshot = False
        if not _contains_ad_dict(all_args) and isinstance(snapshot, (list, tuple)):
            snapshot_norm = _normalize(snapshot)
            if _contains_ad_dict(snapshot_norm):
                all_args = snapshot_norm
                used_snapshot = True

        start_idx = getattr(script, "args_from", None)
        end_idx = getattr(script, "args_to", None)
        if isinstance(start_idx, int) and start_idx < 0:
            start_idx = 0
        if isinstance(end_idx, int) and end_idx < 0:
            end_idx = 0

        if isinstance(start_idx, int) and start_idx < len(all_args):
            slice_start = max(start_idx, 0)
            slice_end = max(end_idx, slice_start) if isinstance(end_idx, int) else len(all_args)
            slice_end = min(slice_end, len(all_args))
        else:
            slice_start = 0
            slice_end = len(all_args)

        subset = all_args[slice_start:slice_end]

        bool_candidates = [item for item in subset if isinstance(item, bool)]
        enable_flag = bool_candidates[0] if bool_candidates else None
        skip_flag = bool_candidates[1] if len(bool_candidates) > 1 else None

        dicts = _extract_ad_dicts(subset)
        fallback_reason = None

        if not dicts and not used_snapshot and isinstance(snapshot, (list, tuple)):
            snapshot_norm = _normalize(snapshot)
            snap_subset = snapshot_norm[slice_start:slice_end]
            dicts = _extract_ad_dicts(snap_subset) or _extract_ad_dicts(snapshot_norm)
            if dicts:
                fallback_reason = "snapshot"
                used_snapshot = True

        if not dicts and _contains_ad_dict(all_args):
            dicts = _extract_ad_dicts(all_args)
            if dicts and fallback_reason is None:
                fallback_reason = "all_args"

        meta = {
            "slice_start": slice_start,
            "slice_end": slice_end,
            "total_args": len(all_args),
            "dict_count": len(dicts),
            "fallback_reason": fallback_reason,
            "used_snapshot": used_snapshot,
        }

        if not dicts:
            return {"args": [], "meta": meta}

        # Manual img2img ADetailer execution must run regardless of persisted UI flags
        # to avoid silently skipping detailing when the extracted enable flag is False.
        enable_flag = True
        # Manual runs should never honour the "skip img2img" style bool.
        skip_flag = False

        # Ensure each tab only runs when it has a valid model
        for idx_dict, ad_dict in enumerate(dicts):
            model_name = str(ad_dict.get("ad_model", "") or "").strip().lower()
            has_model = model_name not in ("", "none")
            if idx_dict == 0 and has_model:
                ad_dict["ad_tab_enable"] = True
            else:
                ad_dict["ad_tab_enable"] = bool(ad_dict.get("ad_tab_enable", False) and has_model)

        sanitized = [enable_flag, skip_flag] + dicts
        return {"args": sanitized, "meta": meta}

    def _manual_adetailer_requires_controlnet(self, script_args):
        """Return True when extracted ADetailer args request ControlNet integration."""
        try:
            for arg in script_args or []:
                if not isinstance(arg, dict):
                    continue
                model_name = str(arg.get("ad_controlnet_model", "") or "").strip().lower()
                if model_name and model_name not in ("none", "passthrough"):
                    return True
        except Exception:
            pass
        return False

    def _images_visibly_different(self, original_image, processed_image):
        """Return True only when pixel content or dimensions actually changed."""
        try:
            if original_image is None or processed_image is None:
                return False

            original_size = getattr(original_image, "size", None)
            processed_size = getattr(processed_image, "size", None)
            if original_size and processed_size and original_size != processed_size:
                return True

            original_compare = original_image
            processed_compare = processed_image

            if hasattr(original_compare, "mode") and original_compare.mode != "RGB":
                original_compare = original_compare.convert("RGB")
            if hasattr(processed_compare, "mode") and processed_compare.mode != "RGB":
                processed_compare = processed_compare.convert("RGB")

            if hasattr(original_compare, "tobytes") and hasattr(processed_compare, "tobytes"):
                return original_compare.tobytes() != processed_compare.tobytes()
        except Exception as compare_exc:
            print(f"[R Post] WARN: Could not compare image pixels: {compare_exc}")

        return False

    def _execute_manual_adetailer(self, p, processed, img2img_results):
        """Run manual ADetailer on img2img results via the deterministic runtime executor."""
        return self._adetailer_orch._execute_manual_adetailer(p, processed, img2img_results)

    def _unpatch_manual_adetailer_overrides(self):
        """Restore any monkey patches applied for manual ADetailer runs."""
        try:
            self._log_patch_event("info", "Starting unpatch of manual ADetailer overrides")
            patch_errors = self._adetailer_patches.uninstall_all()
            if patch_errors:
                print("[R Patch] ADetailer restore warnings: " + "; ".join(patch_errors))
            for attr in (
                "_patched_processed_objects",
                "_patched_adetailer_modules",
                "_patched_conversion_modules",
                "_force_adetailer_images",
            ):
                if hasattr(self, attr):
                    try:
                        delattr(self, attr)
                    except Exception:
                        pass
                if hasattr(self.__class__, attr):
                    try:
                        delattr(self.__class__, attr)
                    except Exception:
                        pass
            try:
                import modules.scripts as _ranbooru_scripts_module

                for runner_attr in ("scripts_txt2img", "scripts_img2img"):
                    runner = getattr(_ranbooru_scripts_module, runner_attr, None)
                    if runner and hasattr(runner, "_ranbooru_guard_installed"):
                        delattr(runner, "_ranbooru_guard_installed")
            except Exception:
                pass
            self._log_patch_event("info", "Completed unpatch of manual ADetailer overrides")
        except Exception as exc:
            self._log_patch_event("warning", f"Failed to unpatch manual ADetailer overrides: {exc}")
            print(f"[R Cleanup] Warn: Failed to unpatch manual ADetailer overrides: {exc}")

    def _is_adetailer_script(self, script):
        """Check if a script is an ADetailer script"""
        return self._adetailer_orch._is_adetailer_script(script)

    def _is_controlnet_script(self, script):
        """Check if a script appears to be a ControlNet script."""
        try:
            if script is None:
                return False
            script_name = (
                script.__class__.__name__.lower()
                if hasattr(script, "__class__")
                else str(script).lower()
            )
            if "controlnet" in script_name:
                return True
            title_attr = getattr(script, "title", None)
            if callable(title_attr):
                try:
                    title_value = str(title_attr()).strip().lower()
                    if "controlnet" in title_value:
                        return True
                except Exception:
                    pass
            return False
        except Exception:
            return False

    def _is_forge_controlnet_script(self, script):
        """Detect Forge's built-in ControlNet script class."""
        try:
            if script is None:
                return False
            cls = getattr(script, "__class__", None)
            class_name = getattr(cls, "__name__", "")
            module_name = getattr(cls, "__module__", "")
            filename = str(getattr(script, "filename", "") or "")
            class_name_l = str(class_name).lower()
            module_name_l = str(module_name).lower()
            filename_l = filename.replace("\\", "/").lower()
            return (
                class_name_l == "controlnetforforgeofficial"
                or "sd_forge_controlnet" in module_name_l
                or "sd_forge_controlnet" in filename_l
            )
        except Exception:
            return False

    @staticmethod
    def _clear_runner_callback_cache(runner):
        """Invalidate ScriptRunner callback cache after script list mutations."""
        try:
            callback_map = getattr(runner, "callback_map", None)
            if isinstance(callback_map, dict):
                callback_map.clear()
        except Exception:
            pass

    @contextmanager
    def _manual_adetailer_script_isolation(
        self, processing_obj, adetailer_script, keep_controlnet: bool = False
    ):
        """Run manual ADetailer with only the selected ADetailer script present in runners."""
        if adetailer_script is None:
            yield
            return

        runners = []
        seen_runner_ids = set()

        def add_runner(runner):
            if runner is None:
                return
            runner_id = id(runner)
            if runner_id in seen_runner_ids:
                return
            seen_runner_ids.add(runner_id)
            runners.append(runner)

        add_runner(getattr(processing_obj, "scripts", None))
        try:
            import modules.scripts as scripts_module

            add_runner(getattr(scripts_module, "scripts_txt2img", None))
            add_runner(getattr(scripts_module, "scripts_img2img", None))
        except Exception:
            pass

        def keep_controlnet_fn(script_item, list_attr):
            if not keep_controlnet or not self._is_controlnet_script(script_item):
                return False
            if list_attr == "scripts":
                return True
            return not self._is_forge_controlnet_script(script_item)

        with ExitStack() as stack:
            for runner in runners:
                stack.enter_context(
                    rb_adetailer_runtime.runner_isolation(
                        runner=runner,
                        adetailer_script=adetailer_script,
                        keep_controlnet_fn=keep_controlnet_fn,
                        keep_controlnet=keep_controlnet,
                    )
                )
            yield

    def _mark_initial_pass(self, p):
        """Mark that we're in initial pass so ADetailer can be intercepted later"""
        self._adetailer_orch._mark_initial_pass(p)

    def _reenable_adetailer_from_previous_generation(self):
        """Re-enable ALL ADetailer scripts that were disabled in the previous generation"""
        self._adetailer_orch._reenable_adetailer_from_previous_generation()

    def _prevent_all_image_saving(self, p, temp_dir):
        """Prevent all possible image saving during initial pass"""
        try:
            print("[R] Implementing comprehensive save prevention for initial pass")
            scope = self._host_scope

            scope.set_attr(p, "do_not_save_samples", True)
            scope.set_attr(p, "do_not_save_grid", True)
            scope.set_attr(p, "save_to_dirs", False)
            scope.set_attr(p, "outpath_samples", temp_dir)
            scope.set_attr(p, "_ranbooru_suppress_all_processing", True)
            scope.set_attr(p, "_ranbooru_initial_pass_only", True)
            print(
                f"[R Save Prevention] Redirected initial pass saves to temp directory: {temp_dir}"
            )
            print(
                "[R Save Prevention] ULTIMATE: Marked initial pass for complete processing suppression"
            )

            # Try to disable any gallery/history saving
            if hasattr(p, "save_images_history"):
                scope.set_attr(p, "save_images_history", False)

            # Disable any extra network saving
            if hasattr(p, "save_samples_dir"):
                scope.set_attr(p, "save_samples_dir", None)

            # Make filename format minimal to prevent accidental saves
            if hasattr(p, "filename_format"):
                scope.set_attr(p, "filename_format", "")

            print("[R] Comprehensive save prevention applied")

        except Exception as e:
            print(f"[R] Error applying save prevention: {e}")

    def _prepare_adetailer_for_img2img(self, p):
        """Prepare ADetailer to run on img2img results"""
        self._adetailer_orch._prepare_adetailer_for_img2img(p)

    def _force_ui_update(self, p, processed, final_results):
        """Force ForgeUI to display our final ADetailer-processed results"""
        try:
            print(f"[R UI] Forcing UI to display {len(final_results)} final results")

            # SAFETY CHECK: Filter out any 640x512 images from final results
            filtered_results = []
            for img in final_results:
                if hasattr(img, "size") and img.size == (640, 512):
                    print("[R UI] BLOCKED 640x512 image from UI display")
                else:
                    filtered_results.append(img)

            if len(filtered_results) != len(final_results):
                print(
                    f"[R UI] Filtered out {len(final_results) - len(filtered_results)} wrong-sized images"
                )
                final_results = filtered_results

            # Method 1: Update all possible UI-related attributes
            ui_attrs = [
                "images",
                "output_images",
                "result_images",
                "final_images",
                "display_images",
                "ui_images",
                "gallery_images",
            ]

            for attr in ui_attrs:
                if hasattr(processed, attr):
                    if isinstance(getattr(processed, attr), list):
                        getattr(processed, attr).clear()
                        getattr(processed, attr).extend(final_results)
                        print(f"[R UI] Updated {attr} for UI")
                    else:
                        setattr(processed, attr, final_results)
                        print(f"[R UI] Set {attr} for UI")

            # Method 2: Try to update WebUI/Gradio state directly
            try:
                import modules.shared as shared_modules

                if hasattr(shared_modules, "state"):
                    # Force UI refresh
                    if hasattr(shared_modules.state, "current_image"):
                        shared_modules.state.current_image = (
                            final_results[0] if final_results else None
                        )
                        print("[R UI] Updated shared.state.current_image")

                    # Update any gallery state
                    if hasattr(shared_modules.state, "gallery_images"):
                        shared_modules.state.gallery_images = final_results
                        print("[R UI] Updated shared.state.gallery_images")

                    # Force UI state update
                    shared_modules.state.need_restart = False  # Prevent restart

            except Exception as e:
                print(f"[R UI] Could not update WebUI state: {e}")

            # Method 3: Try to update processing pipeline UI references
            if hasattr(p, "cached_images"):
                p.cached_images = final_results
                print("[R UI] Updated p.cached_images")

            # Method 4: Force update any Gradio components we can find
            try:
                # This is a bit hacky but should force UI refresh
                processed._ui_force_update = True
                processed._ui_timestamp = __import__("time").time()
                print("[R UI] Added UI force update flags")
            except Exception as ui_update_error:
                _ranbooru_logger.warning(
                    "Unable to add UI force-update flags: %s",
                    rb_http_client.sanitize_exception_text(str(ui_update_error)),
                )

            # Method 5: Update the main result that ForgeUI looks for
            if hasattr(processed, "__dict__"):
                for key, value in processed.__dict__.items():
                    if "result" in key.lower() and isinstance(value, list):
                        value.clear()
                        value.extend(final_results)
                        print(f"[R UI] Updated result attribute: {key}")

            print("[R UI] UI force update complete - ForgeUI should now display final results")

            # Disable preview guard now that correct image is presented
            try:
                self._set_preview_guard(False)
            except Exception:
                pass

        except Exception as e:
            print(f"[R UI] Error forcing UI update: {e}")

    def postprocess_batch(self, p, *args, **kwargs):
        """Ensure the final batch results show img2img instead of txt2img"""
        try:
            if not getattr(self, "_post_enabled", False):
                return
            if not getattr(self, "run_img2img_pass", False):
                return
            if args and hasattr(args[0], "images"):
                self._force_ui_update(p, args[0], args[0].images)
        except Exception as e:
            print(f"[R PostBatch] Error: {e}")

    def process_batch(self, p, *args, **kwargs):
        """Process batch - used to mark initial results as intermediate"""
        try:
            if getattr(self, "run_img2img_pass", False):
                # Mark that we're in a two-pass process
                setattr(self, "_ranbooru_intermediate_results", True)
                print("[R ProcessBatch] Marked results as intermediate - img2img will follow")

        except Exception as e:
            print(f"[R ProcessBatch] Error: {e}")

    def process(self, p, *args):
        """Process method - runs during main processing, can intercept results early"""
        try:
            # This method runs during the main processing phase
            # We can use it to prepare for result interception
            if getattr(self, "run_img2img_pass", False):
                print("[R Process] Preparing for img2img result interception")
                # Mark that we need to intercept results
                setattr(self, "_intercept_results", True)

                if self._is_adetailer_enabled():
                    # EARLY PROTECTION: Disable ADetailer during initial pass
                    self._early_adetailer_protection(p)

                # Set early block flag if we're about to process with img2img
                if hasattr(self, "_ranbooru_manual_adetailer_complete"):
                    setattr(self.__class__, "_ranbooru_block_all_adetailer", True)
                    print("[R Process] Early block flag set - preventing ADetailer execution")

        except Exception as e:
            print(f"[R Process] Error: {e}")

    def _early_adetailer_protection(self, p):
        """Complete ADetailer blocking during initial pass - remove scripts entirely"""
        self._adetailer_orch._early_adetailer_protection(p)

    def _remove_adetailer_from_runner(self, p):
        """Temporarily remove ADetailer scripts from the script runner during initial pass"""
        self._adetailer_orch._remove_adetailer_from_runner(p)

    def _restore_early_adetailer_protection(self, processing_obj=None):
        """Restore ADetailer scripts and flags after an interrupted or completed run."""
        self._adetailer_orch._restore_early_adetailer_protection(processing_obj)

    def process_batch_pre(self, p, *args, **kwargs):
        """Pre-batch processing to set up result interception"""
        try:
            if getattr(self, "run_img2img_pass", False):
                print("[R ProcessBatchPre] Setting up early result interception")
        except Exception as e:
            print(f"[R ProcessBatchPre] Error: {e}")

    @classmethod
    def random_number(self, sorting_order, size):
        global COUNT
        effective_count = COUNT
        if effective_count <= 0:
            print("[R] Warn: COUNT zero in random_number.")
            return []
        if size <= 0:
            return []
        max_index = effective_count
        if sorting_order in ("Score Descending", "Score Ascending"):
            weights = np.arange(1, max_index + 1)
            weights = weights.astype(float)
            if sorting_order == "Score Ascending":
                weights = weights[::-1]
            if weights.sum() == 0:
                weights = np.ones(max_index)
            weights /= weights.sum()
            replace = size > max_index
            try:
                random_indices = np.random.choice(
                    np.arange(max_index), size=size, p=weights, replace=replace
                )
            except ValueError as e:
                print(f"[R] Err weighted choice: {e}. Fallback.")
                random_indices = random.choices(range(max_index), k=size)
        else:
            random_indices = random.choices(range(max_index), k=size)
        return random_indices.tolist() if isinstance(random_indices, np.ndarray) else random_indices

    def use_autotagger(self, model):
        return None

    def _install_scriptrunner_guard(self, p):
        """Wrap p.scripts postprocess and postprocess_image to skip ADetailer when our block flag is active"""
        self._adetailer_orch._install_scriptrunner_guard(p)

    def _prepare_processing_for_manual_adetailer(self, p, processed, img2img_results):
        """Ensure p has correct images, sizes, prompts, and save paths before running ADetailer manually"""
        if not self._is_adetailer_enabled():
            return
        try:
            if not img2img_results:
                return
            # ADetailer 26.x exits early while this initial-pass suppression flag remains set.
            self._clear_manual_adetailer_skip_flags(p)
            # Set init image to the first img2img result
            first_img = img2img_results[0]
            try:
                p.init_images = [first_img]
            except Exception:
                pass
            # Align width/height to the image
            try:
                if hasattr(first_img, "size"):
                    p.width, p.height = first_img.size
            except Exception:
                pass
            # Restore a meaningful prompt (avoid minimal initial-pass prompt)
            try:
                if hasattr(self, "original_full_prompt"):
                    p.prompt = self.original_full_prompt
                elif hasattr(processed, "all_prompts") and processed.all_prompts:
                    p.prompt = processed.all_prompts[0]
            except Exception:
                pass
            # Ensure saving paths are valid for ADetailer internals
            try:
                import modules.shared as shared

                outdir = (
                    getattr(shared.opts, "outdir_img2img_samples", None)
                    or getattr(shared.opts, "outdir_samples", None)
                    or "outputs/img2img-images"
                )
                if not outdir:
                    outdir = "outputs/img2img-images"
                p.outpath_samples = outdir
                # Allow saving final artifacts if extension attempts
                if hasattr(p, "do_not_save_samples"):
                    p.do_not_save_samples = False
                if hasattr(p, "do_not_save_grid"):
                    p.do_not_save_grid = True
                if hasattr(p, "save_to_dirs"):
                    p.save_to_dirs = True
            except Exception:
                # As a last resort, set a default path
                try:
                    p.outpath_samples = "outputs/img2img-images"
                except Exception:
                    pass
        except Exception as e:
            print(f"[R Post] WARN: Could not fully prepare p for manual ADetailer: {e}")

    def _clear_manual_adetailer_skip_flags(self, processing_obj):
        """Clear per-request suppression flags before manually invoking ADetailer."""
        if processing_obj is None:
            return
        for attr in (
            "_ad_disabled",
            "_ranbooru_skip_initial_adetailer",
            "_ranbooru_suppress_all_processing",
            "_ranbooru_initial_pass_only",
        ):
            try:
                setattr(processing_obj, attr, False)
            except Exception:
                pass
        self._adetailer_state.initial_pass_suppressed = False

    def _install_preview_guard(self):
        """Install a guard around shared.state.assign_current_image to block wrong previews"""
        self._adetailer_orch._install_preview_guard()

    def _set_preview_guard(self, enabled: bool, final_dims=None, block_all: bool = False):
        try:
            self.__class__._ranbooru_preview_guard_on = bool(enabled)
            self._adetailer_state.preview_guard_on = bool(enabled)
            if enabled:
                self.__class__._ranbooru_preview_block_all = bool(block_all)
                self._adetailer_state.preview_block_all = bool(block_all)
                self.__class__._ranbooru_preview_block_notice_emitted = False
                if final_dims is not None:
                    self.__class__._ranbooru_final_dims = final_dims
                elif hasattr(self.__class__, "_ranbooru_final_dims"):
                    delattr(self.__class__, "_ranbooru_final_dims")
            else:
                self.__class__._ranbooru_preview_block_all = False
                self._adetailer_state.preview_block_all = False
                if hasattr(self.__class__, "_ranbooru_final_dims"):
                    delattr(self.__class__, "_ranbooru_final_dims")
                if hasattr(self.__class__, "_ranbooru_preview_block_notice_emitted"):
                    delattr(self.__class__, "_ranbooru_preview_block_notice_emitted")
            print(
                f"[R UI] Preview guard set to {enabled} with dims={final_dims}, block_all={block_all}"
            )
        except Exception as e:
            print(f"[R UI] Error setting preview guard: {e}")
