"""Stable user-facing placement for the Seedance 2.5 model family.

Seedance 2.5 is registered dynamically by ``seedance25_adapter`` because the
legacy ``VideoModel`` enum predates the model. Capability registration alone is
not enough for Telegram: grouped keyboards render only model keys explicitly
listed in ``_VIDEO_GROUPS``. Keep the public product in the same groups as the
other Seedance models so a clean process restart cannot silently drop its
button.
"""
from __future__ import annotations


MODEL_KEY = "bytedance/seedance-2-5"
SEEDANCE_2_KEY = "bytedance/seedance-2"
PUBLIC_GROUPS = {"fast", "i2v"}


def _insert_before(keys: list[object], key: str, before: str) -> None:
    """Insert ``key`` once, preferably immediately before ``before``."""
    keys[:] = [item for item in keys if str(getattr(item, "value", item)) != key]
    try:
        index = next(
            idx
            for idx, item in enumerate(keys)
            if str(getattr(item, "value", item)) == before
        )
    except StopIteration:
        index = len(keys)
    keys.insert(index, key)


def install_seedance25_product_surface() -> None:
    """Make Seedance 2.5 a durable Telegram product, not only a runtime model."""
    try:
        from api import seedance25_adapter as seedance25
        from bot.keyboards import models as keyboard_models
    except Exception:
        return

    keyboard_models.VIDEO_CAPS[MODEL_KEY] = dict(seedance25.VIDEO_CAPS)
    keyboard_models.VIDEO_MODEL_DESC[MODEL_KEY] = (
        f"{seedance25.DISPLAY_NAME} · авто T2V/I2V/Reference · 4–30 сек · 480p/720p"
    )

    order = getattr(keyboard_models, "_VIDEO_MODEL_ORDER", None)
    if isinstance(order, list):
        _insert_before(order, MODEL_KEY, SEEDANCE_2_KEY)

    groups = getattr(keyboard_models, "_VIDEO_GROUPS", None)
    if isinstance(groups, list):
        for group_name, keys in groups:
            if group_name in PUBLIC_GROUPS and isinstance(keys, list):
                _insert_before(keys, MODEL_KEY, SEEDANCE_2_KEY)
