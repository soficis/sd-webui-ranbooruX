from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Set, Tuple

# --- Regex Patterns ---
_DASH_UNDERSCORE_RE = re.compile(r"[_\-]+")
_WHITESPACE_RE = re.compile(r"\s+")
_TAG_SPLIT_RE = re.compile(r"[,\s]+")

# --- Constants and Keyword Sets ---
FURRY_CORE_TAGS = {
    "anthro",
    "furry",
    "feral",
    "feral_focus",
    "feral_only",
    "scalie",
    "avian",
    "hooved_animal",
    "digitigrade",
    "taur",
    "mythological_creature",
    "kemono",
    "beastman",
    "beastgirl",
    "beastboy",
    "kemonomimi",
    "fur",
    "fur_focus",
}
_FURRY_CORE_NORMALIZED = {tag.replace("_", " ") for tag in FURRY_CORE_TAGS}

POKEMON_PREFIXES = (
    "pokemon",
    "pikachu",
    "eevee",
    "charizard",
    "mewtwo",
    "gardevoir",
    "lucario",
    "lopunny",
)
_POKEMON_PREFIXES_NORMALIZED = tuple(prefix.replace("_", " ") for prefix in POKEMON_PREFIXES)

ANIMAL_EAR_KEYWORDS = (
    "_ear",
    "animal_ears",
    "beast_ears",
    "cat_ears",
    "dog_ears",
    "fox_ears",
    "bunny_ears",
    "wolf_ears",
    "horse_ears",
    "bear_ears",
)
_ANIMAL_EAR_KEYWORDS_NORMALIZED = tuple(kw.replace("_", " ") for kw in ANIMAL_EAR_KEYWORDS)

HORN_KEYWORDS = (
    "horn",
    "horns",
    "antlers",
    "unicorn_horn",
    "goat_horns",
    "demon_horns",
    "ram_horns",
    "bull_horns",
    "long_horns",
)
_HORN_KEYWORDS_NORMALIZED = tuple(kw.replace("_", " ") for kw in HORN_KEYWORDS)

HEADWEAR_TAGS = {
    "hat",
    "cap",
    "beret",
    "helmet",
    "hood",
    "crown",
    "tiara",
    "headband",
    "hairband",
    "headdress",
    "veil",
    "witch_hat",
    "wizard_hat",
    "top_hat",
    "beanie",
    "goggles",
    "glasses_on_head",
    "sailor_hat",
    "nurse_cap",
    "maid_headdress",
    "pirate_hat",
    "sombrero",
    "bunny_ears_headband",
    "cat_ears_headband",
    "animal_ears_headband",
    "motorcycle_helmet",
    "baseball_cap",
    "bowler_hat",
    "straw_hat",
    "sun_hat",
    "halo",
    "circular_halo",
    "floating_halo",
}
_HEADWEAR_TAGS_NORMALIZED = {tag.replace("_", " ") for tag in HEADWEAR_TAGS}

HALO_TAGS = {"halo", "circular_halo", "ring_halo", "floating_halo", "angelic_halo"}
_HALO_TAGS_NORMALIZED = {tag.replace("_", " ") for tag in HALO_TAGS}

HAIR_COLOR_TAGS = {
    "blonde_hair",
    "brown_hair",
    "black_hair",
    "grey_hair",
    "gray_hair",
    "white_hair",
    "silver_hair",
    "blue_hair",
    "green_hair",
    "red_hair",
    "pink_hair",
    "purple_hair",
    "orange_hair",
    "aqua_hair",
    "magenta_hair",
    "teal_hair",
    "multicolored_hair",
    "gradient_hair",
    "rainbow_hair",
}
_HAIR_COLOR_TAGS_NORMALIZED = {tag.replace("_", " ") for tag in HAIR_COLOR_TAGS}

EYE_COLOR_TAGS = {
    "blue_eyes",
    "green_eyes",
    "red_eyes",
    "brown_eyes",
    "black_eyes",
    "yellow_eyes",
    "amber_eyes",
    "orange_eyes",
    "purple_eyes",
    "pink_eyes",
    "golden_eyes",
    "silver_eyes",
    "grey_eyes",
    "gray_eyes",
    "white_eyes",
    "aqua_eyes",
    "heterochromia",
    "multicolored_eyes",
    "gradient_eyes",
}
_EYE_COLOR_TAGS_NORMALIZED = {tag.replace("_", " ") for tag in EYE_COLOR_TAGS}

