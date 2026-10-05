from ranboorux.anima_detect import get_anima_model_info, is_anima_model


class _Obj:
    pass


def test_is_anima_model_none():
    assert is_anima_model(None) is False


def test_is_anima_model_non_anima():
    obj = _Obj()
    obj.sd_model_checkpoint = "sd_xl_base_1.0.safetensors"
    assert is_anima_model(obj) is False


def test_is_anima_model_filename_detection():
    obj = _Obj()
    obj.sd_model_checkpoint = "anima-base-v1.0.safetensors"
    assert is_anima_model(obj) is True


def test_is_anima_model_class_detection():
    # Class name containing "Anima" -> True (no checkpoint at all)
    obj = type("Anima", (), {})()
    assert is_anima_model(obj) is True


def test_get_anima_model_info_returns_dict():
    info = get_anima_model_info(None)
    assert isinstance(info, dict)
    assert "detected" in info
    assert "method" in info
    assert "model_name" in info


def test_is_anima_model_case_insensitive():
    obj = _Obj()
    obj.sd_model_checkpoint = "Anima-Base-v1.0.safetensors"
    assert is_anima_model(obj) is True


def test_is_anima_model_multiple_attr_paths():
    # Fallback to 'checkpoint' attr
    obj = _Obj()
    obj.checkpoint = "anima-preview3-base.safetensors"
    assert is_anima_model(obj) is True

    # Fallback to 'model_checkpoint' attr
    obj2 = _Obj()
    obj2.model_checkpoint = "anima-aesthetic-v1.0.safetensors"
    assert is_anima_model(obj2) is True


def test_is_anima_model_negative_fixtures():
    """Negative fixtures: substrings of anima like Animate, AnimateDiff, animal must NOT detect as True."""
    for fixture in (
        "Wan2.2-Animate-2-14B.safetensors",
        "AnimateDiff-motion.safetensors",
        "animal_is_fine.safetensors",
    ):
        obj = _Obj()
        obj.sd_model_checkpoint = fixture
        assert is_anima_model(obj) is False, f"Expected False for {fixture}"


def test_is_anima_model_forge_engine_attributes():
    """Forge diffusion engines set sd_model.filename and sd_model.sd_checkpoint_info.filename."""
    # Direct filename on engine
    obj1 = _Obj()
    obj1.filename = "C:/models/checkpoints/anima-base-v1.0.safetensors"
    assert is_anima_model(obj1) is True

    # Via sd_checkpoint_info
    obj2 = _Obj()
    obj2.sd_checkpoint_info = _Obj()
    obj2.sd_checkpoint_info.filename = "D:/Forge/models/Anima-2.9B.safetensors"
    assert is_anima_model(obj2) is True


def test_identifier_ranking():
    """Ranking: model_config > dynamic_args > class_name > filename."""
    from ranboorux.anima_detect import ModelCapabilities

    # 1. model_config takes precedence
    obj1 = _Obj()
    obj1.model_config = type("Anima", (), {"huggingface_repo": "circlestone-labs/Anima"})()
    obj1.filename = "sd_xl_base_1.0.safetensors"  # non-anima filename
    info1 = get_anima_model_info(obj1)
    assert info1["detected"] is True
    assert info1["method"] == "model_config"
    assert isinstance(info1["capabilities"], ModelCapabilities)

    # 2. dynamic_args takes precedence over class_name
    obj2 = _Obj()
    obj2.dynamic_args = _Obj()
    obj2.dynamic_args.anima = True
    info2 = get_anima_model_info(obj2)
    assert info2["detected"] is True
    assert info2["method"] == "dynamic_args"

    # 3. class_name
    obj3 = type("Anima", (), {})()
    info3 = get_anima_model_info(obj3)
    assert info3["detected"] is True
    assert info3["method"] == "class_name"

    # 4. filename
    obj4 = _Obj()
    obj4.filename = "anima-turbo-v1.0.safetensors"
    info4 = get_anima_model_info(obj4)
    assert info4["detected"] is True
    assert info4["method"] == "filename"
    assert info4["variant"] == "turbo"
    assert info4["capabilities"].cfg_range == (1.0, 2.0)


