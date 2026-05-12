from api.kie_model_specs import build_kie_input


def test_build_kie_input_single_qwen_i2i_reference_adds_image_url() -> None:
    resolved_model, inp = build_kie_input(
        model="qwen/image-to-image",
        prompt="A fantasy portrait",
        reference_urls="https://example.test/ref.jpg",
        params={"aspect_ratio": "1:1"},
    )

    assert resolved_model == "qwen/image-to-image"
    assert inp["image_url"] == "https://example.test/ref.jpg"
    assert inp["prompt"] == "A fantasy portrait"
    assert "aspect_ratio" not in inp


def test_build_kie_input_multiple_qwen_i2i_references_uses_first_image_only() -> None:
    resolved_model, inp = build_kie_input(
        model="qwen/image-to-image",
        prompt="A fantasy portrait",
        reference_urls=["https://example.test/ref1.jpg", "https://example.test/ref2.jpg"],
        params={"aspect_ratio": "1:1"},
    )

    assert resolved_model == "qwen/image-to-image"
    assert inp["image_url"] == "https://example.test/ref1.jpg"
    assert inp["prompt"] == "A fantasy portrait"
    assert "aspect_ratio" not in inp


def test_build_kie_input_qwen_image_edit_sets_image_url() -> None:
    resolved_model, inp = build_kie_input(
        model="qwen/image-edit",
        prompt="Edit this scene",
        reference_urls="https://example.test/edit.jpg",
        params={"aspect_ratio": "1:1", "n": 2},
    )

    assert resolved_model == "qwen/image-edit"
    assert inp["image_url"] == "https://example.test/edit.jpg"
    assert inp["prompt"] == "Edit this scene"
    assert "aspect_ratio" not in inp


def test_build_kie_input_qwen2_image_edit_sets_image_url() -> None:
    resolved_model, inp = build_kie_input(
        model="qwen2/image-edit",
        prompt="Change the colors",
        reference_urls="https://example.test/edit2.jpg",
        params={"aspect_ratio": "1:1"},
    )

    assert resolved_model == "qwen2/image-edit"
    assert inp["image_url"] == "https://example.test/edit2.jpg"
    assert inp["prompt"] == "Change the colors"
    assert inp["image_size"] == "1:1"
    assert "aspect_ratio" not in inp


def test_build_kie_input_qwen2_text_maps_unsupported_ratio_to_doc_shape() -> None:
    resolved_model, inp = build_kie_input(
        model="qwen2/text-to-image",
        prompt="Poster",
        params={"aspect_ratio": "2:3"},
    )

    assert resolved_model == "qwen2/text-to-image"
    assert inp["image_size"] == "3:4"
    assert "aspect_ratio" not in inp


def test_build_kie_input_qwen_image_edit_ignores_extra_refs_and_clamps_count() -> None:
    resolved_model, inp = build_kie_input(
        model="qwen/image-edit",
        prompt="Edit this scene",
        reference_urls=["https://example.test/edit-1.jpg", "https://example.test/edit-2.jpg"],
        params={"aspect_ratio": "16:9", "n": 9},
    )

    assert resolved_model == "qwen/image-edit"
    assert inp["image_url"] == "https://example.test/edit-1.jpg"
    assert inp["image_size"] == "landscape_16_9"
    assert inp["num_images"] == "4"
    assert "image_urls" not in inp


def test_build_kie_input_qwen2_image_edit_uses_single_reference_only() -> None:
    resolved_model, inp = build_kie_input(
        model="qwen2/image-edit",
        prompt="Change the colors",
        reference_urls=["https://example.test/edit2-a.jpg", "https://example.test/edit2-b.jpg"],
        params={"aspect_ratio": "9:16"},
    )

    assert resolved_model == "qwen2/image-edit"
    assert inp["image_url"] == "https://example.test/edit2-a.jpg"
    assert inp["image_size"] == "9:16"
    assert "image_urls" not in inp


