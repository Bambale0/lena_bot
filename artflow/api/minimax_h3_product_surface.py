"""User-surface rules for the unified MiniMax H3 family.

H3 provider routes are implementation details. The user chooses MiniMax H3 once;
media presence determines T2V / first-last-frame / omni-reference internally.
Therefore generic mode selectors must not be rendered for this family.
"""
from __future__ import annotations

from typing import Any

from api import minimax_h3_adapter as h3


def _force_single_public_mode(caps: Any) -> None:
    if not isinstance(caps, dict):
        return
    public = caps.get(h3.PUBLIC_MODEL)
    if isinstance(public, dict):
        public["modes"] = ["text"]
        public["auto_route_by_inputs"] = True


def install_minimax_h3_product_surface(routes: Any | None = None) -> None:
    """Expose one H3 button and no technical T2V/I2V/Ref2V choice."""
    h3.PUBLIC_CAPS["modes"] = ["text"]
    h3.PUBLIC_CAPS["auto_route_by_inputs"] = True
    _force_single_public_mode(h3.VIDEO_CAPS)

    try:
        from bot.keyboards import models as keyboard_models

        _force_single_public_mode(getattr(keyboard_models, "VIDEO_CAPS", None))
    except Exception:
        pass

    if routes is not None:
        _force_single_public_mode(getattr(routes, "VIDEO_CAPS", None))
