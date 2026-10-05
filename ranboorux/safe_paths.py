from __future__ import annotations

import os
from pathlib import Path
from typing import Union

PathLike = Union[str, os.PathLike]


def contained_path(root: PathLike, candidate: PathLike, *, follow_symlinks: bool = True) -> Path:
    """Return the resolved candidate iff it is strictly inside root; else ValueError.

    With ``follow_symlinks=True`` (default) both paths go through ``realpath``, so a
    symlink inside ``root`` that points elsewhere is rejected. With
    ``follow_symlinks=False`` containment is lexical (``abspath``/``normpath``):
    ``..`` walkouts and absolute escapes are still rejected, but user-made symlinks
    and junctions inside ``root`` (e.g. LoRA folders on another drive) are allowed.

    TOCTOU Note: Check-then-open is not atomic. In a multi-user or symlink-racing
    environment this could have a race condition, but it is an accepted residual
    risk for this local single-user extension.
    """
    if not root or not candidate:
        raise ValueError("Root and candidate paths must not be empty")

    root_str = os.fspath(root).strip()
    candidate_str = os.fspath(candidate).strip()

    if not root_str or not candidate_str:
        raise ValueError("Root and candidate paths must not be empty or whitespace")

    if "\0" in root_str or "\0" in candidate_str:
        raise ValueError("Paths must not contain NUL bytes")

    try:
        resolve = os.path.realpath if follow_symlinks else os.path.abspath
        root_real = resolve(root_str)
        target_real = resolve(candidate_str)

        # On Windows, drive letters and paths are case-insensitive
        if os.name == "nt":
            root_check = os.path.normcase(root_real)
            target_check = os.path.normcase(target_real)
        else:
            root_check = root_real
            target_check = target_real

        # Target must be strictly below root
        if root_check == target_check:
            raise ValueError(f"Target '{candidate_str}' must be strictly below root '{root_str}'")

        common = os.path.commonpath([root_check, target_check])
        if common != root_check:
            raise ValueError(f"Path '{candidate_str}' is outside allowed root '{root_str}'")

    except ValueError as exc:
        raise ValueError(f"Path containment failed: {exc}") from exc

    return Path(target_real)


def safe_join(root: PathLike, *parts: str, follow_symlinks: bool = True) -> Path:
    """contained_path(root, os.path.join(root, *parts)); rejects absolute parts and '..' escape."""
    if not root:
        raise ValueError("Root path must not be empty")

    for part in parts:
        if not part or not str(part).strip():
            raise ValueError("Parts in safe_join must not be empty")
        if os.path.isabs(part):
            raise ValueError(f"Cannot safe_join absolute part: '{part}'")
        if "\0" in str(part):
            raise ValueError("Parts in safe_join must not contain NUL bytes")

    joined = os.path.join(root, *parts)
    return contained_path(root, joined, follow_symlinks=follow_symlinks)
