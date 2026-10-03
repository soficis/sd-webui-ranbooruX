from ranboorux.tag_pipeline import (
    build_removal_context,
    build_synonym_lookup,
    canonicalize_raw_tag,
    dedupe_keep_order,
    expand_with_synonyms,
    is_clothing_tag,
    is_eye_color_tag,
    is_furry_tag,
    is_girl_suffix_tag,
    is_hair_color_tag,
    is_headwear_tag,
    is_series_tag,
    is_subject_tag,
    is_textual_tag,
    normalize_tag,
    post_rejected_by_filter,
    remove_repeated_tags,
    split_prompt_tags,
    tag_matches_removal,
)


def test_split_prompt_tags():
    assert split_prompt_tags("1girl, blonde hair, blue eyes") == [
        "1girl",
        "blonde hair",
        "blue eyes",
    ]
    assert split_prompt_tags("") == []
    assert split_prompt_tags(None) == []
    assert split_prompt_tags("  , ,, ,  ") == []


def test_dedupe_keep_order():
    assert dedupe_keep_order(["1girl", "blonde hair", "1girl", "blue eyes", "blonde hair"]) == [
        "1girl",
        "blonde hair",
        "blue eyes",
    ]
    assert dedupe_keep_order([]) == []


def test_remove_repeated_tags():
    assert (
        remove_repeated_tags("1girl, blonde hair, 1girl, blue eyes")
        == "1girl,blonde hair,blue eyes"
    )
    assert remove_repeated_tags("") == ""


def test_canonicalize_raw_tag():
    assert canonicalize_raw_tag(" 1GIRL_with_Sword  ") == "1girl with sword"
    assert canonicalize_raw_tag("") == ""
    assert canonicalize_raw_tag(None) == ""


def test_normalize_tag():
    assert normalize_tag("(1girl)") == "1girl"
    assert normalize_tag("[blonde_hair]") == "blonde hair"
    assert normalize_tag("  {blue-eyes}  ") == "blue eyes"
    assert normalize_tag("") == ""
    assert normalize_tag(None) == ""


def test_synonyms_and_lookup():
    syn_groups = [
        {"grayscale", "greyscale", "monochrome"},
        {"1girl", "1female", "1woman"},
    ]
    lookup = build_synonym_lookup(syn_groups)
    assert "grayscale" in lookup
    assert "greyscale" in lookup
    assert lookup["grayscale"] == {"grayscale", "greyscale", "monochrome"}

    target = {"grayscale"}
    expand_with_synonyms("grayscale", target, lookup)
    assert target == {"grayscale", "greyscale", "monochrome"}


def test_tag_classification():
    assert is_furry_tag("kemono") is True
    assert is_furry_tag("pokemon_pikachu") is True
    assert is_furry_tag("cat_ears") is True
    assert is_furry_tag("1girl") is False

    assert is_headwear_tag("witch_hat") is True
    assert is_headwear_tag("floating halo") is True
    assert is_headwear_tag("gloves") is False

    assert is_girl_suffix_tag("cat_girl") is True
    assert is_girl_suffix_tag("girl") is False
    assert is_girl_suffix_tag("1girl") is False

    assert is_hair_color_tag("blonde_hair") is True
    assert is_hair_color_tag("blue_eyes") is False
    assert is_eye_color_tag("blue_eyes") is True

    assert is_series_tag("gacha_game") is True
    assert is_series_tag("fate_series") is True
    assert is_series_tag("hat") is False

    assert is_clothing_tag("dress") is True
    assert is_clothing_tag("no_clothing") is False
    assert is_clothing_tag("nude") is False

    assert is_textual_tag("speech bubble") is True
    assert is_textual_tag("watermark") is True
    assert is_textual_tag("1girl") is False

    assert is_subject_tag("solo") is True
    assert is_subject_tag("2girls") is True
    assert is_subject_tag("blonde_hair") is False


def test_removal_context_and_matching():
    synonym_lookup = build_synonym_lookup([{"1girl", "1female"}])
    removal_raw = ["bad_tag", "remove_*", "*_bad", "*commentary*", "c*a"]
    favorites_raw = ["remove_fav", "1girl"]

    context = build_removal_context(removal_raw, favorites_raw, synonym_lookup)

    assert tag_matches_removal("bad tag", context) is True
    assert tag_matches_removal("remove tag", context) is True
    assert tag_matches_removal("really bad", context) is True
    assert tag_matches_removal("some commentary here", context) is True
    assert tag_matches_removal("cta", context) is True
    assert tag_matches_removal("cbba", context) is True

    assert tag_matches_removal("1girl", context) is False


