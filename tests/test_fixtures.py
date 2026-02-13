import pytest


def test_gradio3_fixture(active_gradio_version):
    if active_gradio_version != "3":
        pytest.skip("Only relevant for Gradio 3 fixture mode")
    import gradio as gr

    assert hasattr(gr.Checkbox, "update")


def test_gradio4_fixture(active_gradio_version):
    if active_gradio_version != "4":
        pytest.skip("Only relevant for Gradio 4 fixture mode")
    import gradio as gr

    assert not hasattr(gr.Checkbox, "update")
