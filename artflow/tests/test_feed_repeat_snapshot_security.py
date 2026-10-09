from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.repeat_runtime import install_repeat_runtime, repeat_launch_context
from bot.handlers import repeat_safe
from db.models import GenerationType

SECRET = "private-author-secret-46c7"


class State:
    def __init__(self, **data):
        self.data = data

    async def clear(self):
        self.data = {}

    async def set_state(self, _state):
        pass

    async def update_data(self, **data):
        self.data.update(data)

    async def get_data(self):
        return dict(self.data)


def test_legacy_repeat_confirmation_hides_protected_lineage_even_without_snapshot_flag():
    text = repeat_safe._confirmation_text({"repeat_prompt": SECRET, "repeat_source_feed_gen_id": 77, "repeat_model_key": "nano-banana-2"})
    assert SECRET not in text


@pytest.mark.asyncio
async def test_open_protected_repeat_uses_generation_prompt_and_hides_it(monkeypatch):
    generation = SimpleNamespace(id=42, user_id=5, model="nano-banana-2", gen_type=GenerationType.image, prompt="safe generation edit", source_feed_gen_id=77, image_session_id=None, input_params={"prompt": SECRET})
    monkeypatch.setattr(repeat_safe, "get_repeat_task_by_any_id", AsyncMock(return_value=generation))
    monkeypatch.setattr(repeat_safe.repo, "resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=2)))
    state = State()
    call = SimpleNamespace(data="repeat_image_42", from_user=SimpleNamespace(id=777), answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()))
    await repeat_safe.open_repeat(call, AsyncMock(), state, SimpleNamespace(id=5, tg_id=777), AsyncMock())
    assert state.data["repeat_prompt_hidden"] is True
    assert state.data["repeat_prompt"] == generation.prompt
    assert SECRET not in call.message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_final_generation_inputs_override_unsafe_outer_repeat_snapshot():
    create = AsyncMock(return_value=SimpleNamespace(id=99))
    repository = SimpleNamespace(create_generation=create, update_generation_task=AsyncMock(), resolve_image_model_cost=AsyncMock(), get_image_session=AsyncMock(return_value=None))
    install_repeat_runtime(repository)
    final_refs = ["https://example.test/source.jpg", "https://example.test/user.jpg"]
    context = {"version": 1, "source_generation_id": 77, "prompt": "safe final prompt"}
    with repeat_launch_context(input_params_extra={"prompt": SECRET, "reference_images": final_refs[1:], "source_feed_gen_id": None, "hidden_prompt": False}):
        await repository.create_generation(
            AsyncMock(), 5, "nano-banana-2", GenerationType.image, "safe final prompt", 2,
            source_feed_gen_id=77, input_params={"reference_images": final_refs, "feed_remix_context": context},
        )
    payload = create.await_args.kwargs["input_params"]
    assert payload["prompt"] == "safe final prompt"
    assert payload["reference_images"] == final_refs
    assert payload["source_feed_gen_id"] == 77
    assert payload["hidden_prompt"] is True
    assert payload["feed_remix_context"] == context
    assert SECRET not in str(payload)


@pytest.mark.asyncio
async def test_repeat_user_edit_has_explicit_current_message_provenance():
    state = State(repeat_source_feed_gen_id=77, repeat_source_generation_id=42, repeat_prompt=SECRET, repeat_prompt_hidden=True)
    message = SimpleNamespace(text="make the coat white", answer=AsyncMock())
    await repeat_safe.save_repeat_prompt(message, state)
    assert state.data.get("repeat_feed_change_request") == "make the coat white"
    assert SECRET not in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_confirm_forwards_explicit_user_edit_and_creates_no_secret_session(monkeypatch):
    source = SimpleNamespace(id=42, user_id=5, gen_type=GenerationType.image, model="nano-banana-2", prompt=SECRET, source_feed_gen_id=77)
    state = State(
        repeat_source_generation_id=42, repeat_raw_task_id="42", repeat_confirm_key="safe-key",
        repeat_prompt="make the coat white", repeat_feed_change_request="make the coat white",
        repeat_source_feed_gen_id=77, repeat_reference_images=[], repeat_quality="2K",
    )
    create_session = AsyncMock(return_value=SimpleNamespace(id=123))
    launch = AsyncMock(return_value=True)
    monkeypatch.setattr(repeat_safe.repo, "get_generation_by_id", AsyncMock(return_value=source))
    monkeypatch.setattr(repeat_safe.repo, "create_image_session", create_session)
    monkeypatch.setattr(repeat_safe, "find_repeat_by_confirm_key", AsyncMock(return_value=None))
    monkeypatch.setattr(repeat_safe.image_gen, "_launch_session_generation", launch)
    call = SimpleNamespace(data="repeat_run_confirm_42", from_user=SimpleNamespace(id=777), answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()))
    await repeat_safe.confirm_repeat(call, AsyncMock(), state, SimpleNamespace(id=5, tg_id=777), AsyncMock())
    assert create_session.await_args.kwargs["base_prompt"] is None
    assert launch.await_args.kwargs["feed_change_request"] == "make the coat white"
    assert launch.await_args.kwargs["source_feed_gen_id"] == 77


