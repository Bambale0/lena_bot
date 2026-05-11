from api.kie_model_specs import build_kie_input


def test_build_kie_input_single_qwen_i2i_reference_adds_image_url() -> None:
    resolved_model, inp = build_kie_input(
        model="qwen/image-to-image",
        prompt="A fantasy portrait",
        reference_urls="https://example.test/ref.jpg",
        params={"aspect_ratio": "1:1"},
    )

    assert resolved_model == "qwen/image-to-image"
    assert inp["image_urls"] == ["https://example.test/ref.jpg"]
    assert inp["image_url"] == "https://example.test/ref.jpg"
    assert inp["prompt"] == "A fantasy portrait"
    assert inp["aspect_ratio"] == "1:1"


def test_build_kie_input_multiple_qwen_i2i_references_still_sets_image_url() -> None:
    resolved_model, inp = build_kie_input(
        model="qwen/image-to-image",
        prompt="A fantasy portrait",
        reference_urls=["https://example.test/ref1.jpg", "https://example.test/ref2.jpg"],
        params={"aspect_ratio": "1:1"},
    )

    assert resolved_model == "qwen/image-to-image"
    assert inp["image_urls"] == ["https://example.test/ref1.jpg", "https://example.test/ref2.jpg"]
    assert inp["image_url"] == "https://example.test/ref1.jpg"
    assert inp["prompt"] == "A fantasy portrait"
    assert inp["aspect_ratio"] == "1:1"