def test_post_rejected_by_filter():
    post = {
        "id": "123",
        "booru_name": "danbooru",
        "tags": "1girl, blonde_hair, blue_eyes, speech_bubble",
        "artist_tags": "drawn_by_unknown",
        "character_tags": "heroine",
        "copyright_tags": "cool_franchise",
    }

    # Toggles order:
    # 0: remove_artist, 1: remove_character, 2: remove_clothing, 3: remove_text,
    # 4: restrict_subject, 5: remove_furry, 6: remove_headwear, 7: remove_girl_suffix,
    # 8: preserve_hair_eye, 9: remove_series

    cache = {}

    rejected, reason = post_rejected_by_filter(
        post,
        filter_ctx=None,
        toggles=(True, False, False, False, False, False, False, False, False, False),
        base_colors=(set(), set()),
        allowed_subjects=set(),
        cache=cache,
        favorites_guard=set(),
    )
    assert rejected is True
    assert reason["rule"] == "artist"

    rejected, reason = post_rejected_by_filter(
        post,
        filter_ctx=None,
        toggles=(False, False, False, True, False, False, False, False, False, False),
        base_colors=(set(), set()),
        allowed_subjects=set(),
        cache=cache,
        favorites_guard=set(),
    )
    assert rejected is True
    assert reason["rule"] == "text"

    # Test preserve hair/eye colors (mismatch)
    rejected, reason = post_rejected_by_filter(
        post,
        filter_ctx=None,
        toggles=(False, False, False, False, False, False, False, False, True, False),
        base_colors=({"brown hair"}, {"blue eyes"}),
        allowed_subjects=set(),
        cache=cache,
        favorites_guard=set(),
    )
    assert rejected is True
    assert reason["rule"] == "hair-color-conflict"

    rejected, reason = post_rejected_by_filter(
        post,
        filter_ctx=None,
        toggles=(False, False, False, False, False, False, False, False, False, False),
        base_colors=(set(), set()),
        allowed_subjects=set(),
        cache=cache,
        favorites_guard=set(),
    )
    assert rejected is False


def test_post_rejected_by_filter_remove_furry():
    post = {"id": "1", "booru_name": "danbooru", "tags": "kemonomimi, 1girl, blonde_hair"}
    cache = {}
    rejected, reason = post_rejected_by_filter(
        post,
        filter_ctx=None,
        toggles=(False, False, False, False, False, True, False, False, False, False),
        base_colors=(set(), set()),
        allowed_subjects=set(),
        cache=cache,
        favorites_guard=set(),
    )
    assert rejected is True
    assert reason["rule"] == "furry"


def test_post_rejected_by_filter_remove_clothing():
    post = {"id": "2", "booru_name": "danbooru", "tags": "dress, 1girl, no_clothing"}
    cache = {}
    rejected, reason = post_rejected_by_filter(
        post,
        filter_ctx=None,
        toggles=(False, False, True, False, False, False, False, False, False, False),
        base_colors=(set(), set()),
        allowed_subjects=set(),
        cache=cache,
        favorites_guard=set(),
    )
    assert rejected is True
    assert reason["rule"] == "clothing"


def test_post_rejected_by_filter_remove_headwear():
    post = {"id": "3", "booru_name": "danbooru", "tags": "halo, 1girl, blonde_hair"}
    cache = {}
    rejected, reason = post_rejected_by_filter(
        post,
        filter_ctx=None,
        toggles=(False, False, False, False, False, False, True, False, False, False),
        base_colors=(set(), set()),
        allowed_subjects=set(),
        cache=cache,
        favorites_guard=set(),
    )
    assert rejected is True
    assert reason["rule"] == "headwear"


def test_post_rejected_by_filter_remove_girl_suffix():
    post = {"id": "4", "booru_name": "danbooru", "tags": "cat_girl, 1girl, girl, blonde_hair"}
    cache = {}
    rejected, reason = post_rejected_by_filter(
        post,
        filter_ctx=None,
        toggles=(False, False, False, False, False, False, False, True, False, False),
        base_colors=(set(), set()),
        allowed_subjects=set(),
        cache=cache,
        favorites_guard=set(),
    )
    assert rejected is True
    assert reason["rule"] == "girl-suffix"
    assert reason["tag"] == "cat_girl"


def test_post_rejected_by_filter_remove_character():
    post = {"id": "5", "booru_name": "danbooru", "tags": "1girl", "character_tags": "heroine"}
    cache = {}
    rejected, reason = post_rejected_by_filter(
        post,
        filter_ctx=None,
        toggles=(False, True, False, False, False, False, False, False, False, False),
        base_colors=(set(), set()),
        allowed_subjects=set(),
        cache=cache,
        favorites_guard=set(),
    )
    assert rejected is True
    assert reason["rule"] == "character"


def test_post_rejected_by_filter_favorites_guard():
    post = {"id": "6", "booru_name": "danbooru", "tags": "bad_tag, 1girl"}
    removal_raw = ["bad_tag"]
    ctx = build_removal_context(removal_raw, favorites_raw=[], synonym_lookup={})
    cache = {}
    # With favorites_guard containing "bad_tag" - should NOT be rejected
    rejected, reason = post_rejected_by_filter(
        post,
        filter_ctx=ctx,
        toggles=(False, False, False, False, False, False, False, False, False, False),
        base_colors=(set(), set()),
        allowed_subjects=set(),
        cache=cache,
        favorites_guard={"bad tag"},
    )
    assert rejected is False


