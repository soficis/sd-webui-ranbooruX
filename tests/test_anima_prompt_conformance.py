import importlib
import sys

import pytest


def _get_ranbooru():
    if "scripts.ranbooru" in sys.modules:
        return sys.modules["scripts.ranbooru"]
    return importlib.import_module("scripts.ranbooru")


@pytest.fixture
def script(stub_modules):
    ranbooru = _get_ranbooru()
    return ranbooru.Script()


def make_default_settings(
    shuffle_tags=False,
    change_dash=True,
    **overrides,
):
    from ranboorux.tag_pipeline import PromptRules

    defaults = {
        "shuffle_tags": shuffle_tags,
        "chaos_mode": "None",
        "chaos_amount": 0.0,
        "limit_tags_pct": 1.0,
        "max_tags_count": 0,
        "change_dash": change_dash,
    }
    defaults.update(overrides)
    return PromptRules(**defaults)


def test_negative_score_tags_survive_dash_transform(script):
    """T1: Negative prompt retains score_1, score_2, score_3 with underscores after change_dash."""
    settings = make_default_settings(change_dash=True)
    neg_input = script._anima_negative_default()
    _, current_neg = script._process_single_prompt(0, "1girl", "", neg_input, "", settings)
    assert "score_1" in current_neg
    assert "score_2" in current_neg
    assert "score_3" in current_neg
    assert "score 1" not in current_neg


def test_positive_score_tag_keeps_underscore(script):
    """T2: Positive prefix retains score_7 (pinning the refactor trap)."""
    settings = make_default_settings(change_dash=True)
    pos_prefix = script._anima_quality_prefix()
    current_prompt, _ = script._process_single_prompt(
        0, "blue_hair", pos_prefix.strip().rstrip(","), "", "", settings
    )
    assert "score_7" in current_prompt
    assert "blue hair" in current_prompt


def test_underscore_to_space_except_score(script):
    """T3: General tags convert _ to space, but score_* tags keep underscores."""
    settings = make_default_settings(change_dash=True)
    current_prompt, _ = script._process_single_prompt(0, "blue_hair, score_7", "", "", "", settings)
    assert "blue hair" in current_prompt
    assert "score_7" in current_prompt
    assert "score 7" not in current_prompt


def test_output_is_lowercased(script):
    """T4: Emitted tags are normalized to lowercase."""
    settings = make_default_settings(change_dash=True)
    current_prompt, _ = script._process_single_prompt(
        0, "Blue_Hair, Hatsune_Miku", "", "", "", settings
    )
    assert [t.strip() for t in current_prompt.split(",")] == ["blue hair", "hatsune miku"]


def test_shuffle_tags_defaults_off_for_anima(script):
    """T5: shuffle_tags does not randomize tag order when Anima is active."""
    script._is_anima_model = True
    settings = make_default_settings(shuffle_tags=True)
    raw = "tag1, tag2, tag3, tag4, tag5, tag6, tag7, tag8"
    current_prompt, _ = script._process_single_prompt(0, raw, "", "", "", settings)
    assert [t.strip() for t in current_prompt.split(",")] == [
        "tag1",
        "tag2",
        "tag3",
        "tag4",
        "tag5",
        "tag6",
        "tag7",
        "tag8",
    ]


def test_creator_disambiguator_stripped(script):
    """T6: Disambiguators like _(vocaloid) are stripped so they do not parse as attention syntax."""
    settings = make_default_settings(change_dash=True)
    current_prompt, _ = script._process_single_prompt(
        0, "hatsune_miku_(vocaloid)", "", "", "", settings
    )
    assert "(vocaloid)" not in current_prompt
    assert current_prompt == "hatsune miku"


def test_quality_prefix_token_match_is_exact(script):
    """T7: _has_quality_prefix performs exact token matching, so 'unsafe' does not match 'safe'."""
    assert script._has_quality_prefix("unsafe, 1girl") is False


def test_quality_prefix_window_covers_full_prompt(script):
    """T8: Quality tags past position 10 in prompt are still detected."""
    prompt_with_late_quality = "t1, t2, t3, t4, t5, t6, t7, t8, t9, t10, masterpiece, 1girl"
    assert script._has_quality_prefix(prompt_with_late_quality) is True


def test_aesthetic_variant_suppresses_score_tags(script):
    """T9: Aesthetic variant suppresses score_* tags in quality prefix."""
    script._anima_model_variant = "aesthetic"
    prefix = script._anima_quality_prefix()
    assert "score_" not in prefix
    assert "score_7" not in prefix


def test_turbo_cfg_floor_is_one(script):
    """T10: Turbo variant allows img2img cfg_scale down to 1.0, not floored at 4.0."""
    import types

    from ranboorux.run_options import RunOptions

    script._is_anima_model = True
    script._anima_model_variant = "turbo"
    script.img2img_denoising = 0.5
    options = RunOptions.from_script_args([object()] * 64)
    script.options = options

    p = types.SimpleNamespace(
        prompt="test", steps=20, cfg_scale=1.0, outpath_samples=None, batch_size=1
    )
    script._prepare_img2img_pass(p, use_img2img=True, use_ip=False)
    assert p.cfg_scale == 1.0
