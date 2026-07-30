#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Sequence

FORBIDDEN_BY_MODE = {
    "gemini": (
        "scripts/ranbooru.py",
        "ranboorux/integrations/",
        "adetailer/",
    ),
    "codex": ("adetailer/",),
}


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip().strip('"')


def check_files(file_list: Iterable[str], forbidden_prefixes: Sequence[str]) -> List[str]:
    violations: List[str] = []
    for path in file_list:
        normalized = normalize_path(path)
        for forbidden in forbidden_prefixes:
            if normalized == forbidden or normalized.startswith(forbidden):
                violations.append(path)
                break
    return violations


def _run_git(repo_root: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", f"safe.directory={repo_root.as_posix()}", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )


def get_git_modified_files(repo_root: Path) -> List[str]:
    diff = _run_git(repo_root, ["diff", "HEAD", "--name-only"])
    status = _run_git(repo_root, ["status", "--porcelain"])

    files = {line.strip() for line in diff.stdout.splitlines() if line.strip()}
    for line in status.stdout.splitlines():
        if not line.strip():
            continue
        payload = line[3:].strip()
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1]
        files.add(payload.strip('"'))
    return sorted(files)


def get_files_to_check(repo_root: Path, explicit_paths: Sequence[str]) -> List[str]:
    if explicit_paths:
        return list(explicit_paths)
    if not (repo_root / ".git").exists():
        print("INFO: Git metadata not found; repository guard is not applicable in source release.")
        return []
    return get_git_modified_files(repo_root)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check forbidden modified paths.")
    parser.add_argument("--mode", choices=sorted(FORBIDDEN_BY_MODE), default="codex")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional simulated changed-file list. Omit to inspect git status.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = Path(__file__).resolve().parents[1]
    forbidden = FORBIDDEN_BY_MODE[args.mode]
    files_to_check = get_files_to_check(repo_root, args.paths)

    violations = check_files(files_to_check, forbidden)
    if violations:
        print(f"ERROR: Forbidden {args.mode} modifications detected:")
        for violation in violations:
            print(f"  - {violation}")
        return 1

    print(f"SUCCESS: No forbidden {args.mode} modifications detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
