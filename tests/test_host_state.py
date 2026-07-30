import types

from ranboorux.mutation_scope import HostMutationScope, RunContext


def test_host_mutation_scope_restores_changed_and_missing_attrs():
    target = types.SimpleNamespace(existing="before")
    scope = HostMutationScope()

    scope.set_attr(target, "existing", "after")
    scope.set_attr(target, "new_attr", 123)

    assert target.existing == "after"
    assert target.new_attr == 123

    scope.restore()
    scope.restore()

    assert target.existing == "before"
    assert not hasattr(target, "new_attr")


def test_host_mutation_scope_patch_restore_is_ownership_safe():
    target = types.SimpleNamespace(callback=lambda: "original")
    original = target.callback
    scope = HostMutationScope()

    def replacement():
        return "ranbooru"

    def third_party():
        return "third-party"

    scope.patch_attr(target, "callback", replacement)
    target.callback = third_party

    scope.restore()

    assert target.callback is third_party
    assert target.callback() == "third-party"
    assert original() == "original"


def test_run_context_removes_owned_temp_paths(tmp_path):
    owned_dir = tmp_path / "owned"
    owned_dir.mkdir()
    (owned_dir / "file.txt").write_text("data", encoding="utf-8")
    owned_file = tmp_path / "owned.txt"
    owned_file.write_text("data", encoding="utf-8")

    context = RunContext()
    context.own_temp_path(str(owned_dir))
    context.own_temp_path(str(owned_file))

    context.cleanup()

    assert not owned_dir.exists()
    assert not owned_file.exists()
    assert context.cleanup_errors == []
