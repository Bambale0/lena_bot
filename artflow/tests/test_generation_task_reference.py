"""Provider references remain searchable and copyable in Telegram."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.handlers import balance, video_gen
from bot.utils.generation_reference import provider_task_reference
from db.models import GenerationType
from tests.factories import make_callback


@pytest.mark.parametrize("stored,raw", [
    ("kie-42", "kie-42"),
    ("neironych:uuid-42", "uuid-42"),
    ("nexus:uuid-42", "uuid-42"),
    ("comet:video:uuid-42", "uuid-42"),
    ("web:neironych:uuid-42", "uuid-42"),
    ("unknown:uuid-42", "unknown:uuid-42"),
    ("comet:uuid-42", "comet:uuid-42"),
])
def test_original_provider_id_is_copyable(stored, raw):
    assert provider_task_reference(stored) == f"\n\n🆔 ID задачи: <code>{raw}</code>"


@pytest.mark.parametrize("task_id", [None, "", " ", "neironych:"])
def test_no_reference_without_provider_id(task_id):
    assert provider_task_reference(task_id) == ""


def test_provider_id_cannot_inject_html():
    assert provider_task_reference('nexus:<x>&"') == (
        '\n\n🆔 ID задачи: <code>&lt;x&gt;&amp;&quot;</code>'
    )
    assert "Task ID:" in provider_task_reference("uuid", language="en")


@pytest.mark.asyncio
async def test_history_retains_full_ids_and_pages_without_splitting_entries():
    call = make_callback("menu:history")
    user = SimpleNamespace(id=42, language="ru")
    # Max-sized IDs and HTML escaping exceed one Telegram message.
    history = [SimpleNamespace(
        model="model<&>", prompt="<&>" * 30,
        task_id=f"neironych:{i}-" + "&" * 240,
        gen_type=GenerationType.image,
        status=SimpleNamespace(value="done"), credits_spent=2,
    ) for i in range(10)]
    session = AsyncMock()
    with patch.object(balance.repo, "get_user_history", AsyncMock(return_value=history)) as get:
        await balance.cb_history(call, session, user)
    get.assert_awaited_once_with(session, user.id, limit=10)
    pages = [call.message.edit_text.await_args.args[0]] + [
        invocation.args[0] for invocation in call.message.answer.await_args_list
    ]
    assert len(pages) > 1
    assert all(len(page) < 4096 for page in pages)
    for generation in history:
        reference = provider_task_reference(generation.task_id)
        assert sum(reference in page for page in pages) == 1
    assert "neironych:" not in "".join(pages)
    assert "model&lt;&amp;&gt;" in pages[0]


@pytest.mark.asyncio
async def test_video_acknowledgment_strips_internal_namespace():
    status = SimpleNamespace(edit_text=AsyncMock())
    await video_gen._show_video_task_started(status, "neironych:provider-uuid")
    assert "<code>provider-uuid</code>" in status.edit_text.await_args.args[0]
    assert "neironych:" not in status.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_video_acknowledgment_failure_does_not_abort_task():
    status = SimpleNamespace(edit_text=AsyncMock(side_effect=RuntimeError("Telegram unavailable")))
    await video_gen._show_video_task_started(status, "provider-uuid")
