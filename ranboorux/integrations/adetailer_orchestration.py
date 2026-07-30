"""ADetailer orchestration — lifecycle management extracted from the Script class.

Phase 3 of the maintainability refactor: encapsulates all ADetailer lifecycle
methods into a single ``AdetailerOrchestrator`` class that the Script instance
delegates to.

The orchestrator holds a reference to the Script instance (``self._script``)
and accesses Script-owned state (``_adetailer_state``, ``_adetailer_patches``,
``_host_scope``, class-level ``_ranbooru_*`` flags, etc.) through it.
"""

import logging
import types
from enum import Enum, auto
from typing import Any, List

from ranboorux import http_client as rb_http_client
from ranboorux.integrations import adetailer_runtime as rb_adetailer_runtime


class AdetailerState(Enum):
    """Simplified state machine for the ADetailer lifecycle."""

    IDLE = auto()
    """No generation in progress or ADetailer is unblocked."""

    INITIAL_PASS = auto()
    """First pass is running — ADetailer is blocked / guarded."""

    IMG2IMG_READY = auto()
    """Initial pass done; ready for the img2img pass with ADetailer available."""

    ADETAILER_ACTIVE = auto()
    """Manual ADetailer execution is in progress."""

    DONE = auto()
    """Processing complete; guard flags cleared, ready for next generation."""


_logger = logging.getLogger("ranboorux.adetailer_orch")


