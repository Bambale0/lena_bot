from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

import pytest

from bot.handlers import image_gen, marketplace, repeat_reference_marketplace
from db.models import ImageGenerationAction


class FakeState:
    def __init__(self, data: dict | None = None) -> None:
        self.data = dict(data or {})
        self.state = None

    async def get_data(self) -> dict:
        return dict(self.data)

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)

    async def clear(self) -> None:
        self.data = {}
        self.state = None

    async def set_state(self, state) -> None:
        self.state = state


def test_marketplace_multi_ref_handler_precedes_legacy_single_photo_handler() -> None:
    callbacks = [handler.callback for handler in marketplace.router.message.handlers]
    assert callbacks.index(repeat_reference_marketplace._collect_prompt_reference) < callbacks.index(
        marketplace.fsm_prompt_use_reference
    )


def test_uploaded_reference_screen_exposes_repeat_settings() -> None:
    markup = repeat_reference_marketplace._keyboard(uploaded=2, max_refs=10, feed_repeat=True)
    callbacks = {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    }

    assert "prompt_multi_ref:mode" in callbacks
    assert "prompt_multi_ref:ratio_menu" in callbacks
    assert "prompt_multi_ref:model_menu" in callbacks


def test_repeat_screen_text_shows_selected_settings() -> None:
    text = repeat_reference_marketplace._text(
        {
            "feed_use_prompt": "hidden",
            "prompt_multi_ref_file_ids": ["one", "two"],
            "prompt_multi_ref_max": 10,
            "prompt_multi_ref_ratio": "9:16",
            "use_model_key": "nano-banana-2",
        }
    )

    assert "Референсы: <b>2/10</b>" in text
    assert "Режим: <b>Фото → фото</b>" in text
    assert "Формат: <b>9:16</b>" in text
    assert "Нейросеть:" in text


def test_ratio_menu_does_not_offer_unsupported_portrait_ratio() -> None:
    assert repeat_reference_marketplace.repeat_references._repeat_ratio_options("qwen/image-edit") == []


@pytest.mark.asyncio
async def test_feed_repeat_collects_first_photo_without_starting_generation(monkeypatch) -> None:
    monkeypatch.setattr(repeat_reference_marketplace.image_gen, "_telegram_file_url", AsyncMock(side_effect=lambda _bot, fid: f"https://example.test/{fid}.jpg"))
    monkeypatch.setattr(repeat_reference_marketplace.repo, "get_public_feed_generation", AsyncMock(return_value=None))
    state = FakeState(
        {
            "feed_use_prompt": "hidden feed prompt",
            "feed_use_gen_id": 77,
            "use_model_key": "test/multi-ref",
        }
    )
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_id="ref-1", file_size=100)],
        answer=AsyncMock(),
    )

    with patch.object(
        repeat_reference_marketplace.repeat_references,
        "_repeat_max_refs",
        return_value=5,
    ), patch.object(
        repeat_reference_marketplace.image_gen,
        "_supports_img2img",
        return_value=True,
    ), patch.object(
        marketplace,
        "fsm_prompt_use_reference",
        AsyncMock(),
    ) as legacy:
        await repeat_reference_marketplace._collect_prompt_reference(
            message,
            AsyncMock(),
            SimpleNamespace(id=42),
            state,
            AsyncMock(),
        )

    assert state.data["prompt_multi_ref_file_ids"] == ["ref-1"]
    # The public source image consumes one of the five provider slots.
    assert state.data["prompt_multi_ref_max"] == 4
    legacy.assert_not_awaited()
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_single_ref_model_uses_legacy_flow() -> None:
    state = FakeState({"use_model_key": "test/single-ref"})
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_id="ref-1", file_size=100)],
        answer=AsyncMock(),
    )
    legacy = AsyncMock()

    with patch.object(
        repeat_reference_marketplace.repeat_references,
        "_repeat_max_refs",
        return_value=1,
    ), patch.object(
        repeat_reference_marketplace.image_gen,
        "_supports_img2img",
        return_value=True,
    ), patch.object(marketplace, "fsm_prompt_use_reference", legacy):
        await repeat_reference_marketplace._collect_prompt_reference(
            message,
            AsyncMock(),
            SimpleNamespace(id=42),
            state,
            AsyncMock(),
        )

    legacy.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("stale_state_user_id", [42, 99])
