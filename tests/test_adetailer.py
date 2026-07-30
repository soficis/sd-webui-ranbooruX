import logging
import sys
import types


def _make_script():
    import scripts.ranbooru as ranbooru

    return ranbooru.Script()


class DummyImage:
    def __init__(self, token: str, size=(64, 64)):
        self.token = token
        self.size = size
        self.mode = "RGB"

    @property
    def width(self):
        return self.size[0]

    @property
    def height(self):
        return self.size[1]

    def tobytes(self):
        return self.token.encode("utf-8")

    def convert(self, mode):
        return DummyImage(self.token, self.size)


def test_patch_health_check():
    script = _make_script()
    target = types.SimpleNamespace(process=lambda *args, **kwargs: None)
    assert script._verify_patch_target(target, "process")


def test_skip_patch_missing():
    script = _make_script()
    target = types.SimpleNamespace()
    assert not script._verify_patch_target(target, "process")


def test_patches_logged(caplog):
    script = _make_script()
    target = types.SimpleNamespace(process=lambda *args, **kwargs: None)
    with caplog.at_level(logging.INFO, logger="ranboorux"):
        script._verify_patch_target(target, "process")
    assert any("patch target verified" in rec.message.lower() for rec in caplog.records)


def test_patch_lifecycle():
    script = _make_script()

    class Runner:
        def __init__(self):
            self.alwayson_scripts = []
            self.scripts = []

        def postprocess(self, *args, **kwargs):
            return "postprocess"

        def postprocess_image(self, *args, **kwargs):
            return "postprocess_image"

    runner = Runner()
    original_postprocess = runner.postprocess
    original_postprocess_image = runner.postprocess_image
    processing = types.SimpleNamespace(scripts=runner, prompt="test prompt")

    scripts_mod = sys.modules["modules.scripts"]
    scripts_mod.scripts_txt2img = runner
    scripts_mod.scripts_img2img = runner

    script._install_scriptrunner_guard(processing)
    assert runner.postprocess != original_postprocess
    assert runner.postprocess_image != original_postprocess_image

    script._unpatch_manual_adetailer_overrides()
    assert runner.postprocess == original_postprocess
    assert runner.postprocess_image == original_postprocess_image


def test_script_reset_scenario():
    script = _make_script()

    class Runner:
        def __init__(self):
            self.alwayson_scripts = []
            self.scripts = []

        def postprocess(self, *args, **kwargs):
            return "ok"

        def postprocess_image(self, *args, **kwargs):
            return "ok"

    runner = Runner()
    processing = types.SimpleNamespace(scripts=runner, prompt="prompt")
    script._install_scriptrunner_guard(processing)

    # Simulate script list reset by another extension.
    runner.alwayson_scripts = []
    runner.scripts = []

    # Guard should remain installed and not crash when re-entered.
    script._install_scriptrunner_guard(processing)
    assert getattr(runner, "_ranbooru_guard_installed", False)


def test_manual_adetailer_script_isolation_restores_runner_lists():
    script = _make_script()

    class AfterDetailerScript:
        pass

    class ControlNetForForgeOfficial:
        pass

    class OtherScript:
        pass

    adetailer_script = AfterDetailerScript()
    controlnet_script = ControlNetForForgeOfficial()
    other_script = OtherScript()

    runner = types.SimpleNamespace(
        alwayson_scripts=[controlnet_script, adetailer_script, other_script],
        scripts=[other_script, controlnet_script, adetailer_script],
    )
    processing = types.SimpleNamespace(scripts=runner, prompt="prompt")

    scripts_mod = sys.modules["modules.scripts"]
    scripts_mod.scripts_txt2img = runner
    scripts_mod.scripts_img2img = runner

    with script._manual_adetailer_script_isolation(processing, adetailer_script):
        assert runner.alwayson_scripts == [adetailer_script]
        assert runner.scripts == [adetailer_script]

    assert runner.alwayson_scripts == [controlnet_script, adetailer_script, other_script]
    assert runner.scripts == [other_script, controlnet_script, adetailer_script]