def test_prompt_rules_and_filter_toggles_equivalence():
    from ranboorux.tag_pipeline import FilterToggles, PromptRules

    # 1. FilterToggles from legacy tuple
    t_tup = (True, False, True, False, False, True, False, True, False, True)
    t_obj = FilterToggles.from_legacy_tuple(t_tup)
    assert t_obj.remove_artist is True
    assert t_obj.remove_character is False
    assert t_obj.remove_clothing is True
    assert t_obj.remove_text is False
    assert t_obj.restrict_subject is False
    assert t_obj.remove_furry is True
    assert t_obj.remove_headwear is False
    assert t_obj.remove_girl_suffix is True
    assert t_obj.preserve_hair_eye is False
    assert t_obj.remove_series is True

    # 2. PromptRules from legacy tuple
    p_tup = (
        True,
        "Random",
        0.5,
        0.8,
        30,
        True,
        True,
        False,
        True,
        False,
        True,
        False,
        True,
        False,
        True,
    )
    p_obj = PromptRules.from_legacy_tuple(p_tup)
    assert p_obj.shuffle_tags is True
    assert p_obj.chaos_mode == "Random"
    assert p_obj.chaos_amount == 0.5
    assert p_obj.limit_tags_pct == 0.8
    assert p_obj.max_tags_count == 30
    assert p_obj.change_dash is True
    assert p_obj.remove_artist_tags is True
    assert p_obj.remove_character_tags is False
    assert p_obj.remove_clothing_tags is True
    assert p_obj.remove_text_tags is False
    assert p_obj.restrict_subject_tags is True
    assert p_obj.remove_furry_tags is False
    assert p_obj.remove_headwear_tags is True
    assert p_obj.preserve_hair_eye_colors is False
    assert p_obj.remove_series_tags is True

    # 3. post_rejected_by_filter equivalence between tuple and FilterToggles
    post = {"id": "1", "artist_tags": ["some_artist"], "tags": "1girl"}
    rej_tup, reason_tup = post_rejected_by_filter(
        post,
        filter_ctx=None,
        toggles=t_tup,
        base_colors=(set(), set()),
        allowed_subjects=set(),
        cache={},
        favorites_guard=set(),
    )
    rej_obj, reason_obj = post_rejected_by_filter(
        post,
        filter_ctx=None,
        toggles=t_obj,
        base_colors=(set(), set()),
        allowed_subjects=set(),
        cache={},
        favorites_guard=set(),
    )
    assert rej_tup == rej_obj is True
    assert reason_tup == reason_obj


def test_filter_rule_divergence_characterization():
    """Characterize current divergence between _process_single_prompt and post_rejected_by_filter.

    1. ' drawn by' tags: post_rejected_by_filter rejects them via remove_artist,
       whereas _process_single_prompt currently retains them unless present in artist_norm.
    2. girl-suffix tags: post_rejected_by_filter rejects them via remove_girl_suffix,
       whereas _process_single_prompt has no girl-suffix rule and retains them.
    """
    import scripts.ranbooru as ranbooru
    from ranboorux.tag_pipeline import FilterToggles, PromptRules, post_rejected_by_filter

    script = ranbooru.Script()

    # Case 1: " drawn by" artist tag without post metadata
    post_drawn_by = {"tags": "art_drawn_by_alice"}
    rej_drawn, reason_drawn = post_rejected_by_filter(
        post_drawn_by,
        filter_ctx=None,
        toggles=FilterToggles(remove_artist=True),
        base_colors=(set(), set()),
        allowed_subjects=set(),
        cache={},
        favorites_guard=set(),
    )
    assert rej_drawn is True
    assert reason_drawn["rule"] == "artist"

    prompt_out_drawn, _ = script._process_single_prompt(
        0,
        "art_drawn_by_alice",
        "",
        "",
        "",
        PromptRules(remove_artist_tags=True),
    )
    # CURRENT DIVERGENCE: _process_single_prompt keeps "art_drawn_by_alice"
    assert "art_drawn_by_alice" in prompt_out_drawn

    # Case 2: girl-suffix tag like "cat_girl"
    post_cat_girl = {"tags": "cat_girl"}
    rej_girl, reason_girl = post_rejected_by_filter(
        post_cat_girl,
        filter_ctx=None,
        toggles=FilterToggles(remove_girl_suffix=True),
        base_colors=(set(), set()),
        allowed_subjects=set(),
        cache={},
        favorites_guard=set(),
    )
    assert rej_girl is True
    assert reason_girl["rule"] == "girl-suffix"

    prompt_out_girl, _ = script._process_single_prompt(
        0,
        "cat_girl",
        "",
        "",
        "",
        PromptRules(remove_girl_suffix_tags=True),
    )
    # CURRENT DIVERGENCE: _process_single_prompt does not have girl-suffix rule yet and keeps "cat_girl"
    assert "cat_girl" in prompt_out_girl