@pytest.mark.parametrize("marker", ["source_feed_gen_id", "pending_source_feed_gen_id"])
def test_legacy_session_repeat_setup_hides_protected_prompt(marker):
    from bot.handlers import image_gen

    image_session = SimpleNamespace(model="qwen/image-edit", quality="basic", aspect_ratio="1:1", reference_file_id=None, reference_file_ids=None)
    text = image_gen._repeat_setup_text(image_session, SECRET, {marker: 77})
    assert SECRET not in text
    assert "скрыт" in text


def test_legacy_session_repeat_setup_keeps_ordinary_own_prompt():
    from bot.handlers import image_gen

    image_session = SimpleNamespace(model="qwen/image-edit", quality="basic", aspect_ratio="1:1", reference_file_id=None, reference_file_ids=None)
    assert "my own prompt" in image_gen._repeat_setup_text(image_session, "my own prompt", {})


@pytest.mark.asyncio
@pytest.mark.parametrize("protection", [{"source_feed_gen_id": 77}, {"input_params": {"hidden_prompt": True}}, {"input_params": '{"hidden_prompt": true}'}])
async def test_bot_history_hides_protected_prompt_preview(monkeypatch, protection):
    from bot.handlers import balance
    from db.models import GenerationStatus

    protected = SimpleNamespace(model="nano-banana-2", gen_type=GenerationType.image, status=GenerationStatus.done, prompt=SECRET, credits_spent=2, **protection)
    ordinary = SimpleNamespace(model="nano-banana-2", gen_type=GenerationType.image, status=GenerationStatus.done, prompt="my own normal prompt", credits_spent=2)
    monkeypatch.setattr(balance.repo, "get_user_history", AsyncMock(return_value=[protected, ordinary]))
    call = SimpleNamespace(message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()), answer=AsyncMock())
    await balance.cb_history(call, AsyncMock(), SimpleNamespace(id=5, language="ru"))
    text = call.message.edit_text.await_args.args[0]
    assert SECRET not in text
    assert "my own normal prompt" in text
    assert "скрыт" in text


@pytest.mark.parametrize("surface", ["web_card", "realtime"])
@pytest.mark.parametrize("protected", [False, True])
def test_public_failure_payload_cannot_echo_protected_author_prompt(surface, protected):
    from datetime import datetime, timezone

    from api.realtime import generation_event_payload
    from api.web.schemas import GenerationCard
    from db.models import GenerationStatus

    generation = SimpleNamespace(
        id=8, user_id=5, model="nano-banana-2", gen_type=GenerationType.image,
        prompt=SECRET, source_feed_gen_id=77 if protected else None,
        status=GenerationStatus.failed, result_url=None, result_urls=None,
        error_msg=f"Provider refused prompt: {SECRET}", credits_spent=0,
        created_at=datetime.now(timezone.utc), finished_at=None, is_public_feed=False,
    )
    payload = GenerationCard.from_generation(generation).model_dump() if surface == "web_card" else generation_event_payload(generation)
    if protected:
        assert SECRET not in str(payload)
        assert payload["error"]
    else:
        assert payload["error"] == generation.error_msg
