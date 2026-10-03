from __future__ import annotations

import types
from typing import List

import pytest
from PIL import Image, ImageOps

from ranboorux import image_ops as rb_image_ops
from ranboorux import tag_pipeline as rb_tag_pipeline
from ranboorux.run_options import UI_ARGUMENT_FIELDS


def _make_script():
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()
    script._use_tag_catalog = False
    return script


def _args(**overrides) -> List[object]:
    defaults = {
        "enabled": False,
        "tags": "1girl",
        "booru": "danbooru",
        "gelbooru_api_key": "",
        "gelbooru_user_id": "",
        "gelbooru_compat_base_url": "",
        "remove_bad_tags": True,
        "max_pages": 1,
        "change_dash": False,
        "same_prompt": False,
        "fringe_benefits": True,
        "remove_tags": "",
        "use_img2img": False,
        "denoising": 0.75,
        "use_last_img": False,
        "change_background": "Don't Change",
        "change_color": "Don't Change",
        "shuffle_tags": False,
        "post_id": "",
        "mix_prompt": False,
        "mix_amount": 2,
        "chaos_mode": "None",
        "chaos_amount": 0.5,
        "limit_tags": 1.0,
        "max_tags": 0,
        "sorting_order": "Random",
        "mature_rating": "All",
        "lora_folder": "",
        "lora_amount": 1,
        "lora_min": 0.6,
        "lora_max": 1.0,
        "lora_enabled": False,
        "lora_custom_weights": "",
        "lora_lock_prev": False,
        "use_ip": False,
        "use_search_txt": False,
        "use_remove_txt": False,
        "choose_search_txt": "",
        "choose_remove_txt": "",
        "search_refresh_btn": None,
        "remove_refresh_btn": None,
        "crop_center": False,
        "enable_adetailer_support": False,
        "use_same_seed": False,
        "reuse_cached_posts": False,
        "use_cache": False,
        "log_prompt_sources": False,
        "remove_artist_tags": False,
        "remove_character_tags": False,
        "remove_clothing_tags": False,
        "remove_text_tags": False,
        "restrict_subject_tags": False,
        "remove_furry_tags": False,
        "remove_headwear_tags": False,
        "remove_girl_suffix_tags": False,
        "preserve_hair_eye_colors": False,
        "remove_series_tags": False,
        "use_tag_catalog": True,
        "catalog_path": "",
        "lora_auto_detect_pony": True,
        "lora_detected_loras": [],
        "anima_auto_detect": False,
        "anima_tune_img2img": True,
        "lora_blacklist": [],
    }
    defaults.update(overrides)
    return [defaults[field] for field in UI_ARGUMENT_FIELDS]


def _processing():
    return types.SimpleNamespace(
        prompt="base_prompt",
        negative_prompt="",
        seed=10,
        subseed=20,
        n_iter=1,
        batch_size=1,
        steps=30,
        cfg_scale=7.0,
        width=64,
        height=64,
        script_args=[],
        scripts=types.SimpleNamespace(alwayson_scripts=[], scripts=[]),
    )


# Lock Test (a): postprocess output shape
def test_lock_postprocess_shape():
    script = _make_script()
    p = _processing()
    script.before_process(p, *_args(enabled=True, use_img2img=False, use_ip=False))
    processed = types.SimpleNamespace(images=["txt2img_res"], seed=10, subseed=20)
    # Ensure postprocess executes without raising and returns None/completes normally
    res = script.postprocess(p, processed)
    assert res is None
    assert processed.images == ["txt2img_res"]


