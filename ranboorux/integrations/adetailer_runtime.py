from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from typing import Any, Callable, ContextManager, Dict, Iterable, Iterator, List, Optional, cast


@dataclass
class AdetailerRunState:
    block_all: bool = False
    manual_active: bool = False
    initial_pass_suppressed: bool = False
    processing_complete: bool = False
    preview_guard_on: bool = False
    preview_block_all: bool = False
    global_guard_active: bool = False
    pipeline_blocked: bool = False

    def reset(self) -> None:
        self.block_all = False
        self.manual_active = False
        self.initial_pass_suppressed = False
        self.processing_complete = False
        self.preview_guard_on = False
        self.preview_block_all = False
        self.global_guard_active = False
        self.pipeline_blocked = False

    def is_blocked(self) -> bool:
        return bool(self.block_all or self.pipeline_blocked)


@dataclass
class PatchRecord:
    target: object
    method_name: str
    original_method: Callable[..., Any]
    installed_method: Callable[..., Any]
    description: str


@dataclass
class PatchRegistry:
    _patches: List[PatchRecord] = field(default_factory=list)
    restore_errors: List[str] = field(default_factory=list)

    def install(
        self,
        target: object,
        method_name: str,
        replacement: Callable[..., Any],
        description: str,
    ) -> None:
        if target is None or not hasattr(target, method_name):
            return
        original = getattr(target, method_name)
        if not callable(original) or not callable(replacement):
            return
        for existing in self._patches:
            if existing.target is target and existing.method_name == method_name:
                if getattr(target, method_name, None) is existing.installed_method:
                    setattr(target, method_name, replacement)
                    existing.installed_method = replacement
                return
        self._patches.append(
            PatchRecord(
                target=target,
                method_name=method_name,
                original_method=original,
                installed_method=replacement,
                description=description,
            )
        )
        setattr(target, method_name, replacement)

    def uninstall_all(self) -> List[str]:
        if not self._patches:
            errors = list(self.restore_errors)
            self.restore_errors.clear()
            return errors
        for patch in reversed(self._patches):
            try:
                if getattr(patch.target, patch.method_name, None) is patch.installed_method:
                    setattr(patch.target, patch.method_name, patch.original_method)
            except Exception as exc:
                self.restore_errors.append(f"{patch.description}: {exc}")
        self._patches.clear()
        errors = list(self.restore_errors)
        self.restore_errors.clear()
        return errors

    def is_empty(self) -> bool:
        return not self._patches


@dataclass
class RunnerSnapshot:
    alwayson_scripts: List[Any]
    scripts: List[Any]
    callback_map: Optional[Dict[Any, Any]]

    @classmethod
    def capture(cls, runner: object) -> "RunnerSnapshot":
        alwayson = list(getattr(runner, "alwayson_scripts", []) or [])
        scripts = list(getattr(runner, "scripts", []) or [])
        callback_map = getattr(runner, "callback_map", None)
        callback_copy: Optional[Dict[Any, Any]] = None
        if isinstance(callback_map, dict):
            callback_copy = dict(callback_map)
        return cls(alwayson_scripts=alwayson, scripts=scripts, callback_map=callback_copy)

    def restore(
        self,
        runner: object,
        *,
        expected_alwayson_scripts: Optional[List[Any]] = None,
        expected_scripts: Optional[List[Any]] = None,
        expected_callback_map: Optional[Dict[Any, Any]] = None,
    ) -> None:
        current_alwayson = list(getattr(runner, "alwayson_scripts", []) or [])
        if expected_alwayson_scripts is None or current_alwayson == expected_alwayson_scripts:
            setattr(runner, "alwayson_scripts", list(self.alwayson_scripts))

        current_scripts = list(getattr(runner, "scripts", []) or [])
        if expected_scripts is None or current_scripts == expected_scripts:
            setattr(runner, "scripts", list(self.scripts))

        if expected_callback_map is not None:
            current_callback_map = getattr(runner, "callback_map", None)
            if (
                not isinstance(current_callback_map, dict)
                or current_callback_map != expected_callback_map
            ):
                return
        if self.callback_map is None:
            if hasattr(runner, "callback_map"):
                try:
                    delattr(runner, "callback_map")
                except Exception:
                    pass
            return
        setattr(runner, "callback_map", dict(self.callback_map))


@dataclass
class ManualAdetailerResult:
    images: List[Any]
    successful_processes: int
    errors: List[str] = field(default_factory=list)


def _is_adetailer_script(script_obj: object) -> bool:
    try:
        class_name = script_obj.__class__.__name__.lower()
    except Exception:
        class_name = ""
    return "adetailer" in class_name or "afterdetailer" in class_name


def _is_controlnet_script(script_obj: object) -> bool:
    try:
        class_name = script_obj.__class__.__name__.lower()
        if "controlnet" in class_name:
            return True
        title_attr = getattr(script_obj, "title", None)
        if callable(title_attr):
            title = str(title_attr()).strip().lower()
            return "controlnet" in title
    except Exception:
        return False
    return False