def test_anima_tune_img2img_can_be_disabled():
    import types

    import scripts.ranbooru as ranbooru
    from ranboorux.run_options import RunOptions

    script = ranbooru.Script()
    script._is_anima_model = True
    script.img2img_denoising = 0.8

    p = types.SimpleNamespace(
        prompt="test", steps=30, cfg_scale=7.5, outpath_samples=None, batch_size=1
    )

    # When anima_tune_img2img is False, script.img2img_denoising and p.steps should not be overridden by Anima bounds
    opts = RunOptions.from_script_args([object()] * 63 + [False, 1.0])
    script.options = opts
    script._prepare_img2img_pass(p, use_img2img=True, use_ip=False)

    assert script.img2img_denoising == 0.6  # Default non-anima max cap, not Anima's 0.5 cap


def test_anima_capabilities_snapshot():
    import dataclasses

    from ranboorux.anima_detect import get_capabilities

    expected_negative = (
        "worst quality, low quality, score_1, score_2, score_3, "
        "artist name, blurry, jpeg artifacts, chromatic aberration"
    )

    expected_snapshots = {
        "base": {
            "family": "anima",
            "variant": "base",
            "prompt_style": "booru_tags",
            "emits_score_tags": True,
            "quality_prefix": "masterpiece, best quality, score_7, safe, ",
            "negative_default": expected_negative,
            "cfg_range": (4.0, 5.0),
            "steps_range": (30, 50),
            "detection_method": "none",
        },
        "aesthetic": {
            "family": "anima",
            "variant": "aesthetic",
            "prompt_style": "booru_tags",
            "emits_score_tags": False,
            "quality_prefix": "masterpiece, best quality, safe, ",
            "negative_default": expected_negative,
            "cfg_range": (3.0, 5.0),
            "steps_range": (30, 50),
            "detection_method": "none",
        },
        "turbo": {
            "family": "anima",
            "variant": "turbo",
            "prompt_style": "booru_tags",
            "emits_score_tags": True,
            "quality_prefix": "masterpiece, best quality, score_7, safe, ",
            "negative_default": expected_negative,
            "cfg_range": (1.0, 2.0),
            "steps_range": (8, 12),
            "detection_method": "none",
        },
        "2.9b": {
            "family": "anima",
            "variant": "2.9b",
            "prompt_style": "booru_tags",
            "emits_score_tags": True,
            "quality_prefix": "masterpiece, best quality, score_7, safe, ",
            "negative_default": expected_negative,
            "cfg_range": (4.0, 5.0),
            "steps_range": (30, 50),
            "detection_method": "none",
        },
        "3.8b": {
            "family": "anima",
            "variant": "3.8b",
            "prompt_style": "booru_tags",
            "emits_score_tags": True,
            "quality_prefix": "masterpiece, best quality, score_7, safe, ",
            "negative_default": expected_negative,
            "cfg_range": (4.0, 5.0),
            "steps_range": (30, 50),
            "detection_method": "none",
        },
        "unknown": {
            "family": "unknown",
            "variant": "",
            "prompt_style": "booru_tags",
            "emits_score_tags": False,
            "quality_prefix": "",
            "negative_default": "",
            "cfg_range": (4.0, 8.0),
            "steps_range": (20, 30),
            "detection_method": "none",
        },
    }

    for variant in ("base", "aesthetic", "turbo", "2.9b", "3.8b"):
        caps = get_capabilities("anima", variant, "none")
        assert dataclasses.asdict(caps) == expected_snapshots[variant]

    unknown_caps = get_capabilities("unknown", "", "none")
    assert dataclasses.asdict(unknown_caps) == expected_snapshots["unknown"]


