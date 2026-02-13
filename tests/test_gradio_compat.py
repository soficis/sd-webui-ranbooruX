def test_compat_helper_gradio3(active_gradio_version):
    if active_gradio_version != "3":
        return
    import gradio as gr

    import scripts.ranbooru as ranbooru

    result = ranbooru._gr_component_update(gr.Checkbox, value=True, visible=False)
    assert isinstance(result, dict)
    assert result["value"] is True
    assert result["visible"] is False


def test_compat_helper_gradio4(active_gradio_version):
    if active_gradio_version != "4":
        return
    import gradio as gr

    import scripts.ranbooru as ranbooru

    result = ranbooru._gr_component_update(gr.Checkbox, value=True, visible=False)
    assert result is not None