def _clear_runner_callback_map(runner: object) -> None:
    callback_map = getattr(runner, "callback_map", None)
    if isinstance(callback_map, dict):
        callback_map.clear()


def _restore_runner_callback_map(
    runner: object,
    original_callback_map: Optional[Dict[Any, Any]],
    expected_callback_map: Dict[Any, Any],
) -> None:
    current_callback_map = getattr(runner, "callback_map", None)
    if not isinstance(current_callback_map, dict) or current_callback_map != expected_callback_map:
        return
    if original_callback_map is None:
        try:
            delattr(runner, "callback_map")
        except Exception:
            pass
        return
    setattr(runner, "callback_map", dict(original_callback_map))


def install_runner_guard(
    runner: object,
    block_flag_fn: Callable[[], bool],
    patch_registry: PatchRegistry,
) -> None:
    if runner is None:
        return

    postprocess = getattr(runner, "postprocess", None)
    if callable(postprocess):

        def guarded_postprocess(*args: Any, **kwargs: Any) -> Any:
            if not block_flag_fn():
                return postprocess(*args, **kwargs)
            saved_alwayson = list(getattr(runner, "alwayson_scripts", []) or [])
            saved_scripts = list(getattr(runner, "scripts", []) or [])
            callback_map = getattr(runner, "callback_map", None)
            saved_callback_map = dict(callback_map) if isinstance(callback_map, dict) else None
            expected_callback_map: Optional[Dict[Any, Any]] = None
            try:
                if hasattr(runner, "alwayson_scripts"):
                    setattr(
                        runner,
                        "alwayson_scripts",
                        [item for item in saved_alwayson if not _is_adetailer_script(item)],
                    )
                if hasattr(runner, "scripts"):
                    setattr(
                        runner,
                        "scripts",
                        [item for item in saved_scripts if not _is_adetailer_script(item)],
                    )
                _clear_runner_callback_map(runner)
                if isinstance(getattr(runner, "callback_map", None), dict):
                    expected_callback_map = {}
                return postprocess(*args, **kwargs)
            finally:
                if hasattr(runner, "alwayson_scripts"):
                    setattr(runner, "alwayson_scripts", saved_alwayson)
                if hasattr(runner, "scripts"):
                    setattr(runner, "scripts", saved_scripts)
                if expected_callback_map is not None:
                    _restore_runner_callback_map(
                        runner,
                        saved_callback_map,
                        expected_callback_map,
                    )

        patch_registry.install(
            runner, "postprocess", guarded_postprocess, "ScriptRunner postprocess guard"
        )

    postprocess_image = getattr(runner, "postprocess_image", None)
    if callable(postprocess_image):

        def guarded_postprocess_image(*args: Any, **kwargs: Any) -> Any:
            if not block_flag_fn():
                return postprocess_image(*args, **kwargs)
            saved_alwayson = list(getattr(runner, "alwayson_scripts", []) or [])
            saved_scripts = list(getattr(runner, "scripts", []) or [])
            callback_map = getattr(runner, "callback_map", None)
            saved_callback_map = dict(callback_map) if isinstance(callback_map, dict) else None
            expected_callback_map: Optional[Dict[Any, Any]] = None
            try:
                if hasattr(runner, "alwayson_scripts"):
                    setattr(
                        runner,
                        "alwayson_scripts",
                        [item for item in saved_alwayson if not _is_adetailer_script(item)],
                    )
                if hasattr(runner, "scripts"):
                    setattr(
                        runner,
                        "scripts",
                        [item for item in saved_scripts if not _is_adetailer_script(item)],
                    )
                _clear_runner_callback_map(runner)
                if isinstance(getattr(runner, "callback_map", None), dict):
                    expected_callback_map = {}
                return postprocess_image(*args, **kwargs)
            finally:
                if hasattr(runner, "alwayson_scripts"):
                    setattr(runner, "alwayson_scripts", saved_alwayson)
                if hasattr(runner, "scripts"):
                    setattr(runner, "scripts", saved_scripts)
                if expected_callback_map is not None:
                    _restore_runner_callback_map(
                        runner,
                        saved_callback_map,
                        expected_callback_map,
                    )

        patch_registry.install(
            runner,
            "postprocess_image",
            guarded_postprocess_image,
            "ScriptRunner postprocess_image guard",
        )


def _should_keep_script(
    script_item: object,
    adetailer_script: object,
    keep_controlnet: bool,
    keep_controlnet_fn: Optional[Callable[[object, str], bool]],
    list_attr: str,
) -> bool:
    if script_item is adetailer_script:
        return True
    if not keep_controlnet:
        return False
    if keep_controlnet_fn is not None:
        return bool(keep_controlnet_fn(script_item, list_attr))
    return _is_controlnet_script(script_item)