async def test_run_feed_repeat_passes_all_reference_urls(monkeypatch, stale_state_user_id) -> None:
    monkeypatch.setattr(repeat_reference_marketplace.repo, "get_public_feed_generation", AsyncMock(return_value=SimpleNamespace(
        id=77, user_id=99, is_public_feed=True, prompt="hidden feed prompt", gen_type="image",
        result_url="https://example.test/source.jpg", result_urls=None,
    )))
    state = FakeState(
        {
            "feed_use_prompt": "hidden feed prompt",
            "feed_use_gen_id": 77,
            "feed_use_user_id": stale_state_user_id,
            "feed_original_recipe_replay": True,
            "use_model_key": "nano-banana-pro",
            "prompt_multi_ref_ratio": "9:16",
            "prompt_multi_ref_file_ids": ["ref-1", "ref-2", "ref-3"],
            "prompt_multi_ref_max": 4,
        }
    )
    call = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())
    db_user = SimpleNamespace(id=42, credits=100)
    image_session = SimpleNamespace(id=123)
    launch = AsyncMock(return_value=True)

    with patch.object(
        repeat_reference_marketplace.repeat_references,
        "_repeat_max_refs",
        return_value=5,
    ), patch.object(
        repeat_reference_marketplace,
        "mirror_telegram_file",
        AsyncMock(
            side_effect=[
                "https://example.test/1.jpg",
                "https://example.test/2.jpg",
                "https://example.test/3.jpg",
            ]
        ),
    ), patch.object(
        repeat_reference_marketplace.repo,
        "resolve_image_model_cost",
        AsyncMock(return_value=SimpleNamespace(credits=2)),
    ), patch.object(
        repeat_reference_marketplace.repo,
        "create_image_session",
        AsyncMock(return_value=image_session),
    ) as create_session, patch.object(
        repeat_reference_marketplace.marketplace,
        "_default_quality_for_model",
        return_value="basic",
    ), patch.object(
        repeat_reference_marketplace.marketplace,
        "_default_count_for_model",
        return_value=1,
    ), patch.object(image_gen, "_launch_session_generation", launch):
        await repeat_reference_marketplace._run(
            call,
            AsyncMock(),
            db_user,
            state,
            AsyncMock(),
        )

    create_kwargs = create_session.await_args.kwargs
    assert create_kwargs["reference_file_ids"] == ["ref-1", "ref-2", "ref-3"]
    assert create_kwargs["mode"] == "image"
    assert create_kwargs["aspect_ratio"] == "9:16"
    assert state.data.get("repeat_aspect_ratio") == "9:16"

    launch_kwargs = launch.await_args.kwargs
    assert launch_kwargs["action_type"] == ImageGenerationAction.repeat
    assert launch_kwargs["parent_generation_id"] == 77
    assert launch_kwargs["source_feed_gen_id"] == 77
    assert launch_kwargs["reference_url"] == [
        "https://example.test/1.jpg",
        "https://example.test/2.jpg",
        "https://example.test/3.jpg",
    ]


