import types
from contextlib import nullcontext

from ranboorux.integrations import adetailer_runtime


class DummyImage:
    def __init__(self, token: str, size=(64, 64)):
        self.token = token
        self.size = size

    def tobytes(self):
        return self.token.encode("utf-8")


def _extract_args(*_args, **_kwargs):
    return {"args": [True, False, {"ad_model": "face_yolov8n.pt", "ad_tab_enable": True}]}


def _build_processed(image):
    return types.SimpleNamespace(images=[image], image=image)


def test_state_reset():
    state = adetailer_runtime.AdetailerRunState(
        block_all=True,
        manual_active=True,
        initial_pass_suppressed=True,
        processing_complete=True,
        preview_guard_on=True,
        preview_block_all=True,
        global_guard_active=True,
        pipeline_blocked=True,
    )

    assert state.is_blocked() is True
    state.reset()

    assert state.block_all is False
    assert state.manual_active is False
    assert state.initial_pass_suppressed is False
    assert state.processing_complete is False
    assert state.preview_guard_on is False
    assert state.preview_block_all is False
    assert state.global_guard_active is False
    assert state.pipeline_blocked is False
    assert state.is_blocked() is False


def test_patch_registry_install_and_uninstall():
    class Target:
        def method(self):
            return "original"

    target = Target()
    registry = adetailer_runtime.PatchRegistry()

    def replacement():
        return "patched"

    registry.install(target, "method", replacement, "unit-test patch")
    assert target.method() == "patched"
    assert registry.is_empty() is False

    registry.uninstall_all()
    assert target.method() == "original"
    assert registry.is_empty() is True


def test_patch_registry_uninstall_is_idempotent():
    target = types.SimpleNamespace(method=lambda: "ok")
    registry = adetailer_runtime.PatchRegistry()
    registry.install(target, "method", lambda: "patched", "idempotent-test")

    registry.uninstall_all()
    registry.uninstall_all()

    assert target.method() == "ok"
    assert registry.is_empty() is True


def test_patch_registry_reports_restore_errors_once():
    class Target:
        block_restore = False

        def method(self):
            return "original"

        def __setattr__(self, name, value):
            if name == "method" and self.block_restore:
                raise RuntimeError("restore blocked")
            super().__setattr__(name, value)

    target = Target()
    registry = adetailer_runtime.PatchRegistry()
    registry.install(target, "method", lambda: "patched", "restore-error-test")
    target.block_restore = True

    errors = registry.uninstall_all()

    assert errors == ["restore-error-test: restore blocked"]
    assert registry.uninstall_all() == []


def test_patch_registry_preserves_later_third_party_patch():
    target = types.SimpleNamespace(method=lambda: "original")
    registry = adetailer_runtime.PatchRegistry()

    def ranbooru_patch():
        return "ranbooru"

    def third_party():
        return "third-party"

    registry.install(target, "method", ranbooru_patch, "ownership-test")
    target.method = third_party

    assert registry.uninstall_all() == []
    assert target.method is third_party
    assert target.method() == "third-party"


def test_runner_snapshot_roundtrip():
    runner = types.SimpleNamespace(
        alwayson_scripts=["a", "b"],
        scripts=["x", "y"],
        callback_map={"k": "v"},
    )

    snapshot = adetailer_runtime.RunnerSnapshot.capture(runner)

    runner.alwayson_scripts = ["changed"]
    runner.scripts = []
    runner.callback_map = {"changed": True}

    snapshot.restore(runner)

    assert runner.alwayson_scripts == ["a", "b"]
    assert runner.scripts == ["x", "y"]
    assert runner.callback_map == {"k": "v"}


def test_runner_snapshot_preserves_later_runner_changes():
    runner = types.SimpleNamespace(
        alwayson_scripts=["ranbooru-filtered"],
        scripts=["ranbooru-filtered"],
        callback_map={},
    )
    snapshot = adetailer_runtime.RunnerSnapshot(
        alwayson_scripts=["original"],
        scripts=["original"],
        callback_map={"original": True},
    )

    runner.alwayson_scripts = ["third-party"]
    runner.scripts = ["third-party"]
    runner.callback_map = {"third-party": True}

    snapshot.restore(
        runner,
        expected_alwayson_scripts=["ranbooru-filtered"],
        expected_scripts=["ranbooru-filtered"],
        expected_callback_map={},
    )

    assert runner.alwayson_scripts == ["third-party"]
    assert runner.scripts == ["third-party"]
    assert runner.callback_map == {"third-party": True}


def test_runner_snapshot_restores_owned_callback_map():
    runner = types.SimpleNamespace(
        alwayson_scripts=["isolated"],
        scripts=["isolated"],
        callback_map={},
    )
    snapshot = adetailer_runtime.RunnerSnapshot(
        alwayson_scripts=["original"],
        scripts=["original"],
        callback_map={"original": True},
    )

    snapshot.restore(
        runner,
        expected_alwayson_scripts=["isolated"],
        expected_scripts=["isolated"],
        expected_callback_map={},
    )

    assert runner.alwayson_scripts == ["original"]
    assert runner.scripts == ["original"]
    assert runner.callback_map == {"original": True}


