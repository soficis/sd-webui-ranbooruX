import types

from ranboorux.run_options import UI_ARGUMENT_FIELDS


def _args(**overrides):
    defaults = {
        "enabled": False,
        "tags": "1girl",
        "booru": "danbooru",
        "gelbooru_api_key": "",
        "gelbooru_user_id": "",
        "gelbooru_compat_base_url": "",
        "remove_bad_tags": True,
        "max_pages": 1,
        "change_dash": False,
        "same_prompt": False,
        "fringe_benefits": True,
        "remove_tags": "",
        "use_img2img": False,
        "denoising": 0.75,
        "use_last_img": False,
        "change_background": "Don't Change",
        "change_color": "Don't Change",
        "shuffle_tags": False,
        "post_id": "",
        "mix_prompt": False,
        "mix_amount": 2,
        "chaos_mode": "None",
        "chaos_amount": 0.5,
        "limit_tags": 1.0,
        "max_tags": 0,
        "sorting_order": "Random",
        "mature_rating": "All",
        "lora_folder": "",
        "lora_amount": 1,
        "lora_min": 0.6,
        "lora_max": 1.0,
        "lora_enabled": False,
        "lora_custom_weights": "",
        "lora_lock_prev": False,
        "use_ip": False,
        "use_search_txt": False,
        "use_remove_txt": False,
        "choose_search_txt": "",
        "choose_remove_txt": "",
        "search_refresh_btn": None,
        "remove_refresh_btn": None,
        "crop_center": False,
        "enable_adetailer_support": False,
        "use_same_seed": False,
        "reuse_cached_posts": False,
        "use_cache": False,
        "log_prompt_sources": False,
        "remove_artist_tags": False,
        "remove_character_tags": False,
        "remove_clothing_tags": False,
        "remove_text_tags": False,
        "restrict_subject_tags": False,
        "remove_furry_tags": False,
        "remove_headwear_tags": False,
        "remove_girl_suffix_tags": False,
        "preserve_hair_eye_colors": False,
        "remove_series_tags": False,
        "use_tag_catalog": True,
        "catalog_path": "",
        "lora_auto_detect_pony": True,
        "lora_detected_loras": [],
        "anima_auto_detect": False,
        "anima_tune_img2img": True,
        "controlnet_weight": 1.0,
        "lora_blacklist": [],
    }
    defaults.update(overrides)
    return [defaults[field] for field in UI_ARGUMENT_FIELDS]


def _processing():
    return types.SimpleNamespace(
        prompt="base_prompt",
        negative_prompt="",
        seed=10,
        subseed=20,
        n_iter=1,
        batch_size=1,
        steps=30,
        cfg_scale=7.0,
        width=64,
        height=64,
        script_args=[],
        scripts=types.SimpleNamespace(alwayson_scripts=[], scripts=[]),
    )


def test_disabled_run_releases_processing_guards(stub_modules):
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()
    p = _processing()

    script.before_process(p, *_args(enabled=False))

    assert getattr(script.__class__, "_ranbooru_global_processing", False) is False
    assert not hasattr(script, "_current_processing_key")


def test_tags_only_run_updates_prompt_without_img2img(monkeypatch, stub_modules):
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()
    p = _processing()

    class FakeApi:
        booru_name = "Danbooru"
        headers = {}

        def get_posts(self, **_kwargs):
            return [{"id": 1, "tags": "1girl blonde_hair", "file_url": "https://img.test/a.png"}]

    monkeypatch.setattr(script, "_get_booru_api", lambda *_args, **_kwargs: FakeApi())

    script.before_process(p, *_args(enabled=True, use_img2img=False, use_ip=False))
    processed = types.SimpleNamespace(images=["txt2img"], seed=10, subseed=20)
    script.postprocess(p, processed)

    assert "base_prompt" in p.prompt
    assert "1girl" in p.prompt
    assert getattr(script.__class__, "_ranbooru_global_processing", False) is False


def test_failed_fetch_releases_processing_guards(monkeypatch, stub_modules):
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()
    p = _processing()

    class FailingApi:
        booru_name = "Danbooru"
        headers = {}

        def get_posts(self, **_kwargs):
            raise ranbooru.BooruError("boom")

    monkeypatch.setattr(script, "_get_booru_api", lambda *_args, **_kwargs: FailingApi())

    script.before_process(p, *_args(enabled=True))

    assert getattr(script.__class__, "_ranbooru_global_processing", False) is False
    assert not hasattr(script, "_current_processing_key")
    assert not hasattr(p, "_ranbooru_already_processing")


def test_argument_parse_failure_releases_processing_guards(stub_modules):
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()
    p = _processing()

    script.before_process(p, *([None] * (len(UI_ARGUMENT_FIELDS) - 1)))

    assert getattr(script.__class__, "_ranbooru_global_processing", False) is False
    assert not hasattr(script, "_current_processing_key")
    assert not hasattr(p, "_ranbooru_already_processing")