@contextmanager
def runner_isolation(
    runner: object,
    adetailer_script: object,
    keep_controlnet_fn: Optional[Callable[[object, str], bool]] = None,
    *,
    keep_controlnet: bool = False,
) -> Iterator[None]:
    if runner is None or adetailer_script is None:
        yield
        return

    snapshot = RunnerSnapshot.capture(runner)
    expected_alwayson: Optional[List[Any]] = None
    expected_scripts: Optional[List[Any]] = None
    expected_callback_map: Optional[Dict[Any, Any]] = None
    try:
        for list_attr in ("alwayson_scripts", "scripts"):
            script_list = getattr(runner, list_attr, None)
            if not isinstance(script_list, (list, tuple)):
                continue
            filtered: List[object] = []
            for script_item in list(script_list):
                if _should_keep_script(
                    script_item,
                    adetailer_script,
                    keep_controlnet,
                    keep_controlnet_fn,
                    list_attr,
                ):
                    filtered.append(script_item)
            setattr(runner, list_attr, filtered)
            if list_attr == "alwayson_scripts":
                expected_alwayson = list(filtered)
            else:
                expected_scripts = list(filtered)
        _clear_runner_callback_map(runner)
        if isinstance(getattr(runner, "callback_map", None), dict):
            expected_callback_map = {}
        yield
    finally:
        snapshot.restore(
            runner,
            expected_alwayson_scripts=expected_alwayson,
            expected_scripts=expected_scripts,
            expected_callback_map=expected_callback_map,
        )


def _images_differ(original: object, updated: object) -> bool:
    if updated is None:
        return False
    if original is None:
        return True
    original_size = getattr(original, "size", None)
    updated_size = getattr(updated, "size", None)
    if original_size is not None and updated_size is not None and original_size != updated_size:
        return True
    try:
        original_bytes = original.tobytes() if hasattr(original, "tobytes") else None
        updated_bytes = updated.tobytes() if hasattr(updated, "tobytes") else None
        if original_bytes is not None and updated_bytes is not None:
            return bool(original_bytes != updated_bytes)
    except Exception:
        return original is not updated
    return original is not updated


def _candidate_scripts(adetailer_scripts: Iterable[object]) -> List[object]:
    deduped: List[object] = []
    seen_ids: set[int] = set()
    for script_obj in adetailer_scripts:
        if script_obj is None:
            continue
        script_id = id(script_obj)
        if script_id in seen_ids:
            continue
        seen_ids.add(script_id)
        if _is_adetailer_script(script_obj):
            deduped.append(script_obj)
    return deduped


def _extract_processed_image(temp_processed: object, fallback: object) -> object:
    images = getattr(temp_processed, "images", None)
    if isinstance(images, list) and images:
        return images[0]
    image = getattr(temp_processed, "image", None)
    if image is not None:
        return image
    return fallback


def execute_manual_adetailer(
    adetailer_scripts: List[object],
    images: List[Any],
    processing_obj: object,
    run_state: AdetailerRunState,
    patch_registry: PatchRegistry,
    *,
    extract_script_args: Callable[[object, object], Dict[str, Any]],
    build_processed: Callable[[object], object],
    isolation_factory: Optional[Callable[[object], ContextManager[None]]] = None,
) -> ManualAdetailerResult:
    del patch_registry
    processed_images: List[Any] = list(images or [])
    successful_processes = 0
    errors: List[str] = []
    run_state.manual_active = True

    try:
        for adetailer_script in _candidate_scripts(adetailer_scripts):
            extracted = extract_script_args(adetailer_script, processing_obj)
            script_args = list(extracted.get("args") or [])
            if not script_args:
                continue

            for index, original_image in enumerate(list(processed_images)):
                try:
                    temp_processed = build_processed(original_image)
                except Exception as exc:
                    errors.append(
                        f"{adetailer_script.__class__.__name__} image {index + 1}: "
                        f"failed to build processed object: {exc}"
                    )
                    continue
                if temp_processed is None:
                    continue

                script_ctx = (
                    isolation_factory(adetailer_script) if isolation_factory else nullcontext()
                )
                try:
                    with script_ctx:
                        script_obj = cast(Any, adetailer_script)
                        if callable(getattr(script_obj, "postprocess_image", None)):
                            script_obj.postprocess_image(
                                processing_obj,
                                temp_processed,
                                *script_args,
                            )
                        elif callable(getattr(script_obj, "postprocess", None)):
                            script_obj.postprocess(
                                processing_obj,
                                temp_processed,
                                *script_args,
                            )
                        else:
                            continue
                except Exception as exc:
                    errors.append(f"{adetailer_script.__class__.__name__} image {index + 1}: {exc}")
                    continue

                candidate_image = _extract_processed_image(temp_processed, original_image)
                if _images_differ(original_image, candidate_image):
                    processed_images[index] = candidate_image
                    successful_processes += 1

        return ManualAdetailerResult(
            images=processed_images,
            successful_processes=successful_processes,
            errors=errors,
        )
    finally:
        run_state.manual_active = False


def gather_adetailer_scripts(processing_obj: object) -> List[object]:
    runner = getattr(processing_obj, "scripts", None)
    if runner is None:
        return []
    scripts_list: List[object] = []
    scripts_list.extend(list(getattr(runner, "alwayson_scripts", []) or []))
    scripts_list.extend(list(getattr(runner, "scripts", []) or []))
    return _candidate_scripts(scripts_list)
