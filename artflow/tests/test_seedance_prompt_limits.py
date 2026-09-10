from pathlib import Path

import pytest
from pydantic import ValidationError

from api.miniapp_routes import VideoGenRequest
from api.video_prompt_limits import (
    SEEDANCE_20_PROMPT_MAX_CHARS,
    SEEDANCE_25_PROMPT_MAX_CHARS,
    append_telegram_seedance_prompt_chunk,
    seedance_prompt_max_chars,
    validate_seedance_prompt,
)


def test_seedance_kie_prompt_limits_are_exact_and_never_truncated() -> None:
    prompt20 = "a" * SEEDANCE_20_PROMPT_MAX_CHARS
    prompt25 = "b" * SEEDANCE_25_PROMPT_MAX_CHARS
    assert seedance_prompt_max_chars("bytedance/seedance-2") == 20_000
    assert seedance_prompt_max_chars("bytedance/seedance-2-fast") == 20_000
    assert seedance_prompt_max_chars("bytedance/seedance-2-mini") == 20_000
    assert seedance_prompt_max_chars("bytedance/seedance-2-5") == 30_000
    assert validate_seedance_prompt("bytedance/seedance-2", prompt20) == prompt20
    assert validate_seedance_prompt("bytedance/seedance-2-5", prompt25) == prompt25
    with pytest.raises(ValueError):
        validate_seedance_prompt("bytedance/seedance-2", prompt20 + "x")
    with pytest.raises(ValueError):
        validate_seedance_prompt("bytedance/seedance-2-5", prompt25 + "x")


def test_video_dto_allows_seedance25_maximum_but_rejects_more() -> None:
    body = VideoGenRequest(model="bytedance/seedance-2-5", prompt="x" * 30_000)
    assert len(body.prompt) == 30_000
    with pytest.raises(ValidationError):
        VideoGenRequest(model="bytedance/seedance-2-5", prompt="x" * 30_001)


def test_telegram_split_prompt_is_reassembled_verbatim() -> None:
    original = "A" * 4096 + "B" * 4096 + "C" * 123
    combined, waiting = append_telegram_seedance_prompt_chunk("bytedance/seedance-2", "", original[:4096])
    assert waiting is True
    combined, waiting = append_telegram_seedance_prompt_chunk("bytedance/seedance-2", combined, original[4096:8192])
    assert waiting is True
    combined, waiting = append_telegram_seedance_prompt_chunk("bytedance/seedance-2", combined, original[8192:])
    assert waiting is False
    assert combined == original


def test_miniapp_seedance_prompt_counter_uses_provider_limits() -> None:
    source = Path("webapp/src/features/generation-screen.tsx").read_text(encoding="utf-8")
    assert 'modelKey === SEEDANCE_25_MODEL) return 30000' in source
    assert 'SEEDANCE_20_MODELS.has(modelKey)) return 20000' in source
    assert 'maxLength={maxPromptLength}' in source
