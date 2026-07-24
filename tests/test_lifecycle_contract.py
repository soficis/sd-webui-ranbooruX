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

    secret_url = "https://site.test/api?api_key=secret&user_id=123&tags=1girl"

    class FakeHttp:
        def get_json(self, *_args, **_kwargs):
            raise RuntimeError(f"boom while fetching {secret_url}")

    booru = ranbooru.Booru("Gelbooru", "https://site.test")
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
