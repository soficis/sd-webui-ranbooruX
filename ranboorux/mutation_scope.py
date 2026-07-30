from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Tuple

_MISSING = object()
_ANY = object()


@dataclass
class RunContext:
    temp_paths: List[Path] = field(default_factory=list)
    cleanup_errors: List[str] = field(default_factory=list)

    def own_temp_path(self, path: str) -> None:
        self.temp_paths.append(Path(path))

    def cleanup(self) -> None:
        for path in reversed(self.temp_paths):
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=False)
                elif path.exists():
                    path.unlink()
            except Exception as exc:
                self.cleanup_errors.append(f"{path}: {exc}")
        self.temp_paths.clear()


@dataclass
class HostMutationScope:
    context: RunContext = field(default_factory=RunContext)
    _snapshots: List[Tuple[object, str, Any, Any]] = field(default_factory=list)
    _restored: bool = False

    def snapshot_attr(self, target: object, attr_name: str) -> None:
        for existing_target, existing_attr, _value, _expected in self._snapshots:
            if existing_target is target and existing_attr == attr_name:
                return
        value = getattr(target, attr_name, _MISSING)
        self._snapshots.append((target, attr_name, value, _ANY))

    def set_attr(self, target: object, attr_name: str, value: object) -> None:
        self.snapshot_attr(target, attr_name)
        setattr(target, attr_name, value)

    def patch_attr(self, target: object, attr_name: str, replacement: object) -> None:
        for index, (existing_target, existing_attr, value, expected) in enumerate(self._snapshots):
            if existing_target is target and existing_attr == attr_name:
                if expected is _ANY or getattr(target, attr_name, _MISSING) is expected:
                    self._snapshots[index] = (target, attr_name, value, replacement)
                    setattr(target, attr_name, replacement)
                return
        value = getattr(target, attr_name, _MISSING)
        self._snapshots.append((target, attr_name, value, replacement))
        setattr(target, attr_name, replacement)

    def restore(self) -> None:
        if self._restored:
            return
        self._restored = True
        for target, attr_name, value, expected in reversed(self._snapshots):
            try:
                if expected is not _ANY and getattr(target, attr_name, _MISSING) is not expected:
                    continue
                if value is _MISSING:
                    if hasattr(target, attr_name):
                        delattr(target, attr_name)
                else:
                    setattr(target, attr_name, value)
            except Exception as exc:
                self.context.cleanup_errors.append(f"{target!r}.{attr_name}: {exc}")
        self._snapshots.clear()
        self.context.cleanup()
