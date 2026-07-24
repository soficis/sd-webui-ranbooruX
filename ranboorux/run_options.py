from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

UI_ARGUMENT_FIELDS: Tuple[str, ...] = (
    "enabled",
    "tags",
    "booru",
    "gelbooru_api_key",
    "gelbooru_user_id",
    "gelbooru_compat_base_url",
    "remove_bad_tags",
    "max_pages",
    "change_dash",
    "same_prompt",
    "fringe_benefits",
    "remove_tags",
    "use_img2img",
    "denoising",
    "use_last_img",
    "change_background",
    "change_color",
    "shuffle_tags",
    "post_id",
    "mix_prompt",
    "mix_amount",
    "chaos_mode",
    "chaos_amount",
    "limit_tags",
    "max_tags",
    "sorting_order",
    "mature_rating",
    "lora_folder",
    "lora_amount",
    "lora_min",
    "lora_max",
    "lora_enabled",
    "lora_custom_weights",
    "lora_lock_prev",
    "use_ip",
    "use_search_txt",
    "use_remove_txt",
    "choose_search_txt",
    "choose_remove_txt",
    "search_refresh_btn",
    "remove_refresh_btn",
    "crop_center",
    "enable_adetailer_support",
    "use_same_seed",
    "reuse_cached_posts",
    "use_cache",
    "log_prompt_sources",
    "remove_artist_tags",
    "remove_character_tags",
    "remove_clothing_tags",
    "remove_text_tags",
    "restrict_subject_tags",
    "remove_furry_tags",
    "remove_headwear_tags",
    "remove_girl_suffix_tags",
    "preserve_hair_eye_colors",
    "remove_series_tags",
    "use_tag_catalog",
    "catalog_path",
    "lora_auto_detect_pony",
    "lora_detected_loras",
    "lora_blacklist",
)


@dataclass(frozen=True)
class GelbooruOptions:
    api_key: object
    user_id: object
    compat_base_url: object
    fringe_benefits: object


@dataclass(frozen=True)
class ImageWorkflowOptions:
    use_img2img: object
    denoising: object
    use_last_img: object
    use_ip: object
    crop_center: object
    enable_adetailer_support: object
    use_same_seed: object
    reuse_cached_posts: object
    use_cache: object


@dataclass(frozen=True)
class TagFilterOptions:
    remove_bad_tags: object
    remove_tags: object
    change_background: object
    change_color: object
    remove_artist_tags: object
    remove_character_tags: object
    remove_clothing_tags: object
    remove_text_tags: object
    restrict_subject_tags: object
    remove_furry_tags: object
    remove_headwear_tags: object
    remove_girl_suffix_tags: object
    preserve_hair_eye_colors: object
    remove_series_tags: object
    use_tag_catalog: object
    catalog_path: object


@dataclass(frozen=True)
class LoranadoOptions:
    folder: object
    amount: object
    minimum_weight: object
    maximum_weight: object
    enabled: object
    custom_weights: object
    lock_previous: object
    auto_detect_pony: object
    detected_loras: object
    blacklist: object