def test_booru_error_redacts_credential_url(stub_modules):
    import scripts.ranbooru as ranbooru
    from ranboorux.boorus import Booru

    secret_url = "https://site.test/api?api_key=secret&user_id=123&tags=1girl"

    class FakeHttp:
        def get_json(self, *_args, **_kwargs):
            raise RuntimeError(f"boom while fetching {secret_url}")

    booru = Booru("Gelbooru", "https://site.test")
    booru.http = FakeHttp()

    try:
        booru._fetch_data(secret_url)
    except ranbooru.BooruError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected BooruError")

    assert "secret" not in message
    assert "123" not in message
    assert "api_key=<redacted>" in message


def test_sequential_jobs_do_not_reuse_previous_prompt(monkeypatch, stub_modules):
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()

    class FakeApi:
        booru_name = "Danbooru"
        headers = {}

        def __init__(self, tag):
            self.tag = tag

        def get_posts(self, **_kwargs):
            return [{"id": 1, "tags": self.tag, "file_url": "https://img.test/a.png"}]

    tags = iter(["first_tag", "second_tag"])
    monkeypatch.setattr(script, "_get_booru_api", lambda *_args, **_kwargs: FakeApi(next(tags)))

    first = _processing()
    script.before_process(first, *_args(enabled=True))
    script.postprocess(first, types.SimpleNamespace(images=["a"], seed=10, subseed=20))

    second = _processing()
    script.before_process(second, *_args(enabled=True))
    script.postprocess(second, types.SimpleNamespace(images=["b"], seed=10, subseed=20))

    assert "first_tag" in first.prompt
    assert "second_tag" in second.prompt
    assert "first_tag" not in second.prompt


def test_initialize_seeds_policies():
    import scripts.ranbooru as ranbooru

    # Policy 1: Internal img2img (overwrite=True, mirror_aliases=True)
    p1 = types.SimpleNamespace(seed=-1, subseed=-1, n_iter=2, batch_size=2)
    s1, ss1 = ranbooru.Script._initialize_seeds(p1, overwrite=True, mirror_aliases=True)
    assert p1.seed == s1 and s1 != -1
    assert p1.subseed == ss1 and ss1 != -1
    assert len(p1.all_seeds) == 4
    assert p1.all_seeds == [s1, s1 + 1, s1 + 2, s1 + 3]
    assert p1.all_subseeds == [ss1, ss1 + 1, ss1 + 2, ss1 + 3]
    assert p1.seeds == p1.all_seeds
    assert p1.subseeds == p1.all_subseeds

    # Policy 2: Duplicate guard (overwrite=False, mirror_aliases=False)
    p2_existing = types.SimpleNamespace(
        seed=10,
        subseed=20,
        n_iter=1,
        batch_size=2,
        all_seeds=[100, 101],
        all_subseeds=[200, 201],
    )
    ranbooru.Script._initialize_seeds(p2_existing, overwrite=False, mirror_aliases=False)
    assert p2_existing.all_seeds == [100, 101]
    assert p2_existing.all_subseeds == [200, 201]
    assert not hasattr(p2_existing, "seeds")
    assert not hasattr(p2_existing, "subseeds")

    p2_missing = types.SimpleNamespace(
        seed=10,
        subseed=20,
        n_iter=1,
        batch_size=2,
        all_seeds=None,
        all_subseeds=None,
    )
    ranbooru.Script._initialize_seeds(p2_missing, overwrite=False, mirror_aliases=False)
    assert p2_missing.all_seeds == [10, 11]
    assert p2_missing.all_subseeds == [20, 21]
    assert not hasattr(p2_missing, "seeds")

    # Policy 3: Main before_process run (overwrite=True, mirror_aliases="if_missing")
    p3 = types.SimpleNamespace(
        seed=50,
        subseed=60,
        n_iter=1,
        batch_size=2,
        seeds=[999],
    )
    s3, ss3 = ranbooru.Script._initialize_seeds(p3, overwrite=True, mirror_aliases="if_missing")
    assert p3.all_seeds == [50, 51]
    assert p3.all_subseeds == [60, 61]
    assert p3.seeds == [999]  # Existing alias not overwritten
    assert p3.subseeds == [60, 61]  # Missing alias mirrored


def test_bail_releases_guards():
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()
    p = types.SimpleNamespace()

    # Set guards
    key = f"_ranbooru_processing_{id(p)}"
    setattr(script, key, True)
    script._current_processing_key = key
    setattr(ranbooru.Script, "_ranbooru_global_processing", True)
    setattr(p, "_ranbooru_already_processing", True)
    script._current_processing_object = p

    # Call _bail
    script._bail(p, use_cache=True, reason="Test bail reason")

    # Assert guards are released
    assert not hasattr(script, key)
    assert not getattr(ranbooru.Script, "_ranbooru_global_processing", False)
    assert not getattr(p, "_ranbooru_already_processing", False)
    assert not hasattr(script, "_current_processing_object")