SERIES_KEYWORDS = {
    "franchise",
    "series",
    "canon",
    "official_media",
    "gacha_game",
    "anime",
    "manga_franchise",
    "visual_novel",
}
_SERIES_KEYWORDS_NORMALIZED = {tag.replace("_", " ") for tag in SERIES_KEYWORDS}

SERIES_SUFFIXES = ("_series", "_franchise", "_media", "_universe")
_SERIES_SUFFIXES_NORMALIZED = tuple(suffix.replace("_", " ") for suffix in SERIES_SUFFIXES)

_CLOTHING_KEYWORDS = {
    "dress",
    "shirt",
    "skirt",
    "skorts",
    "pants",
    "jeans",
    "shorts",
    "jacket",
    "coat",
    "sweater",
    "hoodie",
    "kimono",
    "robe",
    "uniform",
    "school uniform",
    "sailor uniform",
    "bikini",
    "swimsuit",
    "lingerie",
    "underwear",
    "panties",
    "bra",
    "corset",
    "thighhighs",
    "stockings",
    "socks",
    "gloves",
    "mittens",
    "scarf",
    "cape",
    "apron",
    "armor",
    "bustier",
    "bodysuit",
    "leotard",
    "gown",
    "tuxedo",
    "suit",
    "vest",
    "necktie",
    "bowtie",
    "hat",
    "cap",
    "headband",
    "hairband",
    "headdress",
    "veil",
    "crown",
    "helmet",
    "sandals",
    "boots",
    "shoes",
    "heels",
    "sneakers",
    "flip flops",
    "garter",
    "garter belt",
    "pantyhose",
    "stocking",
    "cloak",
    "cardigan",
    "sleeves",
    "armband",
    "choker",
    "ribbon",
    "bow",
    "shawl",
    "loincloth",
    "loin cloth",
    "tabard",
    "capelet",
    "poncho",
    "overalls",
    "tank top",
    "t-shirt",
    "tee shirt",
    "pajamas",
    "nightgown",
}

_TEXTUAL_TAGS = {
    "text",
    "english text",
    "japanese text",
    "chinese text",
    "korean text",
    "translated",
    "translation",
    "commentary",
    "artist commentary",
    "author commentary",
    "publisher commentary",
    "copyright text",
    "speech bubble",
    "speech bubbles",
    "dialogue",
    "dialog",
    "sound effect",
    "sound effects",
    "comic text",
    "comic panel",
    "subtitle",
    "subtitles",
    "caption",
    "captions",
    "floating text",
    "text focus",
    "text overlay",
    "text background",
    "watermark",
    "watermark text",
    "signature",
    "sign",
    "tagme",
    "written text",
    "scribble",
    "handwritten text",
    "handwriting",
    "text box",
    "thought bubble",
    "thought balloon",
    "logo",
    "logo text",
    "notice",
    "speech bubble text",
}

_SUBJECT_TAGS = {
    "solo",
    "duo",
    "trio",
    "quartet",
    "group",
    "gang",
    "crowd",
    "couple",
    "threesome",
    "foursome",
    "orgy",
    "1girl",
    "2girls",
    "3girls",
    "4girls",
    "1boy",
    "2boys",
    "3boys",
    "4boys",
    "1other",
    "2others",
    "3others",
    "4others",
    "multiple girls",
    "multiple boys",
    "multiple people",
    "multiple others",
    "solo focus",
    "female focus",
    "male focus",
    "mixed group",
    "1female",
    "1male",
    "2females",
    "2males",
    "3females",
    "3males",
    "1person",
    "2people",
    "3people",
    "4people",
}

REMOVAL_SYNONYM_GROUPS_RAW = (
    {"grayscale", "greyscale", "monochrome"},
    {"1girl", "1female", "1woman"},
)


# --- Core Tag Pipeline Functions ---


def split_prompt_tags(prompt: str) -> List[str]:
    if not isinstance(prompt, str):
        return []
    return [tag.strip() for tag in prompt.split(",") if tag.strip()]


def dedupe_keep_order(tags: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(tags))


def remove_repeated_tags(prompt: str) -> str:
    tags = split_prompt_tags(prompt)
    if not tags:
        return ""
    return ",".join(dedupe_keep_order(tags))


def canonicalize_raw_tag(tag: str) -> str:
    if not isinstance(tag, str):
        return ""
    lowered = (tag or "").strip().lower().replace("_", " ")
    return _WHITESPACE_RE.sub(" ", lowered) if lowered else ""