class AdetailerOrchestrator:
    """Encapsulates ADetailer lifecycle management for RanbooruX.

    Receives a reference to the owning ``Script`` instance and delegates
    Script-owned state access through ``self._script``.
    """

    def __init__(self, script_instance: Any) -> None:
        self._script: Any = script_instance
        self._state: AdetailerState = AdetailerState.IDLE

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_adetailer_script(script: object) -> bool:
        """Check if a script is an ADetailer script."""
        try:
            if script is None:
                return False
            script_name = (
                script.__class__.__name__.lower()
                if hasattr(script, "__class__")
                else str(script).lower()
            )
            return (
                "adetailer" in script_name
                or "afterdetailer" in script_name
                or "after_detailer" in script_name
                or "ad_script" in script_name
            )
        except Exception as exc:
            _logger.warning(
                "Failed to inspect ADetailer script type: %s",
                rb_http_client.sanitize_exception_text(str(exc)),
            )
            return False

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def is_adetailer_enabled(self) -> bool:
        """Return whether the Script-level ADetailer support toggle is on."""
        return bool(getattr(self._script, "_adetailer_support_enabled", False))

    def _is_adetailer_enabled(self) -> bool:
        """Alias kept for internal callers during extraction."""
        return self.is_adetailer_enabled()

    # ------------------------------------------------------------------
    # Initial-pass lifecycle
    # ------------------------------------------------------------------

    def _mark_initial_pass(self, p: object) -> None:
        """Mark that we are in the initial pass so ADetailer can be intercepted later."""
        self._state = AdetailerState.INITIAL_PASS
        try:
            print("[R] Marking initial pass - ADetailer will run on img2img results instead")

            # Clear any previous hard-disable flag for ADetailer
            try:
                if hasattr(p, "_ad_disabled") and getattr(p, "_ad_disabled", False):
                    self._script._host_scope.set_attr(p, "_ad_disabled", False)
                    print("[R] Cleared p._ad_disabled from previous generation")
            except Exception as _e:
                print(f"[R] WARN: Could not clear p._ad_disabled: {_e}")

            # Clear our class-level guard
            self._script._set_adetailer_block(False)
            self._script._adetailer_state.initial_pass_suppressed = False
            # Clear pipeline-level guard flag
            setattr(self._script.__class__, "_ranbooru_block_all_adetailer", False)

            # Install runner guard (idempotent)
            self._install_scriptrunner_guard(p)

            # CRITICAL: Re-enable any ADetailer scripts from previous generation
            self._reenable_adetailer_from_previous_generation()

            # Just set a flag that we are in initial pass
            self._script._ranbooru_initial_pass = True

            # Store reference to processing object for later use
            self._script._initial_pass_p = p

        except Exception as e:
            print(f"[R] Error marking initial pass: {e}")

    def _early_adetailer_protection(self, p: object) -> None:
        """Complete ADetailer blocking during initial pass — remove scripts entirely."""
        if not self.is_adetailer_enabled():
            return
        try:
            print("[R Process] Early ADetailer protection activated")

            # Check if we are in the initial pass
            if getattr(self._script, "_ranbooru_initial_pass", False):
                print("[R Process] Detected initial pass - COMPLETELY BLOCKING ADetailer")

                # Set comprehensive block flags
                self._script._host_scope.set_attr(p, "_ranbooru_skip_initial_adetailer", True)
                self._script._host_scope.set_attr(p, "_ranbooru_suppress_all_processing", True)
                self._script._host_scope.set_attr(p, "_ranbooru_initial_pass_only", True)
                self._script._host_scope.set_attr(p, "_ad_disabled", True)
                self._script._adetailer_state.initial_pass_suppressed = True

                # CRITICAL: Completely remove ADetailer scripts from the runner during initial pass
                self._remove_adetailer_from_runner(p)

                # Set multiple block flags to ensure no ADetailer execution
                self._script._set_adetailer_block(True)
                setattr(self._script.__class__, "_ranbooru_block_all_adetailer", True)
                setattr(self._script.__class__, "_adetailer_global_guard_active", True)
                self._script._adetailer_state.global_guard_active = True

                print(
                    "[R Process] ADetailer completely blocked for initial pass "
                    "- will be restored for manual img2img processing"
                )
                self._state = AdetailerState.INITIAL_PASS

        except Exception as e:
            print(f"[R Process] Error in early ADetailer protection: {e}")

    def _remove_adetailer_from_runner(self, p: object) -> None:
        """Temporarily remove ADetailer scripts from the script runner during initial pass."""
        try:
            if not hasattr(p, "scripts") or p.scripts is None:
                return

            # Store original scripts for restoration
            if not hasattr(self._script, "_stored_adetailer_scripts"):
                self._script._stored_adetailer_scripts = {"alwayson": [], "regular": []}

            # Remove ADetailer from alwayson_scripts
            if hasattr(p.scripts, "alwayson_scripts") and p.scripts.alwayson_scripts:
                original_alwayson = list(p.scripts.alwayson_scripts)
                filtered_alwayson = [
                    s for s in original_alwayson if not self._is_adetailer_script(s)
                ]
                removed_alwayson = [s for s in original_alwayson if self._is_adetailer_script(s)]

                p.scripts.alwayson_scripts = filtered_alwayson
                self._script._stored_adetailer_scripts["alwayson"] = removed_alwayson
                print(
                    f"[R Process] Removed {len(removed_alwayson)} ADetailer scripts "
                    "from alwayson_scripts"
                )

            # Remove ADetailer from regular scripts
            if hasattr(p.scripts, "scripts") and p.scripts.scripts:
                original_scripts = list(p.scripts.scripts)
                filtered_scripts = [s for s in original_scripts if not self._is_adetailer_script(s)]
                removed_scripts = [s for s in original_scripts if self._is_adetailer_script(s)]

                p.scripts.scripts = filtered_scripts
                self._script._stored_adetailer_scripts["regular"] = removed_scripts
                print(f"[R Process] Removed {len(removed_scripts)} ADetailer scripts from scripts")

            # Also check global script lists (ADetailer-Neo on Forge Neo)
            try:
                import modules.scripts as scripts_module

                for attr in ("scripts_txt2img", "scripts_img2img"):
                    global_runner = getattr(scripts_module, attr, None)
                    if global_runner is None or global_runner is p.scripts:
                        continue
                    for list_attr in ("alwayson_scripts", "scripts"):
                        script_list = getattr(global_runner, list_attr, None)
                        if not script_list:
                            continue
                        adetailer_global = [s for s in script_list if self._is_adetailer_script(s)]
                        if adetailer_global:
                            self._script._stored_adetailer_scripts[list_attr] = adetailer_global
                            print(
                                f"[R Process] Found {len(adetailer_global)} ADetailer "
                                f"scripts in global {attr}.{list_attr} "
                                "(blocking via flags)"
                            )
            except Exception:
                pass

        # Also check global script lists (ADetailer-Neo on Forge Neo)
        except Exception as e:
            print(f"[R Process] Error removing ADetailer from runner: {e}")

    def _restore_early_adetailer_protection(self, processing_obj: object = None) -> None:
        """Restore ADetailer scripts and flags after an interrupted or completed run."""
        try:
            self._state = AdetailerState.IMG2IMG_READY
            print("[R Process] Restoring ADetailer scripts for manual processing")

            # Clear initial pass/block flags so subsequent generations can run ADetailer
            setattr(self._script.__class__, "_ranbooru_block_all_adetailer", False)
            setattr(self._script.__class__, "_adetailer_global_guard_active", False)
            self._script._set_adetailer_block(False)

            # Determine which processing object's script runner to restore into
            candidate_p = (
                processing_obj
                or getattr(self._script, "_initial_pass_p", None)
                or getattr(self._script, "_current_processing_object", None)
            )
            runner = getattr(candidate_p, "scripts", None) if candidate_p else None

            # Restore scripts we removed during the initial pass safeguard
            stored = getattr(self._script, "_stored_adetailer_scripts", None)
            if stored and runner:
                try:
                    if hasattr(runner, "alwayson_scripts") and stored.get("alwayson"):
                        for script in stored["alwayson"]:
                            if script not in runner.alwayson_scripts:
                                runner.alwayson_scripts.append(script)
                        print(
                            f"[R Process] Reattached {len(stored['alwayson'])} "
                            "ADetailer always-on script(s)"
                        )
                    if hasattr(runner, "scripts") and stored.get("regular"):
                        for script in stored["regular"]:
                            if script not in runner.scripts:
                                runner.scripts.append(script)
                        print(
                            f"[R Process] Reattached {len(stored['regular'])} "
                            "ADetailer on-demand script(s)"
                        )
                finally:
                    # Clear stored references so we don't duplicate reinsertion
                    delattr(self._script, "_stored_adetailer_scripts")

            # Ensure any scripts we hard-disabled are re-enabled for the next generation
            if hasattr(self._script, "disabled_adetailer_scripts"):
                self._reenable_adetailer_from_previous_generation()

            # Clear temporary protection flag if present
            if hasattr(self._script, "_temp_disabled_adetailer"):
                delattr(self._script, "_temp_disabled_adetailer")

            print("[R Process] Early protection restoration complete")

        except Exception as e:
            print(f"[R Process] Error restoring early ADetailer protection: {e}")

    def _prepare_adetailer_for_img2img(self, p: object) -> None:
        """Prepare ADetailer to run on img2img results."""
        if not self.is_adetailer_enabled():
            return
        try:
            print("[R] Preparing ADetailer to run on img2img results")

            # Clear the initial pass flag so ADetailer knows to run normally
            self._script._ranbooru_initial_pass = False

        except Exception as e:
            print(f"[R] Error preparing ADetailer: {e}")

    # ------------------------------------------------------------------
    # Full restore / native ADetailer re-enablement
    # ------------------------------------------------------------------

    def _restore_native_adetailer_scripts(self, p: object) -> None:
        """Ensure native ADetailer scripts resume running when manual support is disabled."""
        try:
            if not self._script._adetailer_patches.is_empty():
                self._script._unpatch_manual_adetailer_overrides()
        except Exception as exc:
            print(f"[R Before] Warn: Could not unpatch manual ADetailer overrides: {exc}")
        try:
            self._script._set_adetailer_block(False)
        except Exception:
            pass
        setattr(self._script.__class__, "_ranbooru_block_all_adetailer", False)
        setattr(self._script.__class__, "_adetailer_global_guard_active", False)
        try:
            self._restore_early_adetailer_protection(p)
        except Exception as exc:
            print(f"[R Before] Warn: Could not restore ADetailer runner state: {exc}")
        try:
            self._reenable_adetailer_from_previous_generation()
        except Exception as exc:
            print(f"[R Before] Warn: Could not re-enable ADetailer scripts: {exc}")
        try:
            restored = self._force_enable_adetailer_scripts(p)
        except Exception as exc:
            print(f"[R Before] Warn: Could not force-enable ADetailer scripts: {exc}")
            restored = 0
        if restored:
            print(
                f"[R Before] Restored {restored} native ADetailer script(s) "
                "after manual toggle was disabled"
            )
        if hasattr(self._script, "disabled_adetailer_scripts"):
            try:
                delattr(self._script, "disabled_adetailer_scripts")
            except Exception:
                pass
        guard_present = False
        try:
            import modules.scripts as scripts_module

            for runner_attr in ("scripts_txt2img", "scripts_img2img"):
                runner = getattr(scripts_module, runner_attr, None)
                if runner and getattr(runner, "_ranbooru_guard_installed", False):
                    guard_present = True
                    break
        except Exception:
            guard_present = False
        if guard_present:
            try:
                self._script._reset_script_runner_guards()
            except Exception as exc:
                print(f"[R Before] Warn: Could not reset script runner guards: {exc}")
        self._ensure_native_adetailer_enable_flags(p)
        if not self._script._native_adetailer_detected():
            try:
                import modules.scripts as scripts_module

                if hasattr(scripts_module, "reload_scripts"):
                    print("[R Before] Reloading scripts to restore native ADetailer")
                    scripts_module.reload_scripts()
            except Exception as exc:
                print(f"[R Before] Warn: Could not reload scripts for ADetailer: {exc}")

    def _force_enable_adetailer_scripts(self, processing_obj: object = None) -> int:
        """Return the count of ADetailer scripts restored to their original behaviour."""
        try:
            import modules.scripts as scripts_module
        except Exception as exc:
            print(f"[R Before] Warn: Could not access scripts module to restore ADetailer: {exc}")
            return 0
        runners: List[object] = []
        for runner_attr in ("scripts_txt2img", "scripts_img2img"):
            runner = getattr(scripts_module, runner_attr, None)
            if runner:
                runners.append(runner)
        if (
            processing_obj is not None
            and hasattr(processing_obj, "scripts")
            and processing_obj.scripts not in runners
        ):
            runners.append(processing_obj.scripts)
        seen_ids: set = set()
        restored_count = 0
        for runner in runners:
            if runner is None:
                continue
            for list_attr in ("alwayson_scripts", "scripts"):
                script_list = getattr(runner, list_attr, None)
                if not script_list:
                    continue
                for script in script_list:
                    if not script:
                        continue
                    script_id = id(script)
                    if script_id in seen_ids:
                        continue
                    seen_ids.add(script_id)
                    if not self._is_adetailer_script(script):
                        continue
                    restored = False
                    if hasattr(script, "enabled") and script.enabled is False:
                        script.enabled = True
                        restored = True
                    for method_name in (
                        "postprocess",
                        "process",
                        "process_batch",
                        "before_process",
                        "after_process",
                    ):
                        backup_name = f"_ranbooru_original_{method_name}"
                        if hasattr(script, backup_name):
                            try:
                                setattr(script, method_name, getattr(script, backup_name))
                            except Exception:
                                pass
                            try:
                                delattr(script, backup_name)
                            except Exception:
                                pass
                            restored = True
                    for attr in ("_ranbooru_disabled_after_manual", "_ranbooru_disabled_source"):
                        if hasattr(script, attr):
                            try:
                                delattr(script, attr)
                            except Exception:
                                pass
                            restored = True
                    if restored:
                        restored_count += 1
        if restored_count == 0:
            try:
                debug_entries = []
                for runner in runners:
                    if not runner:
                        continue
                    for list_attr in ("alwayson_scripts", "scripts"):
                        script_list = getattr(runner, list_attr, None)
                        if not script_list:
                            continue
                        for script in script_list:
                            if self._is_adetailer_script(script):
                                debug_entries.append(
                                    f"{script.__class__.__name__}"
                                    f"(enabled={getattr(script, 'enabled', 'n/a')})"
                                )
                if debug_entries:
                    print(
                        "[R Before] Native ADetailer scripts detected: " + ", ".join(debug_entries)
                    )
            except Exception:
                pass
        return restored_count

    def _ensure_native_adetailer_enable_flags(self, processing_obj: Any) -> None:
        """Ensure ADetailer enable/skip flags in script_args are set correctly."""
        if not getattr(self._script, "_adetailer_support_enabled", False):
            return
        try:
            args = getattr(processing_obj, "script_args", None)
        except Exception as exc:
            print(f"[R Before] Native ADetailer: unable to read script_args: {exc}")
            return
        if not isinstance(args, (list, tuple)) or not args:
            print(
                "[R Before] Native ADetailer: script_args empty or not list/tuple; "
                "skipping flag repair"
            )
            return
        args_list = list(args)
        runners: List[object] = []
        runner = getattr(processing_obj, "scripts", None)
        if runner is not None:
            runners.append(runner)
        try:
            import modules.scripts as scripts_module

            for attr in ("scripts_txt2img", "scripts_img2img"):
                global_runner = getattr(scripts_module, attr, None)
                if global_runner is not None and global_runner not in runners:
                    runners.append(global_runner)
        except Exception as exc:
            print(f"[R Before] Native ADetailer: could not gather global runners: {exc}")
        candidates: list = []
        for r in runners:
            for list_attr in ("alwayson_scripts", "scripts"):
                script_list = getattr(r, list_attr, None)
                if script_list:
                    candidates.extend(script_list)
        if not candidates:
            print("[R Before] Native ADetailer: no script candidates found for flag repair")
            return
        changed = False
        for script in candidates:
            if not self._is_adetailer_script(script):
                continue
            extracted = self._script._extract_adetailer_script_args(script, processing_obj)
            sanitized = list(extracted.get("args") or [])
            meta = extracted.get("meta") or {}
            start_idx = meta.get("slice_start")
            end_idx = meta.get("slice_end")
            if start_idx is None or end_idx is None:
                continue
            start_idx = max(0, min(len(args_list), start_idx))
            end_idx = max(start_idx, min(len(args_list), end_idx))
            if not sanitized or end_idx - start_idx != len(sanitized):
                slice_view = args_list[start_idx:end_idx]
            else:
                slice_view = sanitized
            print(
                f"[R Before] Native ADetailer candidate {script.__class__.__name__} "
                f"enabled={getattr(script, 'enabled', 'n/a')} "
                f"slice [{start_idx}:{end_idx}] -> {slice_view}"
            )
            if not sanitized:
                continue
            bool_index = 0
            local_changed = False
            for offset, val in enumerate(sanitized):
                if isinstance(val, bool):
                    if bool_index == 0 and val is False:
                        sanitized[offset] = True
                        local_changed = True
                        print(
                            f"[R Before] Set native ADetailer enable flag True at offset {offset}"
                        )
                    elif bool_index == 1 and val is True:
                        sanitized[offset] = False
                        local_changed = True
                        print(f"[R Before] Cleared native ADetailer skip flag at offset {offset}")
                    bool_index += 1
                elif isinstance(val, dict):
                    if val.get("ad_tab_enable") is False and val.get("ad_model") not in (
                        None,
                        "",
                        "None",
                    ):
                        val["ad_tab_enable"] = True
                        local_changed = True
                        print(f"[R Before] Enabled ad_tab_enable in dict at offset {offset}")
            if local_changed:
                if end_idx - start_idx == len(sanitized):
                    args_list[start_idx:end_idx] = sanitized
                    changed = True
                    continue
                # fallback if lengths mismatch
                for offset, val in enumerate(sanitized):
                    target_idx = start_idx + offset
                    if target_idx < len(args_list):
                        args_list[target_idx] = val
                    else:
                        args_list.append(val)
                changed = True
        if changed:
            if isinstance(args, list):
                processing_obj.script_args = args_list
            else:
                processing_obj.script_args = tuple(args_list)
            print(f"[R Before] Native ADetailer flags updated: {args_list}")
        else:
            print("[R Before] Native ADetailer flags already enabled; no changes made")

    # ------------------------------------------------------------------
    # Re-enable from previous generation
    # ------------------------------------------------------------------

    def _reenable_adetailer_from_previous_generation(self) -> None:
        """Re-enable ALL ADetailer scripts that were disabled in the previous generation."""
        try:
            if (
                hasattr(self._script, "disabled_adetailer_scripts")
                and self._script.disabled_adetailer_scripts
            ):
                print(
                    f"[R] COMPREHENSIVE RE-ENABLE: Restoring "
                    f"{len(self._script.disabled_adetailer_scripts)} ADetailer script(s) "
                    "from previous generation"
                )

                for script, original_enabled in self._script.disabled_adetailer_scripts:
                    source = getattr(script, "_ranbooru_disabled_source", "unknown")
                    print(f"[R] Re-enabling {script.__class__.__name__} from {source}")

                    # Restore original enabled state
                    if hasattr(script, "enabled"):
                        script.enabled = original_enabled

                    # Restore ALL original methods that were disabled
                    methods_to_restore = [
                        "postprocess",
                        "process",
                        "process_batch",
                        "before_process",
                        "after_process",
                    ]
                    for method_name in methods_to_restore:
                        original_method_attr = f"_ranbooru_original_{method_name}"
                        if hasattr(script, original_method_attr):
                            original_method = getattr(script, original_method_attr)
                            setattr(script, method_name, original_method)
                            delattr(script, original_method_attr)

                    # Remove our disable flags
                    if hasattr(script, "_ranbooru_disabled_after_manual"):
                        delattr(script, "_ranbooru_disabled_after_manual")
                    if hasattr(script, "_ranbooru_disabled_source"):
                        delattr(script, "_ranbooru_disabled_source")

                print(
                    f"[R] COMPREHENSIVE RE-ENABLE: Restored "
                    f"{len(self._script.disabled_adetailer_scripts)} ADetailer script(s) "
                    "for new generation"
                )
                # Clear the list now that we've re-enabled everything
                delattr(self._script, "disabled_adetailer_scripts")

        except Exception as e:
            print(f"[R] Error in comprehensive ADetailer re-enable: {e}")

    # ------------------------------------------------------------------
    # Manual ADetailer execution
    # ------------------------------------------------------------------

    def _execute_manual_adetailer(self, p: Any, processed: Any, img2img_results: List[Any]) -> bool:
        """Run manual ADetailer on img2img results via the deterministic runtime executor."""
        if not self.is_adetailer_enabled() or not img2img_results:
            return False

        self._script._clear_manual_adetailer_skip_flags(p)
        adetailer_scripts = rb_adetailer_runtime.gather_adetailer_scripts(p)
        if not adetailer_scripts:
            print("[R Post] WARN: No ADetailer scripts discovered for manual execution")
            return False

        setattr(self._script.__class__, "_ranbooru_manual_adetailer_active", True)

        def build_processed(single_image: object) -> object:
            temp_processed = types.SimpleNamespace()
            temp_processed.images = [single_image]
            temp_processed.image = single_image
            for attr in (
                "prompt",
                "negative_prompt",
                "seed",
                "subseed",
                "width",
                "height",
                "cfg_scale",
                "steps",
            ):
                if hasattr(processed, attr):
                    setattr(temp_processed, attr, getattr(processed, attr))
            return temp_processed

        self._state = AdetailerState.ADETAILER_ACTIVE
        try:
            result = rb_adetailer_runtime.execute_manual_adetailer(
                adetailer_scripts=adetailer_scripts,
                images=list(img2img_results),
                processing_obj=p,
                run_state=self._script._adetailer_state,
                patch_registry=self._script._adetailer_patches,
                extract_script_args=self._script._extract_adetailer_script_args,
                build_processed=build_processed,
                isolation_factory=lambda script_obj: self._script._manual_adetailer_script_isolation(
                    p,
                    script_obj,
                    keep_controlnet=self._script._manual_adetailer_requires_controlnet(
                        self._script._extract_adetailer_script_args(script_obj, p).get("args") or []
                    ),
                ),
            )
        finally:
            setattr(self._script.__class__, "_ranbooru_manual_adetailer_active", False)
            self._state = AdetailerState.IMG2IMG_READY

        for error in result.errors:
            print(f"[R Post] WARN: Manual ADetailer error: {error}")
        processed.images.clear()
        processed.images.extend(result.images)
        img2img_results.clear()
        img2img_results.extend(result.images)
        if hasattr(p, "processed") and hasattr(p.processed, "images"):
            p.processed.images.clear()
            p.processed.images.extend(result.images)
        return result.successful_processes > 0

    # ------------------------------------------------------------------
    # ScriptRunner guard
    # ------------------------------------------------------------------

    def _install_scriptrunner_guard(self, p: object) -> None:
        """Wrap p.scripts postprocess/postprocess_image to skip ADetailer when blocked."""
        try:
            if not hasattr(p, "scripts") or p.scripts is None:
                return
            runner = p.scripts
            if getattr(runner, "_ranbooru_guard_installed", False):
                return
            rb_adetailer_runtime.install_runner_guard(
                runner=runner,
                block_flag_fn=lambda: bool(
                    getattr(self._script.__class__, "_ranbooru_block_all_adetailer", False)
                    and not getattr(
                        self._script.__class__, "_ranbooru_manual_adetailer_active", False
                    )
                ),
                patch_registry=self._script._adetailer_patches,
            )
            runner._ranbooru_guard_installed = True
            self._script._log_patch_event(
                "info", "Installed ScriptRunner guard to skip ADetailer when blocked"
            )
        except Exception as e:
            self._script._log_patch_event("warning", f"Failed to install ScriptRunner guard: {e}")
            print(f"[R] Error installing ScriptRunner guard: {e}")

    # ------------------------------------------------------------------
    # Preview guard (shared.state)
    # ------------------------------------------------------------------

    def _install_preview_guard(self) -> None:
        """Install a guard around shared.state.assign_current_image to block wrong previews."""
        try:
            import modules.shared as shared

            if not hasattr(shared, "state"):
                return
            state = shared.state
            installed_wrapper = getattr(state, "_ranbooru_preview_guard_wrapper", None)
            if (
                getattr(state, "_ranbooru_preview_guard_installed", False)
                and installed_wrapper is not None
                and getattr(state, "assign_current_image", None) is installed_wrapper
            ):
                self._state = AdetailerState.IMG2IMG_READY
                return
            if not hasattr(state, "assign_current_image"):
                self._state = AdetailerState.IMG2IMG_READY
                return
            self._state = AdetailerState.INITIAL_PASS
            original_assign_current_image = state.assign_current_image
            script_class = self._script.__class__

            def guarded_assign_current_image(img: object) -> Any:
                try:
                    if getattr(script_class, "_ranbooru_preview_guard_on", False):
                        if getattr(script_class, "_ranbooru_preview_block_all", False):
                            if not getattr(
                                script_class, "_ranbooru_preview_block_notice_emitted", False
                            ):
                                print(
                                    "[R UI] Preview blocked: withholding intermediary frame "
                                    "until final image is ready"
                                )
                                script_class._ranbooru_preview_block_notice_emitted = True
                            return
                        # If we know final dims, only allow those; otherwise block 640x512
                        final_dims = getattr(script_class, "_ranbooru_final_dims", None)
                        if img is not None and hasattr(img, "size"):
                            if final_dims and img.size != final_dims:
                                print("[R UI] Preview blocked: mismatched size")
                                return
                            if img.size == (640, 512):
                                print("[R UI] Preview blocked: 640x512 preview")
                                return
                except Exception:
                    pass
                return original_assign_current_image(img)

            self._script._host_scope.patch_attr(
                state, "assign_current_image", guarded_assign_current_image
            )
            self._script._host_scope.set_attr(state, "_ranbooru_preview_guard_installed", True)
            self._script._host_scope.set_attr(
                state, "_ranbooru_preview_guard_wrapper", guarded_assign_current_image
            )
            print("[R UI] Installed preview guard")
        except Exception as e:
            print(f"[R UI] Error installing preview guard: {e}")