def test_before_process_comments_on_success_and_failure(monkeypatch, stub_modules):
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()

    # Success case
    class FakeApi:
        booru_name = "danbooru"

        def get_posts(self, **_kwargs):
            return [{"id": 1, "tags": "1girl solo watermark", "file_url": "https://img.test/a.png"}]

    monkeypatch.setattr(script, "_get_booru_api", lambda *_args, **_kwargs: FakeApi())

    p_success = _processing()
    p_success.comments = []
    p_success.comment = lambda text: p_success.comments.append(text)

    script.before_process(p_success, *_args(enabled=True, booru="danbooru", remove_bad_tags=True))

    assert len(p_success.comments) == 1
    assert (
        p_success.comments[0]
        == "RanbooruX: danbooru · 1 post(s) · 1 tag(s) removed by filters (batch total) · catalog bundled"
    )

    # Failure case
    p_fail = _processing()
    p_fail.comments = []
    p_fail.comment = lambda text: p_fail.comments.append(text)

    def fail_fetch(*_args, **_kwargs):
        raise RuntimeError("network failure contacting booru")

    monkeypatch.setattr(script, "_fetch_booru_posts", fail_fetch)

    script.before_process(p_fail, *_args(enabled=True, booru="danbooru"))

    assert len(p_fail.comments) == 1
    fail_comment = p_fail.comments[0]
    assert fail_comment.startswith("RanbooruX: network failure contacting booru")
    assert "Generated with your prompt unchanged." in fail_comment


def test_before_process_failure_after_prompt_applied_says_so(monkeypatch, stub_modules):
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()

    class FakeApi:
        booru_name = "danbooru"

        def get_posts(self, **_kwargs):
            return [{"id": 1, "tags": "1girl solo", "file_url": "https://img.test/a.png"}]

    monkeypatch.setattr(script, "_get_booru_api", lambda *_args, **_kwargs: FakeApi())

    def fail_late(*_args, **_kwargs):
        raise RuntimeError("img2img prep exploded")

    monkeypatch.setattr(script, "_prepare_img2img_pass", fail_late)

    p = _processing()
    p.comments = []
    p.comment = lambda text: p.comments.append(text)

    script.before_process(p, *_args(enabled=True, booru="danbooru"))

    assert len(p.comments) == 1
    assert p.comments[0].startswith("RanbooruX: img2img prep exploded.")
    assert "The booru prompt was already applied" in p.comments[0]
    assert "unchanged" not in p.comments[0]


def test_note_run_failure_handles_empty_reason(stub_modules):
    import scripts.ranbooru as ranbooru

    class P:
        def __init__(self):
            self.notes = []

        def comment(self, text):
            self.notes.append(text)

    p = P()
    ranbooru._note_run_failure(p, "")
    ranbooru._note_run_failure(p, "boom.", "Generated with your prompt unchanged.")
    assert p.notes == [
        "RanbooruX: unexpected error.",
        "RanbooruX: boom. Generated with your prompt unchanged.",
    ]


def _img2img_run(monkeypatch, posts, fetched):
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()
    p = _processing()
    p.comments = []
    steps_before = p.steps

    class FakeApi:
        booru_name = "Danbooru"
        headers = {}

        def get_posts(self, **_kwargs):
            return posts

    seen = []

    def fake_fetch(selected_posts, *_args, **_kwargs):
        seen.extend(selected_posts)
        return list(fetched)

    monkeypatch.setattr(script, "_get_booru_api", lambda *_args, **_kwargs: FakeApi())
    monkeypatch.setattr(script, "_fetch_images", fake_fetch)
    monkeypatch.setattr(script, "_install_preview_guard", lambda: None)
    monkeypatch.setattr(script, "_set_preview_guard", lambda *_args, **_kwargs: None)

    script.before_process(p, *_args(enabled=True, use_img2img=True, use_ip=False))
    return ranbooru, script, p, steps_before, seen


def test_img2img_without_source_image_runs_normal_generation(monkeypatch, stub_modules):
    posts = [{"id": 1, "tags": "1girl blonde_hair"}]
    ranbooru, script, p, steps_before, _ = _img2img_run(monkeypatch, posts, fetched=[])

    # A one-step placeholder pass must not become the user's only output.
    assert script.run_img2img_pass is False
    assert p.steps == steps_before
    assert ranbooru.IMG2IMG_NO_SOURCE_NOTE in p.comments


def test_img2img_ignores_posts_without_downloadable_image(monkeypatch, stub_modules):
    posts = [
        {"id": 1, "tags": "1girl blonde_hair"},
        {"id": 2, "tags": "1girl red_hair", "file_url": "https://img.test/b.png"},
    ]
    _, script, _, _, seen = _img2img_run(monkeypatch, posts, fetched=[object()])

    assert [post["id"] for post in seen] == [2]
    assert script.run_img2img_pass is True
