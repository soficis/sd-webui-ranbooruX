#!/usr/bin/env python
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGETS = (ROOT / "scripts", ROOT / "ranboorux", ROOT / "tests")
PATTERN = re.compile(r"gr\.\w+\.update\(")
SKIP_FILE_NAMES = {"ranbooru.before_revert.py"}


def main() -> int:
    violations: list[str] = []
    for base in TARGETS:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if path.name in SKIP_FILE_NAMES:
                continue
            text = path.read_text(encoding="utf-8")
            if PATTERN.search(text):
                violations.append(str(path.relative_to(ROOT)))

    if violations:
        print("Blocked: gr.Component.update() usage is not allowed.")
        for item in violations:
            print(f"- {item}")
        return 1

    print("No forbidden gr.Component.update() usage found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