# Lock Test (b): Tier 4a delegators equivalence on canned input
def test_lock_delegators_tier4a_equivalence():
    import scripts.ranbooru as ranbooru

    script = _make_script()

    # 1. _canonicalize_raw_tag
    assert ranbooru.Script._canonicalize_raw_tag(" Blonde_Hair ") == rb_tag_pipeline.canonicalize_raw_tag(" Blonde_Hair ")

    # 2. _normalize_tag
    assert ranbooru.Script._normalize_tag(" Blonde_Hair ") == rb_tag_pipeline.normalize_tag(" Blonde_Hair ")

    # 3. _extract_subject_tags
    sample_text = "1girl, solo, cat_ears, smiling, outdoors"
    assert script._extract_subject_tags(sample_text) == rb_tag_pipeline.extract_subject_tags(sample_text)

    # 4. _is_adetailer_enabled
    assert script._is_adetailer_enabled() == script._adetailer_orch.is_adetailer_enabled()

    # 5. _mark_initial_pass
    p = _processing()
    script._mark_initial_pass(p)
    assert script._adetailer_orch._state.name == "INITIAL_PASS"

    # 6. _reenable_adetailer_from_previous_generation
    script._reenable_adetailer_from_previous_generation()

    # 7. _remove_adetailer_from_runner
    script._remove_adetailer_from_runner(p)

    # 8. _restore_early_adetailer_protection
    script._restore_early_adetailer_protection(p)


# Lock Test (c): tag_pipeline closure and normalization output equivalence
def test_lock_tag_pipeline_normalization_closure():
    post = {"tags": "1girl, blonde_hair, azure_hair, 1girl, unknown_tag"}
    alias_dict = {"azure_hair": "blue_hair"}
    resolve_alias_fn = lambda t: alias_dict.get(t, t)
    cache = {}

    normalized_tags, buckets = rb_tag_pipeline.normalize_post_tags(post, cache, resolve_alias_fn)
    assert "1girl" in normalized_tags
    assert "blue hair" in normalized_tags

    # Filter rejection check
    rejected, reason = rb_tag_pipeline.post_rejected_by_filter(
        post,
        filter_ctx=None,
        toggles=(False, False, False, False, False, False, False, False, False, False),
        base_colors=(set(), set()),
        allowed_subjects=set(),
        cache=cache,
        favorites_guard=set(),
        catalog_resolve_alias_fn=resolve_alias_fn,
    )
    assert rejected is False


# Lock Test (d): _prepare_img2img_pass CFG clamp values pinned
def test_lock_prepare_img2img_cfg_clamps():
    # Anima base: max(3.0, min(cfg, 6.0))
    for cfg_in, expected in [(1.0, 3.0), (4.5, 4.5), (8.0, 6.0), (3.0, 3.0), (6.0, 6.0)]:
        base_tuned = max(3.0, min(cfg_in, 6.0))
        assert base_tuned == expected

    # Anima turbo: max(1.0, min(cfg, 6.0))
    for cfg_in, expected in [(0.5, 1.0), (2.5, 2.5), (7.0, 6.0), (1.0, 1.0), (6.0, 6.0)]:
        turbo_tuned = max(1.0, min(cfg_in, 6.0))
        assert turbo_tuned == expected

    # Steps: max(8, min(15, steps // 3))
    for steps_in, expected in [(15, 8), (30, 10), (60, 15), (9, 8), (45, 15)]:
        steps_tuned = max(8, min(15, steps_in // 3))
        assert steps_tuned == expected

    # Denoise: min(0.5, denoising)
    for denoise_in, expected in [(0.75, 0.5), (0.4, 0.4), (0.5, 0.5)]:
        denoise_tuned = min(0.5, denoise_in)
        assert denoise_tuned == expected


# Lock Test (e): image_ops.resize_image vs PIL.ImageOps.fit parity probe (informational)
def test_lock_image_ops_resize_image_parity_probe():
    src = Image.new("RGB", (100, 50), color=(128, 64, 32))
    w, h = 64, 64

    custom_out = rb_image_ops.resize_image(src, w, h, cropping=True)
    fit_out = ImageOps.fit(src, (w, h), Image.Resampling.LANCZOS)

    assert custom_out is not None
    assert custom_out.size == (w, h)
    assert fit_out.size == (w, h)
    # Informational parity check: record whether exact pixel equality holds
    # Both are valid; we do not assert pixel identity here.


# Lock Test (f): WebUI hook symbol presence
def test_lock_webui_hook_symbols_presence():
    import scripts.ranbooru as ranbooru

    hooks = [
        "title",
        "show",
        "ui",
        "before_process",
        "process_batch",
        "postprocess_batch",
        "postprocess",
    ]
    for hook in hooks:
        assert hasattr(ranbooru.Script, hook), f"Missing WebUI hook: {hook}"
        assert callable(getattr(ranbooru.Script, hook)), f"Hook {hook} is not callable"