def test_extract_adetailer_script_args_forces_manual_enable_flags():
    script = _make_script()

    class AfterDetailerScript:
        args_from = 0
        args_to = 6

    ad_script = AfterDetailerScript()
    processing = types.SimpleNamespace(
        script_args=[
            False,  # global enable from UI (disabled)
            True,  # skip flag from UI
            {
                "ad_model": "face_yolov8n.pt",
                "ad_tab_enable": True,
                "ad_prompt": "",
                "ad_negative_prompt": "",
            },
            {"ad_model": "None", "ad_tab_enable": False},
        ]
    )

    extracted = script._extract_adetailer_script_args(ad_script, processing)
    args = extracted["args"]

    assert args[0] is True
    assert args[1] is False
    assert args[2]["ad_tab_enable"] is True


def test_manual_adetailer_requires_controlnet_detection():
    script = _make_script()
    assert script._manual_adetailer_requires_controlnet([]) is False
    assert (
        script._manual_adetailer_requires_controlnet(
            [
                True,
                False,
                {"ad_model": "face_yolov8n.pt", "ad_controlnet_model": "None"},
            ]
        )
        is False
    )
    assert (
        script._manual_adetailer_requires_controlnet(
            [
                True,
                False,
                {"ad_model": "face_yolov8n.pt", "ad_controlnet_model": "sargezt_xl_depth"},
            ]
        )
        is True
    )


def test_manual_adetailer_script_isolation_can_keep_controlnet():
    script = _make_script()

    class AfterDetailerScript:
        pass

    class ControlNetForForgeOfficial:
        def title(self):
            return "ControlNet"

    class OtherScript:
        pass

    adetailer_script = AfterDetailerScript()
    controlnet_script = ControlNetForForgeOfficial()
    other_script = OtherScript()

    runner = types.SimpleNamespace(
        alwayson_scripts=[controlnet_script, adetailer_script, other_script],
        scripts=[other_script, controlnet_script, adetailer_script],
    )
    processing = types.SimpleNamespace(scripts=runner, prompt="prompt")

    scripts_mod = sys.modules["modules.scripts"]
    scripts_mod.scripts_txt2img = runner
    scripts_mod.scripts_img2img = runner

    with script._manual_adetailer_script_isolation(
        processing, adetailer_script, keep_controlnet=True
    ):
        assert runner.alwayson_scripts == [adetailer_script]
        assert runner.scripts == [controlnet_script, adetailer_script]

    assert runner.alwayson_scripts == [controlnet_script, adetailer_script, other_script]
    assert runner.scripts == [other_script, controlnet_script, adetailer_script]


def test_manual_adetailer_script_isolation_keeps_nonforge_controlnet_alwayson():
    script = _make_script()

    class AfterDetailerScript:
        pass

    class ControlNetScript:
        def title(self):
            return "ControlNet"

    class OtherScript:
        pass

    adetailer_script = AfterDetailerScript()
    controlnet_script = ControlNetScript()
    other_script = OtherScript()

    runner = types.SimpleNamespace(
        alwayson_scripts=[controlnet_script, adetailer_script, other_script],
        scripts=[other_script, controlnet_script, adetailer_script],
    )
    processing = types.SimpleNamespace(scripts=runner, prompt="prompt")

    scripts_mod = sys.modules["modules.scripts"]
    scripts_mod.scripts_txt2img = runner
    scripts_mod.scripts_img2img = runner

    with script._manual_adetailer_script_isolation(
        processing, adetailer_script, keep_controlnet=True
    ):
        assert runner.alwayson_scripts == [controlnet_script, adetailer_script]
        assert runner.scripts == [controlnet_script, adetailer_script]

    assert runner.alwayson_scripts == [controlnet_script, adetailer_script, other_script]
    assert runner.scripts == [other_script, controlnet_script, adetailer_script]


def test_manual_adetailer_script_isolation_restores_runner_callback_cache():
    script = _make_script()

    class AfterDetailerScript:
        pass

    class OtherScript:
        pass

    adetailer_script = AfterDetailerScript()
    other_script = OtherScript()

    runner = types.SimpleNamespace(
        alwayson_scripts=[adetailer_script, other_script],
        scripts=[other_script, adetailer_script],
        callback_map={"script_process_before_every_sampling": (1, [other_script])},
    )
    processing = types.SimpleNamespace(scripts=runner, prompt="prompt")

    scripts_mod = sys.modules["modules.scripts"]
    scripts_mod.scripts_txt2img = runner
    scripts_mod.scripts_img2img = runner

    with script._manual_adetailer_script_isolation(processing, adetailer_script):
        assert runner.callback_map == {}

    assert runner.callback_map == {"script_process_before_every_sampling": (1, [other_script])}


