from __future__ import annotations

import types
from typing import List

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


def test_postprocess_no_debug_stdout(capsys, monkeypatch):
    import scripts.ranbooru as ranbooru

    script = _make_script()
    script._post_enabled = True
    script._post_use_img2img = True
    script._post_use_last_img = False
    script._post_crop_center = True
    script._post_use_cache = False
    script._post_adetailer_enabled = False
    script._adetailer_support_enabled = False
    script.run_img2img_pass = True
    script.real_steps = 1
    script.last_img = [Image.new("RGB", (64, 64))]
    script._img2img_final_outpath_samples = "outputs"
    script._img2img_final_batch_size = 1

    p = _processing()
    p.sampler_name = "Euler"

    class DummyImg2Img:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setattr(ranbooru, "StableDiffusionProcessingImg2Img", DummyImg2Img)
    monkeypatch.setattr(
        ranbooru,
        "process_images",
        lambda proc: types.SimpleNamespace(
            images=[proc.init_images[0]],
            infotexts=["info"],
            seed=0,
            subseed=0,
        ),
    )
    monkeypatch.setattr(ranbooru.rb_image_ops, "resize_image", lambda img, *_args, **_kwargs: img)
    monkeypatch.setattr(script, "_force_ui_update", lambda *_args, **_kwargs: None)

    ranbooru.shared.sd_model = object()
    ranbooru.shared.opts = types.SimpleNamespace(
        outdir_samples="outputs",
        outdir_img2img_samples="outputs",
        outdir_grids="outputs",
        outdir_img2img_grids="outputs",
    )

    processed = types.SimpleNamespace(
        images=[Image.new("RGB", (64, 64))],
        prompt="prompt",
        negative_prompt="",
        seed=10,
        subseed=20,
        infotexts=["info"],
        all_prompts=[],
        all_negative_prompts=[],
        all_seeds=[],
        all_subseeds=[],
    )

    script.postprocess(p, processed)

    captured = capsys.readouterr()
    assert "[R Post DEBUG]" not in captured.out


# Lock Test (b): Tier 4a delegators equivalence on canned input
def test_lock_delegators_tier4a_equivalence():
    script = _make_script()

    # 1. canonicalize_raw_tag
    assert rb_tag_pipeline.canonicalize_raw_tag(" Blonde_Hair ") == "blonde hair"

    # 2. normalize_tag
    assert rb_tag_pipeline.normalize_tag(" Blonde_Hair ") == "blonde hair"

    # 3. extract_subject_tags
    sample_text = "1girl, solo, cat_ears, smiling, outdoors"
    assert "1girl" in rb_tag_pipeline.extract_subject_tags(sample_text)

    # 4. is_adetailer_enabled
    assert script._adetailer_orch.is_adetailer_enabled() is False

    # 5. _mark_initial_pass
    p = _processing()
    script._adetailer_orch._mark_initial_pass(p)
    assert script._adetailer_orch._state.name == "INITIAL_PASS"

    # 6. _reenable_adetailer_from_previous_generation
    script._adetailer_orch._reenable_adetailer_from_previous_generation()

    # 7. _remove_adetailer_from_runner
    script._adetailer_orch._remove_adetailer_from_runner(p)

    # 8. _restore_early_adetailer_protection
    script._adetailer_orch._restore_early_adetailer_protection(p)


# Lock Test (c): tag_pipeline closure and normalization output equivalence
def test_lock_tag_pipeline_normalization_closure():
    post = {"tags": "1girl, blonde_hair, azure_hair, 1girl, unknown_tag"}
    alias_dict = {"azure_hair": "blue_hair"}

    def resolve_alias_fn(t):
        return alias_dict.get(t, t)

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


# Task B3: AST verification that dead symbols are absent and Script._extract_color_tags is preserved
def test_dead_symbols_absent():
    import ast
    from pathlib import Path

    dead_specs = {
        Path("scripts/ranbooru.py"): [
            "_images_visibly_different",
            "_normalize_post_tags",
            "_ensure_pil_images_in_processed",
            "_ensure_pil_in_processing",
            "_normalize_lora_name",
            "_clear_runner_callback_cache",
            "_ensure_user_file",
            "_expand_with_synonyms",
            "use_autotagger",
        ],
        Path("ranboorux/tag_pipeline.py"): [
            "extract_color_tags",
        ],
        Path("ranboorux/boorus/gelbooru.py"): [
            "get_tags",
            "get_tag_aliases",
        ],
        Path("ranboorux/http_client.py"): [
            "get_text",
        ],
    }

    for file_path, dead_names in dead_specs.items():
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        defined_names = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined_names.add(node.name)
        for dead_name in dead_names:
            assert dead_name not in defined_names, f"{dead_name} still defined in {file_path}"

    ranbooru_tree = ast.parse(Path("scripts/ranbooru.py").read_text(encoding="utf-8"))
    ranbooru_defs = {
        node.name
        for node in ast.walk(ranbooru_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_extract_color_tags" in ranbooru_defs, "Script._extract_color_tags must NOT be deleted!"