def test_anima_detection_ladder_characterization():
    import types

    import scripts.ranbooru as ranbooru

    # Helper simulating Site 1 (before_process)
    def run_site1(p, shared_obj, script_cls):
        pending_ckpt = None
        if hasattr(p, "override_settings") and isinstance(p.override_settings, dict):
            pending_ckpt = p.override_settings.get("sd_model_checkpoint")
        if not pending_ckpt and hasattr(shared_obj, "opts"):
            pending_ckpt = getattr(shared_obj.opts, "sd_model_checkpoint", None)

        info = None
        if pending_ckpt:
            info = get_anima_model_info(pending_ckpt)
        if not info or not info.get("detected"):
            info = get_anima_model_info(getattr(shared_obj, "sd_model", None))
        if not info or not info.get("detected"):
            info = getattr(script_cls, "_last_loaded_model_info", None)
        if not info:
            info = {"detected": False, "method": "none", "model_name": "", "variant": "base"}
        return info

    # Helper simulating Site 2 (process)
    def run_site2(shared_obj):
        return get_anima_model_info(getattr(shared_obj, "sd_model", None))

    class DummyAnimaModel:
        def __init__(self, filename="anima-base.safetensors"):
            self.filename = filename

    # Case 1: pending in override_settings
    p1 = types.SimpleNamespace(
        override_settings={"sd_model_checkpoint": "anima-aesthetic.safetensors"}
    )
    s1_res = run_site1(p1, types.SimpleNamespace(opts=None, sd_model=None), ranbooru.Script)
    assert s1_res["detected"] is True
    assert s1_res["variant"] == "aesthetic"

    # Case 2: pending in shared.opts
    p2 = types.SimpleNamespace()
    opts2 = types.SimpleNamespace(sd_model_checkpoint="anima-turbo.safetensors")
    s2_res = run_site1(p2, types.SimpleNamespace(opts=opts2, sd_model=None), ranbooru.Script)
    assert s2_res["detected"] is True
    assert s2_res["variant"] == "turbo"

    # Case 3: shared.sd_model loaded (Site 1 & Site 2 both detect)
    anima_model = DummyAnimaModel("anima-2.9b.safetensors")
    shared_case3 = types.SimpleNamespace(opts=None, sd_model=anima_model)
    res_site1_case3 = run_site1(types.SimpleNamespace(), shared_case3, ranbooru.Script)
    res_site2_case3 = run_site2(shared_case3)
    assert res_site1_case3["detected"] is True
    assert res_site2_case3["detected"] is True
    assert res_site1_case3["variant"] == "2.9b"
    assert res_site2_case3["variant"] == "2.9b"

    # Case 4: _last_loaded_model_info fallback
    cached_info = get_anima_model_info("anima-3.8b.safetensors")
    ranbooru.Script._last_loaded_model_info = cached_info
    s4_res = run_site1(
        types.SimpleNamespace(), types.SimpleNamespace(opts=None, sd_model=None), ranbooru.Script
    )
    assert s4_res["detected"] is True
    assert s4_res["variant"] == "3.8b"
    ranbooru.Script._last_loaded_model_info = None

    # Case 5: all non-anima
    s5_res = run_site1(
        types.SimpleNamespace(), types.SimpleNamespace(opts=None, sd_model=None), ranbooru.Script
    )
    assert s5_res["detected"] is False


def test_script_detect_anima_unified_method():
    import types

    from modules import shared

    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()

    # When pending checkpoint is an anima model
    p = types.SimpleNamespace(
        override_settings={"sd_model_checkpoint": "anima-aesthetic.safetensors"}
    )
    shared.opts = types.SimpleNamespace()
    shared.sd_model = None

    info = script._detect_anima(p=p)
    assert info["detected"] is True
    assert script._is_anima_model is True
    assert script._anima_model_variant == "aesthetic"
    assert script._anima_capabilities is not None

    # When model is non-anima
    p_non = types.SimpleNamespace(
        override_settings={"sd_model_checkpoint": "sdxl_base.safetensors"}
    )
    info_non = script._detect_anima(p=p_non)
    assert info_non["detected"] is False
    assert script._is_anima_model is False
    assert script._anima_model_variant == "base"