def normalize_tag(tag: str) -> str:
    if not isinstance(tag, str):
        return ""
    normalized = unicodedata.normalize("NFKC", tag).casefold()
    normalized = _DASH_UNDERSCORE_RE.sub(" ", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    if not normalized:
        return ""
    wrapper_pairs = {("(", ")"), ("[", "]"), ("{", "}")}
    while len(normalized) > 2 and (normalized[0], normalized[-1]) in wrapper_pairs:
        normalized = normalized[1:-1].strip()
    return normalized


def build_synonym_lookup(groups_raw: Iterable[Iterable[str]]) -> Dict[str, Set[str]]:
    lookup: Dict[str, Set[str]] = {}
    for group in groups_raw:
        normalized_group = {normalize_tag(tag) for tag in group if normalize_tag(tag)}
        if normalized_group:
            for entry in normalized_group:
                lookup[entry] = normalized_group
    return lookup


def expand_with_synonyms(
    normalized_tag: str, target_set: Set[str], synonym_lookup: Dict[str, Set[str]]
) -> None:
    if not normalized_tag:
        return
    group = synonym_lookup.get(normalized_tag)
    if group:
        target_set.update(group)


def is_furry_tag(tag: str) -> bool:
    normalized = (normalize_tag(tag) or "").strip().lower()
    if not normalized:
        normalized = canonicalize_raw_tag(tag)
    if not normalized:
        return False
    raw_lower = (tag or "").strip().lower()
    if normalized in _FURRY_CORE_NORMALIZED or raw_lower in FURRY_CORE_TAGS:
        return True
    if any(
        normalized.startswith(prefix) or raw_lower.startswith(prefix)
        for prefix in _POKEMON_PREFIXES_NORMALIZED
    ):
        return True
    if any(keyword in normalized for keyword in _ANIMAL_EAR_KEYWORDS_NORMALIZED):
        return True
    if any(keyword in normalized for keyword in _HORN_KEYWORDS_NORMALIZED):
        return True
    return False


def is_headwear_tag(tag: str) -> bool:
    normalized = (normalize_tag(tag) or "").strip().lower()
    if not normalized:
        normalized = canonicalize_raw_tag(tag)
    if not normalized:
        return False
    if normalized in _HEADWEAR_TAGS_NORMALIZED or normalized in _HALO_TAGS_NORMALIZED:
        return True
    if " halo" in normalized or normalized.endswith(" halo"):
        return True
    return False


def is_girl_suffix_tag(tag: str) -> bool:
    normalized = (normalize_tag(tag) or "").strip().lower()
    if not normalized:
        normalized = canonicalize_raw_tag(tag)
    if not normalized:
        return False
    excluded = {
        "girl",
        "1girl",
        "2girls",
        "3girls",
        "4girls",
        "5girls",
        "6+girls",
        "multiple girls",
    }
    if normalized in excluded:
        return False
    if normalized.endswith(" girl") or normalized.endswith("_girl"):
        return True
    return False


def is_hair_color_tag(tag: str, catalog_is_hair_fn=None) -> bool:
    normalized = normalize_tag(tag)
    if catalog_is_hair_fn and normalized:
        if catalog_is_hair_fn(normalized.replace(" ", "_")):
            return True
    return normalized in _HAIR_COLOR_TAGS_NORMALIZED


def is_eye_color_tag(tag: str, catalog_is_eye_fn=None) -> bool:
    normalized = normalize_tag(tag)
    if catalog_is_eye_fn and normalized:
        if catalog_is_eye_fn(normalized.replace(" ", "_")):
            return True
    return normalized in _EYE_COLOR_TAGS_NORMALIZED


def is_series_tag(tag: str, catalog_category_fn=None) -> bool:
    normalized = (normalize_tag(tag) or "").strip().lower()
    if not normalized:
        normalized = canonicalize_raw_tag(tag)
    if not normalized:
        return False
    if catalog_category_fn and catalog_category_fn(normalized.replace(" ", "_")) == 3:
        return True
    if normalized in _SERIES_KEYWORDS_NORMALIZED:
        return True
    if any(normalized.endswith(suffix) for suffix in _SERIES_SUFFIXES_NORMALIZED):
        return True
    return False


def is_clothing_tag(tag: str) -> bool:
    normalized = normalize_tag(tag)
    if not normalized:
        return False
    if (
        normalized.startswith("no ")
        or normalized.startswith("without ")
        or " without " in normalized
        or normalized.startswith("nude")
    ):
        return False
    for keyword in _CLOTHING_KEYWORDS:
        if keyword in normalized:
            return True
    if (
        normalized.endswith(" uniform")
        or normalized.endswith(" outfit")
        or normalized.endswith(" costume")
    ):
        return True
    return False


def is_textual_tag(tag: str, catalog_is_textual_fn=None) -> bool:
    normalized = normalize_tag(tag)
    if not normalized:
        return False
    if catalog_is_textual_fn and catalog_is_textual_fn(normalized.replace(" ", "_")):
        return True
    if normalized in _TEXTUAL_TAGS:
        return True
    if " text" in normalized or normalized.endswith(" text") or normalized.startswith("text "):
        return True
    if (
        "commentary" in normalized
        or "speech bubble" in normalized
        or "dialog" in normalized
        or "subtitle" in normalized
        or "caption" in normalized
    ):
        return True
    if normalized.startswith("translated ") or normalized.startswith("translation "):
        return True
    return False


def is_subject_tag(tag: str) -> bool:
    normalized = normalize_tag(tag)
    return normalized in _SUBJECT_TAGS


def extract_color_tags(text: str) -> Tuple[Set[str], Set[str]]:
    if not text:
        return set(), set()
    hair_tags = set()
    eye_tags = set()
    segments = [seg.strip() for seg in _TAG_SPLIT_RE.split(text) if seg.strip()]
    for seg in segments:
        normalized = normalize_tag(seg)
        if normalized in _HAIR_COLOR_TAGS_NORMALIZED:
            hair_tags.add(normalized)
        elif normalized in _EYE_COLOR_TAGS_NORMALIZED:
            eye_tags.add(normalized)
    return hair_tags, eye_tags


def extract_subject_tags(text: str) -> Set[str]:
    if not text:
        return set()
    tags = [t.strip() for t in _TAG_SPLIT_RE.split(text) if t.strip()]
    return {normalize_tag(t) for t in tags if is_subject_tag(t)}


# --- Filter Context and Matches ---


def build_removal_context(
    removal_raw: Iterable[str],
    favorites_raw: Iterable[str],
    synonym_lookup: Dict[str, Set[str]],
) -> Dict[str, object]:
    exact: Set[str] = set()
    prefix: List[str] = []
    suffix: List[str] = []
    contains: List[str] = []
    regex_objects: List[re.Pattern[str]] = []

    for raw in removal_raw:
        if not isinstance(raw, str):
            continue
        candidate = raw.strip()
        if not candidate:
            continue
        if "*" not in candidate:
            normalized = normalize_tag(candidate)
            if normalized:
                exact.add(normalized)
                expand_with_synonyms(normalized, exact, synonym_lookup)
            continue
        if candidate.startswith("*") and candidate.endswith("*") and candidate.count("*") == 2:
            body = candidate[1:-1]
            normalized = normalize_tag(body)
            if normalized:
                contains.append(normalized)
            continue
        if candidate.endswith("*") and candidate.count("*") == 1:
            body = candidate[:-1]
            normalized = normalize_tag(body)
            if normalized:
                prefix.append(normalized)
            continue
        if candidate.startswith("*") and candidate.count("*") == 1:
            body = candidate[1:]
            normalized = normalize_tag(body)
            if normalized:
                suffix.append(normalized)
            continue

        segments = candidate.split("*")
        pattern_fragments: List[str] = []
        for idx, segment in enumerate(segments):
            if segment:
                normalized_segment = normalize_tag(segment)
                if normalized_segment:
                    pattern_fragments.append(re.escape(normalized_segment))
            if idx < len(segments) - 1:
                pattern_fragments.append(".*")
        pattern_body = "".join(pattern_fragments)
        if pattern_body:
            try:
                regex_objects.append(re.compile(f"^{pattern_body}$"))
            except re.error:
                pass

    contains_set = set(filter(None, contains))
    contains_regex: Optional[re.Pattern[str]] = None
    if len(contains_set) > 50:
        pattern_union = "|".join(re.escape(term) for term in contains_set if term)
        if pattern_union:
            try:
                contains_regex = re.compile(pattern_union)
            except re.error:
                contains_regex = None

    prefix_tuple = tuple(sorted(set(filter(None, prefix))))
    suffix_tuple = tuple(sorted(set(filter(None, suffix))))
    contains_tuple = tuple(sorted(contains_set))

    favorites_exact: Set[str] = set()
    for fav in favorites_raw:
        if not isinstance(fav, str):
            continue
        normalized = normalize_tag(fav)
        if not normalized:
            continue
        favorites_exact.add(normalized)
        expand_with_synonyms(normalized, favorites_exact, synonym_lookup)

    return {
        "exact": frozenset(exact),
        "prefix": prefix_tuple,
        "suffix": suffix_tuple,
        "contains": contains_tuple,
        "contains_regex": contains_regex,
        "regex_objects": tuple(regex_objects),
        "favorites": frozenset(favorites_exact),
    }


def tag_matches_removal(normalized_tag: str, context: Optional[Dict[str, object]]) -> bool:
    if not context or not normalized_tag:
        return False
    favorites: Set[str] = context.get("favorites", frozenset())  # type: ignore
    if normalized_tag in favorites:
        return False
    exact: Set[str] = context.get("exact", frozenset())  # type: ignore
    if normalized_tag in exact:
        return True
    prefix_terms: Tuple[str, ...] = context.get("prefix", tuple())  # type: ignore
    if any(normalized_tag.startswith(term) for term in prefix_terms if term):
        return True
    suffix_terms: Tuple[str, ...] = context.get("suffix", tuple())  # type: ignore
    if any(normalized_tag.endswith(term) for term in suffix_terms if term):
        return True
    contains_regex: Optional[re.Pattern[str]] = context.get("contains_regex")  # type: ignore
    if contains_regex and contains_regex.search(normalized_tag):
        return True
    contains_terms: Tuple[str, ...] = context.get("contains", tuple())  # type: ignore
    if not contains_regex and any(term and term in normalized_tag for term in contains_terms):
        return True
    regex_patterns: Tuple[re.Pattern[str], ...] = context.get("regex_objects", tuple())  # type: ignore
    for pattern in regex_patterns:
        if pattern.fullmatch(normalized_tag):
            return True
    return False


def normalize_post_tags(
    post: Optional[Dict[str, object]],
    cache: Dict[str, str],
    catalog_resolve_alias_fn=None,
) -> Tuple[Set[str], Dict[str, List[str]]]:
    normalized_tags: Set[str] = set()
    buckets: Dict[str, List[str]] = {
        "tags": [],
        "artist_tags": [],
        "character_tags": [],
        "copyright_tags": [],
    }
    if not isinstance(post, dict):
        return normalized_tags, buckets

    raw_tags = post.get("tags")
    tag_list: List[str] = []
    if isinstance(raw_tags, str):
        tag_list = [
            segment.strip() for segment in _TAG_SPLIT_RE.split(raw_tags.strip()) if segment.strip()
        ]
    elif isinstance(raw_tags, dict):
        for value in raw_tags.values():
            if isinstance(value, (list, tuple, set)):
                tag_list.extend(
                    [str(item).strip() for item in value if isinstance(item, str) and item.strip()]
                )
            elif isinstance(value, str) and value.strip():
                tag_list.append(value.strip())
    elif isinstance(raw_tags, (list, tuple, set)):
        tag_list = [
            str(item).strip() for item in raw_tags if isinstance(item, str) and item.strip()
        ]
    buckets["tags"] = tag_list

    for key in ("artist_tags", "character_tags", "copyright_tags"):
        values = post.get(key)
        if isinstance(values, str) and values.strip():
            buckets[key] = [values.strip()]
        elif isinstance(values, (list, tuple, set)):
            buckets[key] = [
                str(item).strip() for item in values if isinstance(item, str) and item.strip()
            ]
        else:
            buckets[key] = []

    def get_normalized_cached(tag_val: str) -> str:
        cached = cache.get(tag_val)
        if cached is not None:
            return cached
        normalized = normalize_tag(tag_val)
        if normalized:
            if catalog_resolve_alias_fn:
                catalog_token = normalized.replace(" ", "_")
                canonical = catalog_resolve_alias_fn(catalog_token)
                if canonical and canonical != catalog_token:
                    normalized = canonical.replace("_", " ")
        cache[tag_val] = normalized
        return normalized

    for key, values in buckets.items():
        cleaned: List[str] = []
        for tag in values:
            if not isinstance(tag, str):
                continue
            cleaned_tag = tag.strip()
            if not cleaned_tag:
                continue
            cleaned.append(cleaned_tag)
            normalized = get_normalized_cached(cleaned_tag)
            if normalized:
                normalized_tags.add(normalized)
        buckets[key] = cleaned

    return normalized_tags, buckets


def post_rejected_by_filter(
    post: Optional[Dict[str, object]],
    *,
    filter_ctx: Optional[Dict[str, object]],
    toggles: Tuple[bool, bool, bool, bool, bool, bool, bool, bool, bool, bool],
    base_colors: Tuple[Set[str], Set[str]],
    allowed_subjects: Set[str],
    cache: Dict[str, str],
    favorites_guard: Set[str],
    catalog_resolve_alias_fn=None,
    catalog_is_textual_fn=None,
    catalog_is_hair_fn=None,
    catalog_is_eye_fn=None,
    catalog_category_fn=None,
) -> Tuple[bool, Optional[Dict[str, object]]]:
    (
        remove_artist,
        remove_character,
        remove_clothing,
        remove_text,
        restrict_subject,
        remove_furry,
        remove_headwear,
        remove_girl_suffix,
        preserve_hair_eye,
        remove_series,
    ) = toggles
    base_hair, base_eye = base_colors
    _, buckets = normalize_post_tags(post, cache, catalog_resolve_alias_fn)
    primary_subject: Optional[str] = None

    def get_normalized_cached(tag_val: str) -> str:
        cached = cache.get(tag_val)
        if cached is not None:
            return cached
        normalized = normalize_tag(tag_val)
        if normalized:
            if catalog_resolve_alias_fn:
                catalog_token = normalized.replace(" ", "_")
                canonical = catalog_resolve_alias_fn(catalog_token)
                if canonical and canonical != catalog_token:
                    normalized = canonical.replace("_", " ")
        cache[tag_val] = normalized
        return normalized

    for bucket_name, tags in buckets.items():
        for raw_tag in tags:
            normalized_tag = get_normalized_cached(raw_tag)
            if normalized_tag and normalized_tag in favorites_guard:
                continue
            canonical_tag = normalized_tag or canonicalize_raw_tag(raw_tag)
            canonical_tag = canonical_tag or ""
            reason_base = {
                "tag": raw_tag,
                "norm": normalized_tag,
                "bucket": bucket_name,
            }

            if remove_artist and (
                bucket_name == "artist_tags"
                or (
                    normalized_tag
                    and (normalized_tag.endswith(" artist") or " drawn by" in normalized_tag)
                )
            ):
                return True, {**reason_base, "rule": "artist"}

            if remove_character and (
                bucket_name == "character_tags"
                or ("(" in raw_tag and ")" in raw_tag and not raw_tag.strip().startswith("("))
                or (
                    normalized_tag
                    and (
                        normalized_tag.endswith(" character")
                        or normalized_tag.endswith(" characters")
                        or normalized_tag.endswith(" series")
                        or normalized_tag.endswith(" franchise")
                    )
                )
            ):
                return True, {**reason_base, "rule": "character"}

            if remove_series and (
                bucket_name == "copyright_tags" or is_series_tag(raw_tag, catalog_category_fn)
            ):
                return True, {**reason_base, "rule": "series"}

            if remove_clothing and is_clothing_tag(raw_tag):
                return True, {**reason_base, "rule": "clothing"}

            if remove_text and is_textual_tag(raw_tag, catalog_is_textual_fn):
                return True, {**reason_base, "rule": "text"}

            if remove_furry and is_furry_tag(raw_tag):
                return True, {**reason_base, "rule": "furry"}

            if remove_headwear and is_headwear_tag(raw_tag):
                return True, {**reason_base, "rule": "headwear"}

            if remove_girl_suffix and is_girl_suffix_tag(raw_tag):
                return True, {**reason_base, "rule": "girl-suffix"}

            if preserve_hair_eye:
                if is_hair_color_tag(raw_tag, catalog_is_hair_fn) and base_hair:
                    if normalized_tag not in base_hair:
                        return True, {**reason_base, "rule": "hair-color-conflict"}
                if is_eye_color_tag(raw_tag, catalog_is_eye_fn) and base_eye:
                    if normalized_tag not in base_eye:
                        return True, {**reason_base, "rule": "eye-color-conflict"}

            if restrict_subject and is_subject_tag(raw_tag):
                subject_norm = normalized_tag or canonical_tag
                if allowed_subjects:
                    if subject_norm not in allowed_subjects:
                        return True, {**reason_base, "rule": "subject-not-allowed"}
                else:
                    if primary_subject is None:
                        primary_subject = subject_norm
                    elif subject_norm != primary_subject:
                        return True, {**reason_base, "rule": "multiple-subjects"}

            if tag_matches_removal(canonical_tag, filter_ctx):
                return True, {**reason_base, "rule": "removal-list"}

    return False, None
