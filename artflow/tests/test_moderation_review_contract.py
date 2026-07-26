from __future__ import annotations

import pytest

from api import assistant_service, llm_provider_service as llm


@pytest.mark.asyncio
async def test_moderation_review_uses_dedicated_system_contract(monkeypatch) -> None:
    captured: list[llm.LLMRequest] = []

    async def fake_call(routes, request, **kwargs):
        captured.append(request)
        return llm.LLMResult(
            text="Вердикт: ручная проверка",
            provider=llm.LLMProvider.KIE_RESPONSES,
            model="gpt-5-4",
        )

    monkeypatch.setattr(assistant_service.llm, "call_with_fallbacks", fake_call)

    result = await assistant_service.generate_prompt_moderation_review(
        prompt_id=1,
        title="Test",
        description="Description",
        prompt_text="Ambiguous content",
        tags=["test"],
        model="gpt-image-2",
    )

    assert result == "Вердикт: ручная проверка"
    assert len(captured) == 1
    assert "AI-модератор" in captured[0].system_prompt
    assert "Вердикт" in captured[0].system_prompt
    assert "AI-ассистент внутри" not in captured[0].system_prompt