@pytest.mark.asyncio
async def test_stale_hidden_marketplace_prompt_never_launches_multi_reference(monkeypatch) -> None:
    state = FakeState(
        {
            "use_prompt_id": 91,
            "use_model_key": "nano-banana-pro",
            "prompt_multi_ref_file_ids": ["ref-1"],
            "prompt_multi_ref_max": 2,
        }
    )
    call = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())
    prompt = SimpleNamespace(id=91)
    use_prompt = AsyncMock()
    create_session = AsyncMock()
    launch = AsyncMock()

    monkeypatch.setattr(
        repeat_reference_marketplace,
        "mirror_telegram_file",
        AsyncMock(return_value="https://example.test/ref.jpg"),
    )
    monkeypatch.setattr(
        repeat_reference_marketplace,
        "_reference_candidate",
        AsyncMock(
            return_value=(
                {"reference_urls": ["https://example.test/ref.jpg"]},
                2,
                [],
            )
        ),
    )
    monkeypatch.setattr(
        repeat_reference_marketplace,
        "public_url_is_available",
        lambda _url: True,
    )
    monkeypatch.setattr(
        image_gen,
        "_accept_reference_candidate",
        AsyncMock(return_value={"accepted": True}),
    )
    monkeypatch.setattr(
        repeat_reference_marketplace.repo,
        "resolve_image_model_cost",
        AsyncMock(return_value=SimpleNamespace(credits=2)),
    )
    monkeypatch.setattr(marketplace, "get_prompt_by_id", AsyncMock(return_value=prompt))
    visibility = AsyncMock(return_value=False)
    monkeypatch.setattr(marketplace, "_public_prompt_is_available", visibility)
    monkeypatch.setattr(marketplace, "use_prompt", use_prompt)
    monkeypatch.setattr(repeat_reference_marketplace.repo, "create_image_session", create_session)
    monkeypatch.setattr(image_gen, "_launch_session_generation", launch)

    await repeat_reference_marketplace._run(
        call,
        AsyncMock(),
        SimpleNamespace(id=42, credits=100),
        state,
        AsyncMock(),
    )

    visibility.assert_awaited_once_with(ANY, prompt, lock=True)
    use_prompt.assert_not_awaited()
    create_session.assert_not_awaited()
    launch.assert_not_awaited()
    assert call.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["nano-banana-pro", "nano-banana-2"])
@pytest.mark.parametrize("available", [False, True])
async def test_marketplace_run_uses_recipe_without_canonical_scene(monkeypatch, model, available):
    from db.models import GenerationType

    source_url = "https://example.test/expired-source.jpg"
    source = SimpleNamespace(id=77, user_id=99, is_public_feed=True, prompt="hidden feed prompt",
                             gen_type=GenerationType.image, result_url=source_url, result_urls=None)
    data = {
        "feed_use_prompt": "hidden feed prompt", "feed_use_gen_id": 77,
        "feed_use_user_id": 42, "feed_original_recipe_replay": True,
        "use_model_key": model, "prompt_multi_ref_file_ids": ["identity-file"],
        "image_session_id": 123,
    }
    state = FakeState(data)
    state.state = "previous-accepted-state"
    source_lookup = AsyncMock(return_value=source)
    create = AsyncMock(return_value=SimpleNamespace(id=456))
    archive = AsyncMock()
    launch = AsyncMock(return_value=True)
    monkeypatch.setattr(repeat_reference_marketplace.repo, "get_public_feed_generation", source_lookup)
    monkeypatch.setattr(repeat_reference_marketplace.image_gen, "canonical_generation_result_url", lambda _source: source_url)
    monkeypatch.setattr(repeat_reference_marketplace, "public_url_is_available", lambda url: available if url == source_url else True, raising=False)
    monkeypatch.setattr(repeat_reference_marketplace, "mirror_telegram_file", AsyncMock(return_value="https://example.test/identity.jpg"))
    monkeypatch.setattr(repeat_reference_marketplace.repo, "create_image_session", create)
    monkeypatch.setattr(repeat_reference_marketplace.repo, "archive_active_image_sessions", archive)
    monkeypatch.setattr(repeat_reference_marketplace.repo, "resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=2)))
    monkeypatch.setattr(image_gen, "_launch_session_generation", launch)
    call = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())
    await repeat_reference_marketplace._run(call, AsyncMock(), SimpleNamespace(id=42, credits=100), state, AsyncMock())
    create.assert_awaited_once()
    launch.assert_awaited_once()
    assert launch.await_args.kwargs["reference_url"] == ["https://example.test/identity.jpg"]
    assert source_url not in str(launch.await_args)