def test_manual_adetailer_script_isolation_preserves_newer_callback_cache():
    script = _make_script()

    class AfterDetailerScript:
        pass

    class OtherScript:
        pass

    adetailer_script = AfterDetailerScript()
    other_script = OtherScript()
    third_party_script = OtherScript()

    runner = types.SimpleNamespace(
        alwayson_scripts=[adetailer_script, other_script],
        scripts=[other_script, adetailer_script],
        callback_map={"original": (1, [other_script])},
    )
    processing = types.SimpleNamespace(scripts=runner, prompt="prompt")

    scripts_mod = sys.modules["modules.scripts"]
    scripts_mod.scripts_txt2img = runner
    scripts_mod.scripts_img2img = runner

    with script._manual_adetailer_script_isolation(processing, adetailer_script):
        runner.callback_map = {"third-party": (2, [third_party_script])}

    assert runner.callback_map == {"third-party": (2, [third_party_script])}


def test_preview_guard_block_all_hides_intermediate_frames():
    script = _make_script()
    shared_mod = sys.modules["modules.shared"]
    assigned_images = []

    def assign_current_image(img):
        assigned_images.append(img)
        return img

    shared_mod.state = types.SimpleNamespace(assign_current_image=assign_current_image)
    script._install_preview_guard()

    preview_img = types.SimpleNamespace(size=(1024, 1024))
    script._set_preview_guard(True, block_all=True)
    shared_mod.state.assign_current_image(preview_img)
    assert assigned_images == []

    script._set_preview_guard(False)
    shared_mod.state.assign_current_image(preview_img)
    assert assigned_images == [preview_img]


def test_cleanup_after_run_turns_preview_guard_off():
    script = _make_script()
    script._set_preview_guard(True, final_dims=(768, 768), block_all=True)

    script._cleanup_after_run(use_cache=True)

    assert getattr(script.__class__, "_ranbooru_preview_guard_on", False) is False
    assert getattr(script.__class__, "_ranbooru_preview_block_all", False) is False


def test_preview_guard_cleanup_preserves_later_callback_replacement():
    script = _make_script()
    shared_mod = sys.modules["modules.shared"]
    assigned_images = []

    def original(img):
        assigned_images.append(("original", img))

    def third_party(img):
        assigned_images.append(("third-party", img))

    shared_mod.state.assign_current_image = original

    script._install_preview_guard()
    installed_wrapper = shared_mod.state.assign_current_image
    assert installed_wrapper is not original

    shared_mod.state.assign_current_image = third_party
    script._cleanup_after_run(use_cache=True)

    assert shared_mod.state.assign_current_image is third_party
    assert not hasattr(shared_mod.state, "_ranbooru_preview_guard_installed")
    assert not hasattr(shared_mod.state, "_ranbooru_preview_guard_wrapper")


def test_initial_pass_suppression_sets_flags_and_blocks_runner_guard():
    script = _make_script()
    script._adetailer_support_enabled = True

    class AfterDetailerScript:
        def __init__(self):
            self.postprocess_calls = 0
            self.postprocess_image_calls = 0

        def postprocess(self, *args, **kwargs):
            self.postprocess_calls += 1
            return True

        def postprocess_image(self, *args, **kwargs):
            self.postprocess_image_calls += 1
            return True

    class Runner:
        def __init__(self, adetailer_script):
            self.alwayson_scripts = [adetailer_script]
            self.scripts = [adetailer_script]

        def postprocess(self, p, processed, *args, **kwargs):
            for script_obj in self.alwayson_scripts:
                if hasattr(script_obj, "postprocess"):
                    script_obj.postprocess(p, processed, *args, **kwargs)
            return "ok"

        def postprocess_image(self, p, processed, *args, **kwargs):
            for script_obj in self.scripts:
                if hasattr(script_obj, "postprocess_image"):
                    script_obj.postprocess_image(p, processed, *args, **kwargs)
            return "ok"

    adetailer_script = AfterDetailerScript()
    runner = Runner(adetailer_script)
    processing = types.SimpleNamespace(
        scripts=runner,
        steps=20,
        prompt="test prompt",
        cfg_scale=7.0,
        batch_size=1,
        do_not_save_samples=False,
        do_not_save_grid=False,
        outpath_samples="outputs",
    )
    processed = types.SimpleNamespace(images=[DummyImage("base")])

    scripts_mod = sys.modules["modules.scripts"]
    scripts_mod.scripts_txt2img = runner
    scripts_mod.scripts_img2img = runner

    script._prepare_img2img_pass(processing, use_img2img=True, use_ip=False)
    script._early_adetailer_protection(processing)

    assert getattr(processing, "_ad_disabled", False) is True
    assert getattr(processing, "_ranbooru_skip_initial_adetailer", False) is True
    assert getattr(processing, "_ranbooru_suppress_all_processing", False) is True
    assert getattr(script.__class__, "_ranbooru_block_all_adetailer", False) is True

    runner.postprocess(processing, processed)
    runner.postprocess_image(processing, processed)

    assert adetailer_script.postprocess_calls == 0
    assert adetailer_script.postprocess_image_calls == 0


