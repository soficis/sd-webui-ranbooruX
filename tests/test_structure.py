import re
from pathlib import Path


def test_no_bundled_controlnet():
    assert not Path("scripts/controlnet.py").exists()


def test_no_bundled_imports():
    source = Path("scripts/ranbooru.py").read_text(encoding="utf-8")
    assert "import scripts.controlnet" not in source
    assert "from scripts import controlnet" not in source


def test_no_remaining_update_calls():
    source = Path("scripts/ranbooru.py").read_text(encoding="utf-8")
    pattern = re.compile(r"gr\.\w+\.update\(")
    assert not pattern.search(source)


def test_no_deepbooru_feature():
    source = Path("scripts/ranbooru.py").read_text(encoding="utf-8").lower()
    assert "deepbooru" not in source


def test_quick_strip_preset_exists():
    source = Path("scripts/ranbooru.py").read_text(encoding="utf-8")
    assert "Quick Strip" in source
