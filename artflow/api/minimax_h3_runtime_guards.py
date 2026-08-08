"""Runtime compatibility guards for MiniMax H3 media preparation."""
from __future__ import annotations

from typing import Any

from api import minimax_h3_adapter as h3


def install_minimax_h3_runtime_guards() -> None:
    """Normalize video_service's None/string/list reference return shapes.

    `_prepare_video_reference_urls` deliberately returns a string for one image,
    a list for multiple images, and None for no images. H3's family router always
    works on a list, so normalize that legacy shape before deduplication.
    """

    def dedupe(values: Any) -> list[str]:
        return list(dict.fromkeys(h3._urls(values)))

    h3._dedupe = dedupe