def test_build_kie_input_grok_imagine_i2i_keeps_single_image_url_alias_for_first_ref() -> None:
    resolved_model, inp = build_kie_input(
        model="grok-imagine/image-to-image",
        prompt="Restyle this portrait",
        reference_urls=["https://example.test/grok-1.jpg", "https://example.test/grok-2.jpg"],
    )

    assert resolved_model == "grok-imagine/image-to-image"
    assert inp["image_urls"] == [
        "https://example.test/grok-1.jpg",
        "https://example.test/grok-2.jpg",
    ]
    assert inp["image_url"] == "https://example.test/grok-1.jpg"


def test_build_kie_input_wan_multi_ref_uses_input_urls_without_singular_alias() -> None:
    resolved_model, inp = build_kie_input(
        model="wan/2-7-image-pro",
        prompt="Blend the face from the first ref with the outfit from the second ref",
        reference_urls=["https://example.test/wan-1.jpg", "https://example.test/wan-2.jpg"],
        params={"resolution": "2K"},
    )

    assert resolved_model == "wan/2-7-image-pro"
    assert inp["input_urls"] == [
        "https://example.test/wan-1.jpg",
        "https://example.test/wan-2.jpg",
    ]
    assert "input_url" not in inp


def test_build_kie_input_nano_banana_variants_do_not_send_count() -> None:
    for model in ("nano-banana-2", "nano-banana-pro"):
        resolved_model, inp = build_kie_input(
            model=model,
            prompt="Studio portrait",
            params={"aspect_ratio": "1:1", "n": 6, "quality": "4K", "resolution": "4K"},
        )

        assert resolved_model == model
        assert "n" not in inp
        assert "num_images" not in inp
        assert inp["resolution"] == "4K"


def test_build_kie_input_grok_t2v_clamps_duration_to_provider_range() -> None:
    resolved_model, inp = build_kie_input(
        model="grok-imagine/text-to-video",
        prompt="beauty ad",
        params={"duration": 5, "grok_mode": "spicy", "resolution": "480p", "aspect_ratio": "16:9"},
    )

    assert resolved_model == "grok-imagine/text-to-video"
    assert inp["duration"] == "6"
    assert inp["mode"] == "spicy"
    assert inp["aspect_ratio"] == "16:9"


def test_build_kie_input_grok_i2v_omits_aspect_ratio_for_single_external_ref() -> None:
    resolved_model, inp = build_kie_input(
        model="grok-imagine/image-to-video",
        prompt="camera move",
        reference_urls=["https://example.test/ref.jpg"],
        params={"duration": 5, "grok_mode": "spicy", "aspect_ratio": "16:9", "resolution": "480p"},
    )

    assert resolved_model == "grok-imagine/image-to-video"
    assert inp["duration"] == "6"
    assert inp["mode"] == "normal"
    assert inp["image_urls"] == ["https://example.test/ref.jpg"]
    assert "aspect_ratio" not in inp


def test_build_kie_input_grok_i2v_keeps_aspect_ratio_for_multi_ref() -> None:
    resolved_model, inp = build_kie_input(
        model="grok-imagine/image-to-video",
        prompt="camera move",
        reference_urls=["https://example.test/ref-1.jpg", "https://example.test/ref-2.jpg"],
        params={"duration": 10, "grok_mode": "fun", "aspect_ratio": "16:9", "resolution": "720p"},
    )

    assert resolved_model == "grok-imagine/image-to-video"
    assert inp["duration"] == "10"
    assert inp["mode"] == "fun"
    assert inp["aspect_ratio"] == "16:9"


def test_build_kie_input_kling_t2v_enables_sound_by_default() -> None:
    resolved_model, inp = build_kie_input(
        model="kling-2.6/text-to-video",
        prompt="city night drive",
        params={"duration": 5, "aspect_ratio": "16:9"},
    )

    assert resolved_model == "kling-2.6/text-to-video"
    assert inp["sound"] is True
    assert inp["duration"] == "5"


def test_build_kie_input_seedance_enables_audio_by_default() -> None:
    resolved_model, inp = build_kie_input(
        model="bytedance/seedance-2",
        prompt="fashion ad",
        params={"duration": 5, "aspect_ratio": "16:9", "resolution": "720p"},
    )

    assert resolved_model == "bytedance/seedance-2"
    assert inp["generate_audio"] is True