def test_img2img_initial_pass_mutations_restore_processing_object(monkeypatch):
    import scripts.ranbooru as ranbooru

    script = _make_script()
    processing = types.SimpleNamespace(
        steps=30,
        prompt="test prompt",
        cfg_scale=7.0,
        batch_size=4,
        do_not_save_samples=False,
        do_not_save_grid=False,
        outpath_samples="outputs/original",
        save_to_dirs=True,
        filename_format="[seed]-[prompt]",
        save_images_history=True,
        save_samples_dir="history",
        scripts=types.SimpleNamespace(alwayson_scripts=[], scripts=[]),
    )
    shared_opts = types.SimpleNamespace(
        save_images="shared-save-images",
        outdir_txt2img_samples="shared-txt2img",
    )
    ranbooru.shared.opts = shared_opts

    monkeypatch.setattr(script, "_install_preview_guard", lambda: None)
    monkeypatch.setattr(script, "_set_preview_guard", lambda *_args, **_kwargs: None)

    script._prepare_img2img_pass(processing, use_img2img=True, use_ip=False)

    assert processing.do_not_save_samples is True
    assert processing.do_not_save_grid is True
    assert processing.save_to_dirs is False
    assert processing.outpath_samples != "outputs/original"
    assert processing.filename_format == ""
    assert processing.save_images_history is False
    assert processing.save_samples_dir is None
    assert getattr(processing, "_ranbooru_suppress_all_processing", False) is True

    script._cleanup_after_run(use_cache=True)

    assert processing.steps == 30
    assert processing.cfg_scale == 7.0
    assert processing.batch_size == 4
    assert processing.do_not_save_samples is False
    assert processing.do_not_save_grid is False
    assert processing.outpath_samples == "outputs/original"
    assert processing.save_to_dirs is True
    assert processing.filename_format == "[seed]-[prompt]"
    assert processing.save_images_history is True
    assert processing.save_samples_dir == "history"
    assert not hasattr(processing, "_ranbooru_suppress_all_processing")
    assert not hasattr(processing, "_ranbooru_initial_pass_only")
    assert shared_opts.save_images == "shared-save-images"
    assert shared_opts.outdir_txt2img_samples == "shared-txt2img"
    assert not hasattr(script, "original_save_images")
    assert not hasattr(script, "original_save_grid")
    assert not hasattr(script, "original_outpath")


def test_guard_blocks_during_suppression():
    script = _make_script()

    class AfterDetailerScript:
        def __init__(self):
            self.calls = 0

        def postprocess(self, *args, **kwargs):
            self.calls += 1

    class Runner:
        def __init__(self, adetailer_script):
            self.alwayson_scripts = [adetailer_script]
            self.scripts = [adetailer_script]

        def postprocess(self, p, processed, *args, **kwargs):
            for script_obj in self.alwayson_scripts:
                if hasattr(script_obj, "postprocess"):
                    script_obj.postprocess(p, processed, *args, **kwargs)
            return "ok"

        def postprocess_image(self, *args, **kwargs):
            return "ok"

    adetailer_script = AfterDetailerScript()
    runner = Runner(adetailer_script)
    processing = types.SimpleNamespace(scripts=runner, prompt="prompt")

    scripts_mod = sys.modules["modules.scripts"]
    scripts_mod.scripts_txt2img = runner
    scripts_mod.scripts_img2img = runner

    script._install_scriptrunner_guard(processing)
    setattr(script.__class__, "_ranbooru_block_all_adetailer", True)
    runner.postprocess(processing, types.SimpleNamespace(images=[]))
    assert adetailer_script.calls == 0


