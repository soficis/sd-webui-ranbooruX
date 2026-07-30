def snapshot_host_state(p, script_runner=None, preview_method=None, request_cache=None):
    return {
        "prompt": getattr(p, "prompt", None),
        "negative_prompt": getattr(p, "negative_prompt", None),
        "seed": getattr(p, "seed", None),
        "batch_size": getattr(p, "batch_size", None),
        "steps": getattr(p, "steps", None),
        "cfg_scale": getattr(p, "cfg_scale", None),
        "do_not_save_grid": getattr(p, "do_not_save_grid", None),
        "do_not_save_samples": getattr(p, "do_not_save_samples", None),
        "outpath_grids": getattr(p, "outpath_grids", None),
        "outpath_samples": getattr(p, "outpath_samples", None),
        "script_args": list(getattr(p, "script_args", [])),
        "script_runner_scripts": (
            [script.__class__.__name__ for script in getattr(script_runner, "scripts", [])]
            if script_runner
            else []
        ),
        "callback_map": (
            dict(getattr(script_runner, "callback_map", {}) or {})
            if script_runner and isinstance(getattr(script_runner, "callback_map", None), dict)
            else None
        ),
        "preview_method_id": id(preview_method) if preview_method is not None else None,
        "request_cache_installed": (
            request_cache.patcher.is_installed()
            if (
                request_cache
                and hasattr(request_cache, "patcher")
                and hasattr(request_cache.patcher, "is_installed")
            )
            else False
        ),
    }


def assert_snapshots_equal(left, right):
    assert left == right
