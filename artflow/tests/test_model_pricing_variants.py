from core.model_pricing import split_pricing_variant_key


def test_split_pricing_variant_key_returns_runtime_model_and_options() -> None:
    assert split_pricing_variant_key(
        "bytedance/seedance-2-5__duration=10__resolution=720p"
    ) == (
        "bytedance/seedance-2-5",
        {"duration": "10", "resolution": "720p"},
    )


def test_split_pricing_variant_key_leaves_unknown_suffix_untouched() -> None:
    assert split_pricing_variant_key("provider/model__private=1") == (
        "provider/model__private=1",
        {},
    )
