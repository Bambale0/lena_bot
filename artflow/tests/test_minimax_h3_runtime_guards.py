from api import minimax_h3_adapter as h3
from api.minimax_h3_runtime_guards import install_minimax_h3_runtime_guards


def test_h3_runtime_guard_normalizes_none_string_and_list_refs():
    install_minimax_h3_runtime_guards()

    assert h3._dedupe(None) == []
    assert h3._dedupe("https://example.test/one.jpg") == ["https://example.test/one.jpg"]
    assert h3._dedupe(
        [
            "https://example.test/one.jpg",
            "https://example.test/one.jpg",
            "https://example.test/two.jpg",
        ]
    ) == [
        "https://example.test/one.jpg",
        "https://example.test/two.jpg",
    ]
