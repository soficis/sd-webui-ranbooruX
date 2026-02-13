def _make_script():
    import scripts.ranbooru as ranbooru

    return ranbooru.Script()


def test_render():
    script = _make_script()
    text = script._render_platform_diagnostics()
    assert isinstance(text, str)
    assert text


def test_shows_version():
    script = _make_script()
    text = script._render_platform_diagnostics()
    assert "Gradio Version" in text


def test_shows_controlnet():
    script = _make_script()
    text = script._render_platform_diagnostics()
    assert "ControlNet External Code" in text


def test_shows_adetailer():
    script = _make_script()
    text = script._render_platform_diagnostics()
    assert "ADetailer Detected" in text


def test_toggle():
    script = _make_script()
    visible, markdown_update, button_update = script._toggle_platform_diagnostics(False)
    assert visible is True
    assert markdown_update is not None
    assert button_update is not None