def test_runner_isolation_restores_owned_callback_map():
    class AfterDetailerScript:
        pass

    class OtherScript:
        pass

    adetailer_script = AfterDetailerScript()
    other_script = OtherScript()
    runner = types.SimpleNamespace(
        alwayson_scripts=[adetailer_script, other_script],
        scripts=[other_script, adetailer_script],
        callback_map={"original": (1, [other_script])},
    )

    with adetailer_runtime.runner_isolation(runner, adetailer_script):
        assert runner.callback_map == {}

    assert runner.callback_map == {"original": (1, [other_script])}


def test_runner_isolation_preserves_later_callback_map():
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

    with adetailer_runtime.runner_isolation(runner, adetailer_script):
        runner.callback_map = {"third-party": (2, [third_party_script])}

    assert runner.callback_map == {"third-party": (2, [third_party_script])}


def test_runner_guard_restores_owned_callback_map():
    class AfterDetailerScript:
        def __init__(self):
            self.calls = 0

        def postprocess(self, *_args, **_kwargs):
            self.calls += 1

    class Runner:
        def __init__(self, adetailer_script):
            self.alwayson_scripts = [adetailer_script]
            self.scripts = [adetailer_script]
            self.callback_map = {"original": (1, [adetailer_script])}

        def postprocess(self, *_args, **_kwargs):
            return "ok"

    adetailer_script = AfterDetailerScript()
    runner = Runner(adetailer_script)
    registry = adetailer_runtime.PatchRegistry()
    adetailer_runtime.install_runner_guard(runner, lambda: True, registry)

    runner.postprocess()

    assert runner.callback_map == {"original": (1, [adetailer_script])}


def test_execute_manual_adetailer_counts_changed_image():
    class AfterDetailerScript:
        def postprocess_image(self, _p, temp_processed, *_args):
            temp_processed.images = [DummyImage(f"{temp_processed.image.token}-ad")]

    state = adetailer_runtime.AdetailerRunState()
    result = adetailer_runtime.execute_manual_adetailer(
        adetailer_scripts=[AfterDetailerScript()],
        images=[DummyImage("img-1")],
        processing_obj=types.SimpleNamespace(),
        run_state=state,
        patch_registry=adetailer_runtime.PatchRegistry(),
        extract_script_args=_extract_args,
        build_processed=_build_processed,
        isolation_factory=lambda _script: nullcontext(),
    )

    assert result.successful_processes == 1
    assert result.images[0].token == "img-1-ad"
    assert state.manual_active is False


def test_execute_manual_adetailer_treats_unchanged_as_noop():
    class AfterDetailerScript:
        def postprocess_image(self, _p, temp_processed, *_args):
            temp_processed.images = [temp_processed.image]

    result = adetailer_runtime.execute_manual_adetailer(
        adetailer_scripts=[AfterDetailerScript()],
        images=[DummyImage("img-1")],
        processing_obj=types.SimpleNamespace(),
        run_state=adetailer_runtime.AdetailerRunState(),
        patch_registry=adetailer_runtime.PatchRegistry(),
        extract_script_args=_extract_args,
        build_processed=_build_processed,
    )

    assert result.successful_processes == 0
    assert result.images[0].token == "img-1"


def test_execute_manual_adetailer_batch_counts_only_changed_images():
    class AfterDetailerScript:
        def postprocess_image(self, _p, temp_processed, *_args):
            token = temp_processed.image.token
            if token == "img-2":
                temp_processed.images = [temp_processed.image]
            else:
                temp_processed.images = [DummyImage(f"{token}-ad")]

    result = adetailer_runtime.execute_manual_adetailer(
        adetailer_scripts=[AfterDetailerScript()],
        images=[DummyImage("img-1"), DummyImage("img-2"), DummyImage("img-3")],
        processing_obj=types.SimpleNamespace(),
        run_state=adetailer_runtime.AdetailerRunState(),
        patch_registry=adetailer_runtime.PatchRegistry(),
        extract_script_args=_extract_args,
        build_processed=_build_processed,
    )

    assert result.successful_processes == 2
    assert [img.token for img in result.images] == ["img-1-ad", "img-2", "img-3-ad"]


def test_execute_manual_adetailer_continues_after_single_image_exception():
    class AfterDetailerScript:
        def postprocess_image(self, _p, temp_processed, *_args):
            if temp_processed.image.token == "img-2":
                raise RuntimeError("simulated failure")
            temp_processed.images = [DummyImage(f"{temp_processed.image.token}-ad")]

    state = adetailer_runtime.AdetailerRunState()
    result = adetailer_runtime.execute_manual_adetailer(
        adetailer_scripts=[AfterDetailerScript()],
        images=[DummyImage("img-1"), DummyImage("img-2"), DummyImage("img-3")],
        processing_obj=types.SimpleNamespace(),
        run_state=state,
        patch_registry=adetailer_runtime.PatchRegistry(),
        extract_script_args=_extract_args,
        build_processed=_build_processed,
    )

    assert result.successful_processes == 2
    assert [img.token for img in result.images] == ["img-1-ad", "img-2", "img-3-ad"]
    assert result.errors == ["AfterDetailerScript image 2: simulated failure"]
    assert state.manual_active is False