def test_build_kie_input_wan_multiref_keeps_input_urls_without_singular_alias() -> None:
    resolved_model, inp = build_kie_input(
        model="wan/2-7-image-pro",
        prompt="Replace the background and keep the subject",
        reference_urls=[
            "https://example.test/wan-1.jpg",
            "https://example.test/wan-2.jpg",
        ],
        params={"resolution": "2K", "n": 1},
    )

    assert resolved_model == "wan/2-7-image-pro"
    assert inp["input_urls"] == [
        "https://example.test/wan-1.jpg",
        "https://example.test/wan-2.jpg",
    ]
    assert "input_url" not in inp


def test_build_kie_input_gpt_image_2_multiref_keeps_input_urls_without_singular_alias() -> None:
    resolved_model, inp = build_kie_input(
        model="gpt-image-2-image-to-image",
        prompt="Use both references",
        reference_urls=[
            "https://example.test/gpt-1.jpg",
            "https://example.test/gpt-2.jpg",
        ],
        params={"aspect_ratio": "16:9", "resolution": "2K"},
    )

    assert resolved_model == "gpt-image-2-image-to-image"
    assert inp["input_urls"] == [
        "https://example.test/gpt-1.jpg",
        "https://example.test/gpt-2.jpg",
    ]
    assert "input_url" not in inp


def test_build_kie_input_seedance_multiref_keeps_reference_image_urls_without_alias() -> None:
    resolved_model, inp = build_kie_input(
        model="bytedance/seedance-2",
        prompt="Animate this concept",
        reference_urls=[
            "https://example.test/seedance-1.jpg",
            "https://example.test/seedance-2.jpg",
        ],
        params={"duration": 5, "resolution": "720p", "aspect_ratio": "16:9"},
    )

    assert resolved_model == "bytedance/seedance-2"
    assert inp["reference_image_urls"] == [
        "https://example.test/seedance-1.jpg",
        "https://example.test/seedance-2.jpg",
    ]
    assert "reference_image_url" not in inp


def test_build_kie_input_happyhorse_multiref_keeps_image_url_alias() -> None:
    resolved_model, inp = build_kie_input(
        model="happyhorse/image-to-video",
        prompt="Animate both angles",
        reference_urls=[
            "https://example.test/hh-1.jpg",
            "https://example.test/hh-2.jpg",
        ],
        params={"duration": 5, "resolution": "720p"},
    )

    assert resolved_model == "happyhorse/image-to-video"
    assert inp["image_urls"] == [
        "https://example.test/hh-1.jpg",
        "https://example.test/hh-2.jpg",
    ]
    assert inp["image_url"] == "https://example.test/hh-1.jpg"


def test_build_kie_input_kling_26_motion_uses_provider_mode_values() -> None:
    resolved_model, inp = build_kie_input(
        model="kling-2.6/motion-control",
        prompt="Character follows the motion video",
        reference_urls=["https://example.test/person.jpg"],
        params={
            "resolution": "720p",
            "reference_video_url": "https://example.test/motion.mp4",
        },
    )

    assert resolved_model == "kling-2.6/motion-control"
    assert inp["input_urls"] == ["https://example.test/person.jpg"]
    assert inp["video_urls"] == ["https://example.test/motion.mp4"]
    assert inp["mode"] == "720p"
    assert inp["character_orientation"] == "image"


def test_build_kie_input_kling_30_motion_maps_legacy_pro_to_1080p() -> None:
    resolved_model, inp = build_kie_input(
        model="kling-3.0/motion-control",
        prompt="Character follows the motion video",
        reference_urls=["https://example.test/person.jpg"],
        params={
            "resolution": "pro",
            "reference_video_url": "https://example.test/motion.mp4",
        },
    )

    assert resolved_model == "kling-3.0/motion-control"
    assert inp["input_urls"] == ["https://example.test/person.jpg"]
    assert inp["video_urls"] == ["https://example.test/motion.mp4"]
    assert inp["mode"] == "1080p"
    assert inp["character_orientation"] == "image"
    assert inp["background_source"] == "input_video"
