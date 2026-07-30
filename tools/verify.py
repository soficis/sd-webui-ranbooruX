#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
CHECK_TARGETS = ["scripts/ranbooru.py", "ranboorux", "tests", "tools", "install.py"]


def run_step(name: str, command: Sequence[str]) -> bool:
    print(f"\n--- {name} ---")
    print(" ".join(command))
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        print(f"FAILED: {name} exited with {result.returncode}")
        return False
    print(f"OK: {name}")
    return True


def require_module(module_name: str) -> bool:
    if importlib.util.find_spec(module_name) is not None:
        return True
    print(f"FAILED: configured developer tool '{module_name}' is not installed for {PYTHON}.")
    print("Install it in this environment, then rerun tools/verify.py.")
    return False


def main() -> int:
    steps = [
        ("Repository guard", [PYTHON, "tools/repo_guard.py", "--mode", "codex"]),
        ("Gradio compatibility", [PYTHON, "tools/check_no_gradio_update.py"]),
        ("Pytest default", [PYTHON, "-m", "pytest", "tests/", "-q"]),
        ("Pytest Gradio 4", [PYTHON, "-m", "pytest", "tests/", "-q", "--gradio-version=4"]),
    ]

    for name, command in steps:
        if not run_step(name, command):
            return 1

    missing = [
        module_name for module_name in ("ruff", "black", "mypy") if not require_module(module_name)
    ]
    if missing:
        return 1

    tool_steps = [
        ("Ruff", [PYTHON, "-m", "ruff", "check", *CHECK_TARGETS]),
        ("Black", [PYTHON, "-m", "black", "--check", *CHECK_TARGETS]),
        ("Mypy", [PYTHON, "-m", "mypy", "ranboorux"]),
    ]
    for name, command in tool_steps:
        if not run_step(name, command):
            return 1

    print("\nVerification completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
