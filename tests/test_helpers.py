from host_snapshot import assert_snapshots_equal, snapshot_host_state


class MockScriptRunner:
    def __init__(self, scripts):
        self.scripts = scripts
        self.callback_map = {"on_after": object()}


class MockP:
    def __init__(self):
        self.prompt = "masterpiece, 1girl"
        self.negative_prompt = "low quality"
        self.seed = 42
        self.batch_size = 1
        self.steps = 20
        self.cfg_scale = 7.0
        self.do_not_save_grid = False
        self.do_not_save_samples = False
        self.outpath_grids = "/tmp/grids"
        self.outpath_samples = "/tmp/samples"
        self.script_args = [1, 2, 3]


class MockRequestCache:
    def __init__(self, installed=False):
        class DummyPatcher:
            def __init__(self, is_installed):
                self._installed = is_installed

            def is_installed(self):
                return self._installed

        self.patcher = DummyPatcher(installed)


def test_snapshot_identical():
    p = MockP()
    runner = MockScriptRunner([])

    def dummy_preview():
        return None

    cache = MockRequestCache()

    snap1 = snapshot_host_state(p, runner, dummy_preview, cache)
    snap2 = snapshot_host_state(p, runner, dummy_preview, cache)

    assert_snapshots_equal(snap1, snap2)


def test_snapshot_detects_changed_attribute():
    p = MockP()
    runner = MockScriptRunner([])

    def dummy_preview():
        return None

    cache = MockRequestCache()

    snap1 = snapshot_host_state(p, runner, dummy_preview, cache)
    p.prompt = "new prompt"
    p.steps = 50
    p.do_not_save_grid = True
    snap2 = snapshot_host_state(p, runner, dummy_preview, cache)

    assert snap1 != snap2
    assert snap1["prompt"] == "masterpiece, 1girl"
    assert snap2["prompt"] == "new prompt"
    assert snap1["steps"] == 20
    assert snap2["steps"] == 50
    assert snap1["do_not_save_grid"] is False
    assert snap2["do_not_save_grid"] is True


def test_snapshot_detects_changed_preview_identity():
    p = MockP()
    runner = MockScriptRunner([])

    def preview1():
        return None

    def preview2():
        return None

    cache = MockRequestCache()

    snap1 = snapshot_host_state(p, runner, preview1, cache)
    snap2 = snapshot_host_state(p, runner, preview2, cache)

    assert snap1 != snap2
    assert snap1["preview_method_id"] != snap2["preview_method_id"]


def test_snapshot_detects_changed_runner_scripts_and_callbacks():
    p = MockP()

    class ScriptA:
        pass

    class ScriptB:
        pass

    runner = MockScriptRunner([ScriptA()])
    snap1 = snapshot_host_state(p, runner)

    runner.scripts.append(ScriptB())
    runner.callback_map = {"changed": True}
    snap2 = snapshot_host_state(p, runner)

    assert snap1 != snap2
    assert snap1["script_runner_scripts"] == ["ScriptA"]
    assert snap2["script_runner_scripts"] == ["ScriptA", "ScriptB"]
    assert snap1["callback_map"] != snap2["callback_map"]


def test_snapshot_detects_changed_request_cache_state():
    p = MockP()
    cache1 = MockRequestCache(installed=False)
    cache2 = MockRequestCache(installed=True)

    snap1 = snapshot_host_state(p, request_cache=cache1)
    snap2 = snapshot_host_state(p, request_cache=cache2)

    assert snap1 != snap2
    assert snap1["request_cache_installed"] is False
    assert snap2["request_cache_installed"] is True
