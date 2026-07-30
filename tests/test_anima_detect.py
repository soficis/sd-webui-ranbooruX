from ranboorux.anima_detect import get_anima_model_info, is_anima_model


class _Obj:
    """Minimal attribute holder for test mocks."""

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


def test_anima_tune_img2img_can_be_disabled(monkeypatch):
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
    opts = RunOptions.from_script_args([object()] * 63 + [False])
    script.options = opts
    script._prepare_img2img_pass(p, use_img2img=True, use_ip=False)

    assert script.img2img_denoising == 0.6  # Default non-anima max cap, not Anima's 0.5 cap
