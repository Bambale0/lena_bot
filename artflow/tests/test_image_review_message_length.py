"""Telegram review must never exceed the text transport limit."""
from html import unescape
from types import SimpleNamespace

import pytest

from bot.handlers.image_gen import _image_review_text


@pytest.mark.parametrize("prompt", [
    "❤️" * 5000,
    "<>&\\\"" * 2700,
    "Промпт " * 1000,
])
def test_image_review_truncates_preview_but_does_not_mutate_original_prompt(prompt):
    original = prompt
    session = SimpleNamespace(model="nano-banana-2.1", aspect_ratio="1:1", quality="2K", count=1)
    rendered = _image_review_text(image_session=session, prompt=prompt, credits=1, has_reference=True)
    assert prompt == original
    assert len(rendered) < 4096
    assert len(unescape(rendered)) < 4096
    assert "Промпт" in rendered
    assert "полный промпт сохранён" in rendered


def test_image_review_escapes_special_characters_without_truncating_short_prompt():
    session = SimpleNamespace(model="nano-banana-2.1", aspect_ratio="1:1", quality="2K", count=1)
    rendered = _image_review_text(image_session=session, prompt="A < B & C", credits=1, has_reference=False)
    assert "A &lt; B &amp; C" in rendered
    assert "полный промпт сохранён" not in rendered