def test_manual_per_image_execution():
    script = _make_script()
    script._adetailer_support_enabled = True

    class AfterDetailerScript:
        args_from = 0
        args_to = 3

        def __init__(self):
            self.calls = []

        def postprocess_image(self, p, temp_processed, *args):
            self.calls.append(temp_processed.image.token)
            temp_processed.image = DummyImage(
                f"{temp_processed.image.token}-ad", temp_processed.image.size
            )
            return True

    adetailer_script = AfterDetailerScript()
    runner = types.SimpleNamespace(
        alwayson_scripts=[adetailer_script],
        scripts=[adetailer_script],
    )
    processing = types.SimpleNamespace(
        scripts=runner,
        script_args=[True, False, {"ad_model": "face_yolov8n.pt", "ad_tab_enable": True}],
        processed=types.SimpleNamespace(images=[]),
    )
    images = [DummyImage("img1"), DummyImage("img2"), DummyImage("img3")]
    processed = types.SimpleNamespace(
        images=list(images),
        prompt="prompt",
        negative_prompt="",
        seed=1,
        subseed=2,
        width=64,
        height=64,
        cfg_scale=7.0,
        steps=20,
    )

    ran = script._execute_manual_adetailer(processing, processed, images)

    assert ran is True
    assert adetailer_script.calls == ["img1", "img2", "img3"]
    assert [img.token for img in processed.images] == ["img1-ad", "img2-ad", "img3-ad"]


def test_manual_execution_clears_adetailer_disable_flag():
    script = _make_script()
    script._adetailer_support_enabled = True

    class AfterDetailerScript:
        args_from = 0
        args_to = 3

        def postprocess_image(self, p, temp_processed, *args):
            if getattr(p, "_ad_disabled", False):
                return True
            temp_processed.image = DummyImage(f"{temp_processed.image.token}-ad")
            return True

    adetailer_script = AfterDetailerScript()
    runner = types.SimpleNamespace(
        alwayson_scripts=[adetailer_script],
        scripts=[adetailer_script],
    )
    processing = types.SimpleNamespace(
        scripts=runner,
        script_args=[True, False, {"ad_model": "face_yolov8n.pt", "ad_tab_enable": True}],
        processed=types.SimpleNamespace(images=[]),
        _ad_disabled=True,
        _ranbooru_skip_initial_adetailer=True,
        _ranbooru_suppress_all_processing=True,
    )
    original = [DummyImage("same-1")]
    processed = types.SimpleNamespace(
        images=list(original),
        prompt="prompt",
        negative_prompt="",
        seed=1,
        subseed=2,
        width=64,
        height=64,
        cfg_scale=7.0,
        steps=20,
    )

    ran = script._execute_manual_adetailer(processing, processed, original)

    assert ran is True
    assert getattr(processing, "_ad_disabled", False) is False
    assert getattr(processing, "_ranbooru_skip_initial_adetailer", False) is False
    assert [img.token for img in processed.images] == ["same-1-ad"]


def test_unchanged_image_noop():
    script = _make_script()
    script._adetailer_support_enabled = True

    class AfterDetailerScript:
        args_from = 0
        args_to = 3

        def postprocess_image(self, p, temp_processed, *args):
            temp_processed.images = [temp_processed.image]
            return True

    adetailer_script = AfterDetailerScript()
    runner = types.SimpleNamespace(
        alwayson_scripts=[adetailer_script],
        scripts=[adetailer_script],
    )
    processing = types.SimpleNamespace(
        scripts=runner,
        script_args=[True, False, {"ad_model": "face_yolov8n.pt", "ad_tab_enable": True}],
        processed=types.SimpleNamespace(images=[]),
    )
    original = [DummyImage("same-1"), DummyImage("same-2")]
    processed = types.SimpleNamespace(
        images=list(original),
        prompt="prompt",
        negative_prompt="",
        seed=1,
        subseed=2,
        width=64,
        height=64,
        cfg_scale=7.0,
        steps=20,
    )

    ran = script._execute_manual_adetailer(processing, processed, original)

    assert ran is False
    assert [img.token for img in processed.images] == ["same-1", "same-2"]


