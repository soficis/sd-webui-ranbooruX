import types

from ranboorux.integrations.img2img_lifecycle import repeat_to_length, replace_processed_results


def test_repeat_to_length_repeats_lists_and_scalars():
    assert repeat_to_length("prompt", 3) == ["prompt", "prompt", "prompt"]
    assert repeat_to_length(["a", "b"], 5) == ["a", "b", "a", "b", "a"]
    assert repeat_to_length([], 2) == [None, None]
    assert repeat_to_length(["only"], 0) == []


def test_replace_processed_results_preserves_existing_list_objects():
    images = ["old"]
    infotexts = ["old info"]
    all_prompts = ["old prompt"]
    cached_images = ["old cached"]
    processed = types.SimpleNamespace(
        images=images,
        infotexts=infotexts,
        all_prompts=all_prompts,
        all_negative_prompts=[],
        all_seeds=[],
        all_subseeds=[],
        cached_images=cached_images,
    )

    replace_processed_results(
        processed,
        images=["img1", "img2"],
        prompts=["prompt1", "prompt2"],
        negative_prompts=["neg1", "neg2"],
        infotexts=["info1", "info2"],
        seed=10,
        subseed=20,
        width=64,
        height=96,
    )

    assert processed.images is images
    assert processed.images == ["img1", "img2"]
    assert processed.infotexts is infotexts
    assert processed.infotexts == ["info1", "info2"]
    assert processed.prompt == ["prompt1", "prompt2"]
    assert processed.negative_prompt == ["neg1", "neg2"]
    assert processed.seed == 10
    assert processed.subseed == 20
    assert processed.width == 64
    assert processed.height == 96
    assert processed.all_prompts is all_prompts
    assert processed.all_prompts == ["prompt1", "prompt2"]
    assert processed.all_negative_prompts == ["neg1", "neg2"]
    assert processed.all_seeds == [10, 11]
    assert processed.all_subseeds == [20, 21]
    assert processed.cached_images is cached_images
    assert processed.cached_images == ["img1", "img2"]
