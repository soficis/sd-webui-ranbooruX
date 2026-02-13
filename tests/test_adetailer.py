import logging
import sys
import types


def _make_script():
    import scripts.ranbooru as ranbooru

    return ranbooru.Script()


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
            True,   # skip flag from UI
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
    assert script._manual_adetailer_requires_controlnet(
        [
            True,
            False,
            {"ad_model": "face_yolov8n.pt", "ad_controlnet_model": "None"},
        ]
    ) is False
    assert script._manual_adetailer_requires_controlnet(
        [
            True,
            False,
            {"ad_model": "face_yolov8n.pt", "ad_controlnet_model": "sargezt_xl_depth"},
        ]
    ) is True


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

    with script._manual_adetailer_script_isolation(processing, adetailer_script, keep_controlnet=True):
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

    with script._manual_adetailer_script_isolation(processing, adetailer_script, keep_controlnet=True):
        assert runner.alwayson_scripts == [controlnet_script, adetailer_script]
        assert runner.scripts == [controlnet_script, adetailer_script]

    assert runner.alwayson_scripts == [controlnet_script, adetailer_script, other_script]
    assert runner.scripts == [other_script, controlnet_script, adetailer_script]


def test_manual_adetailer_script_isolation_clears_runner_callback_cache():
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

    assert runner.callback_map == {}


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