def test_failure_path_cleanup(monkeypatch):
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()
    script._post_enabled = True
    script._post_use_img2img = True
    script._post_use_last_img = False
    script._post_crop_center = False
    script._post_use_cache = True
    script._post_adetailer_enabled = True
    script._adetailer_support_enabled = True
    script.run_img2img_pass = True
    script.real_steps = 10
    script.last_img = [DummyImage("base")]
    script._img2img_final_outpath_samples = "outputs"
    script._img2img_final_batch_size = 1

    class AfterDetailerScript:
        pass

    class Runner:
        def __init__(self):
            self.alwayson_scripts = [AfterDetailerScript()]
            self.scripts = [AfterDetailerScript()]

        def postprocess(self, *args, **kwargs):
            return "postprocess"

        def postprocess_image(self, *args, **kwargs):
            return "postprocess_image"

    runner = Runner()
    processing = types.SimpleNamespace(
        scripts=runner,
        width=64,
        height=64,
        sampler_name="Euler",
        cfg_scale=7.0,
        prompt="prompt",
    )
    processed = types.SimpleNamespace(
        images=[DummyImage("base")],
        prompt="prompt",
        negative_prompt="",
        seed=11,
        subseed=22,
        infotexts=["info"],
        all_prompts=[],
        all_negative_prompts=[],
        all_seeds=[],
        all_subseeds=[],
    )
    processing.processed = types.SimpleNamespace(images=[DummyImage("base")])

    scripts_mod = sys.modules["modules.scripts"]
    scripts_mod.scripts_txt2img = runner
    scripts_mod.scripts_img2img = runner

    pre_guard_postprocess = runner.postprocess
    pre_guard_postprocess_image = runner.postprocess_image
    script._install_scriptrunner_guard(processing)

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
            seed=getattr(proc, "seed", 0),
            subseed=getattr(proc, "subseed", 0),
        ),
    )
    monkeypatch.setattr(ranbooru.rb_image_ops, "resize_image", lambda img, *_args, **_kwargs: img)
    monkeypatch.setattr(script, "_force_ui_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        script, "_prepare_processing_for_manual_adetailer", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        script,
        "_execute_manual_adetailer",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    ranbooru.shared.sd_model = object()
    ranbooru.shared.opts = types.SimpleNamespace(
        outdir_samples="outputs",
        outdir_img2img_samples="outputs",
        outdir_grids="outputs",
        outdir_img2img_grids="outputs",
    )

    script.postprocess(processing, processed)

    assert runner.postprocess == pre_guard_postprocess
    assert runner.postprocess_image == pre_guard_postprocess_image


def test_no_state_leakage():
    script = _make_script()
    p = types.SimpleNamespace()

    setattr(script, "_ranbooru_processing_complete", True)
    setattr(script, "_ranbooru_intermediate_results", True)
    setattr(script, "_native_adetailer_fallback_used", True)
    setattr(script.__class__, "_ranbooru_block_all_adetailer", True)
    setattr(script.__class__, "_adetailer_global_guard_active", True)
    setattr(script.__class__, "_ranbooru_manual_adetailer_active", True)
    script._set_preview_guard(True, final_dims=(64, 64), block_all=True)

    script._reset_adetailer_state_for_run(p)
    script._cleanup_after_run(use_cache=True)

    assert not hasattr(script, "_ranbooru_processing_complete")
    assert not hasattr(script, "_ranbooru_intermediate_results")
    assert not hasattr(script, "_native_adetailer_fallback_used")
    assert getattr(script.__class__, "_ranbooru_block_all_adetailer", False) is False
    assert getattr(script.__class__, "_adetailer_global_guard_active", False) is False
    assert getattr(script.__class__, "_ranbooru_manual_adetailer_active", False) is False
    assert getattr(script.__class__, "_ranbooru_preview_guard_on", False) is False
    assert getattr(script.__class__, "_ranbooru_preview_block_all", False) is False