@dataclass(frozen=True)
class RunOptions:
    enabled: object
    tags: object
    booru: object
    gelbooru_api_key: object
    gelbooru_user_id: object
    gelbooru_compat_base_url: object
    remove_bad_tags: object
    max_pages: object
    change_dash: object
    same_prompt: object
    fringe_benefits: object
    remove_tags: object
    use_img2img: object
    denoising: object
    use_last_img: object
    change_background: object
    change_color: object
    shuffle_tags: object
    post_id: object
    mix_prompt: object
    mix_amount: object
    chaos_mode: object
    chaos_amount: object
    limit_tags: object
    max_tags: object
    sorting_order: object
    mature_rating: object
    lora_folder: object
    lora_amount: object
    lora_min: object
    lora_max: object
    lora_enabled: object
    lora_custom_weights: object
    lora_lock_prev: object
    use_ip: object
    use_search_txt: object
    use_remove_txt: object
    choose_search_txt: object
    choose_remove_txt: object
    search_refresh_btn: object
    remove_refresh_btn: object
    crop_center: object
    enable_adetailer_support: object
    use_same_seed: object
    reuse_cached_posts: object
    use_cache: object
    log_prompt_sources: object
    remove_artist_tags: object
    remove_character_tags: object
    remove_clothing_tags: object
    remove_text_tags: object
    restrict_subject_tags: object
    remove_furry_tags: object
    remove_headwear_tags: object
    remove_girl_suffix_tags: object
    preserve_hair_eye_colors: object
    remove_series_tags: object
    use_tag_catalog: object
    catalog_path: object
    lora_auto_detect_pony: object
    lora_detected_loras: object
    lora_blacklist: object

    @classmethod
    def from_script_args(cls, args: Sequence[object]) -> "RunOptions":
        values = list(args)
        expected = len(UI_ARGUMENT_FIELDS)
        if len(values) != expected:
            raise ValueError(f"Expected {expected} RanbooruX script args, got {len(values)}")
        return cls(**dict(zip(UI_ARGUMENT_FIELDS, values)))

    def as_dict(self) -> Dict[str, object]:
        return {field: getattr(self, field) for field in UI_ARGUMENT_FIELDS}

    @property
    def gelbooru(self) -> GelbooruOptions:
        return GelbooruOptions(
            api_key=self.gelbooru_api_key,
            user_id=self.gelbooru_user_id,
            compat_base_url=self.gelbooru_compat_base_url,
            fringe_benefits=self.fringe_benefits,
        )

    @property
    def image_workflow(self) -> ImageWorkflowOptions:
        return ImageWorkflowOptions(
            use_img2img=self.use_img2img,
            denoising=self.denoising,
            use_last_img=self.use_last_img,
            use_ip=self.use_ip,
            crop_center=self.crop_center,
            enable_adetailer_support=self.enable_adetailer_support,
            use_same_seed=self.use_same_seed,
            reuse_cached_posts=self.reuse_cached_posts,
            use_cache=self.use_cache,
        )

    @property
    def tag_filters(self) -> TagFilterOptions:
        return TagFilterOptions(
            remove_bad_tags=self.remove_bad_tags,
            remove_tags=self.remove_tags,
            change_background=self.change_background,
            change_color=self.change_color,
            remove_artist_tags=self.remove_artist_tags,
            remove_character_tags=self.remove_character_tags,
            remove_clothing_tags=self.remove_clothing_tags,
            remove_text_tags=self.remove_text_tags,
            restrict_subject_tags=self.restrict_subject_tags,
            remove_furry_tags=self.remove_furry_tags,
            remove_headwear_tags=self.remove_headwear_tags,
            remove_girl_suffix_tags=self.remove_girl_suffix_tags,
            preserve_hair_eye_colors=self.preserve_hair_eye_colors,
            remove_series_tags=self.remove_series_tags,
            use_tag_catalog=self.use_tag_catalog,
            catalog_path=self.catalog_path,
        )

    @property
    def loranado(self) -> LoranadoOptions:
        return LoranadoOptions(
            folder=self.lora_folder,
            amount=self.lora_amount,
            minimum_weight=self.lora_min,
            maximum_weight=self.lora_max,
            enabled=self.lora_enabled,
            custom_weights=self.lora_custom_weights,
            lock_previous=self.lora_lock_prev,
            auto_detect_pony=self.lora_auto_detect_pony,
            detected_loras=self.lora_detected_loras,
            blacklist=self.lora_blacklist,
        )


@dataclass(frozen=True)
class RunComponents:
    components: Mapping[str, object]

    @classmethod
    def from_sequence(cls, values: Sequence[object]) -> "RunComponents":
        expected = len(UI_ARGUMENT_FIELDS)
        if len(values) != expected:
            raise ValueError(f"Expected {expected} RanbooruX UI components, got {len(values)}")
        return cls(dict(zip(UI_ARGUMENT_FIELDS, values)))

    def script_args(self) -> List[object]:
        missing = [field for field in UI_ARGUMENT_FIELDS if field not in self.components]
        if missing:
            raise ValueError(f"Missing RanbooruX components: {', '.join(missing)}")
        return [self.components[field] for field in UI_ARGUMENT_FIELDS]


def assert_known_fields(fields: Iterable[str]) -> None:
    incoming = tuple(fields)
    if incoming != UI_ARGUMENT_FIELDS:
        raise ValueError("RanbooruX UI argument fields do not match the authoritative order")
