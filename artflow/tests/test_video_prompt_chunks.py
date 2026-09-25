from __future__ import annotations

import html
from pathlib import Path

from bot.utils.telegram_ui import split_text_chunks


def test_split_text_chunks_preserves_entire_long_video_prompt() -> None:
    prompt = ("Первый блок с деталями камеры и движения. " * 180) + "\n\n" + (
        "Второй блок со светом, стилем и таймлайном. " * 180
    )
    clean = prompt.strip()

    chunks = split_text_chunks(prompt, max_chars=3000)

    assert len(chunks) > 1
    assert "".join(chunks) == clean
    assert all(0 < len(chunk) <= 3000 for chunk in chunks)


def test_video_prompt_handler_sends_every_chunk_without_truncation() -> None:
    handler = Path("bot/handlers/video_prompt.py").read_text(encoding="utf-8")

    assert "_MAX_PROMPT_MESSAGE_CHARS" not in handler
    assert "сокращённая версия" not in handler
    assert "split_text_chunks(prompt, max_chars=_MAX_PROMPT_CHUNK_CHARS)" in handler
    assert "for result_message in _result_messages(prompt, credits=credits):" in handler
    assert "await message.answer(result_message)" in handler
    assert "Часть {index}/{total}" in handler


def test_video_prompt_chunk_html_escaping_does_not_change_prompt_text() -> None:
    prompt = '<camera move="slow"> & foreground > background'
    chunks = split_text_chunks(prompt, max_chars=12)

    escaped = [html.escape(chunk, quote=False) for chunk in chunks]

    assert "".join(html.unescape(chunk) for chunk in escaped) == prompt
