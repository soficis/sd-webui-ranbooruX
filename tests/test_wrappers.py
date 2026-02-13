def test_prompt_wrappers_match_module():
    import scripts.ranbooru as ranbooru
    from ranboorux import prompting

    prompt = "a, b, a, c"
    assert ranbooru.remove_repeated_tags(prompt) == prompting.remove_repeated_tags(prompt)
    assert ranbooru.limit_prompt_tags("a, b, c, d", 2, "Max") == prompting.limit_prompt_tags(
        "a, b, c, d", 2, "Max"
    )


def test_controlnet_wrapper_uses_integration(monkeypatch):
    import scripts.ranbooru as ranbooru

    script = ranbooru.Script()
    sentinel = object()
    monkeypatch.setattr(
        ranbooru.rb_controlnet_integration, "load_external_code", lambda root: sentinel
    )
    assert script._load_cn_external_code() is sentinel
