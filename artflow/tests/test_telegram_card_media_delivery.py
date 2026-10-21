from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendDocument, SendVideo
from aiogram.types import Chat, FSInputFile, Message

from api import public_files
from bot.handlers import feed, marketplace
from db.models import GenerationType


def video_card(url):
    return SimpleNamespace(
        generation=SimpleNamespace(
            id=46718,
            user_id=7,
            gen_type=GenerationType.video,
            result_url=url,
            model="bytedance/seedance-2-5",
            likes_count=0,
            shares_count=0,
        ),
        username=None,
        full_name="Synthetic",
        aspect_ratio="9:16",
    )


@pytest.mark.asyncio
async def test_feed_uploads_surviving_large_local_video_without_public_url_fetch(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    path = tmp_path / "result.mp4"
    with path.open("wb") as f:
        f.truncate(21 * 1024 * 1024)
    transport = AsyncMock()
    holder = Message(message_id=1, date=0, chat=Chat(id=7, type="private")).as_(transport)
    await feed._show_feed_card(
        holder=holder,
        card=video_card("https://example.test/static/upload/result.mp4"),
        source="all",
        index=0,
        total=1,
    )
    transport.assert_awaited_once()
    method = transport.await_args.args[0]
    assert isinstance(method, SendVideo)
    assert isinstance(method.video, FSInputFile)
    assert method.video.path == path
    assert transport.await_args.kwargs == {"request_timeout": 90}
    assert "request_timeout" not in method.model_extra


@pytest.mark.asyncio
async def test_failed_local_video_preview_still_delivers_original_document(monkeypatch, tmp_path):
    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    (tmp_path / "result.mp4").write_bytes(b"synthetic-mp4")
    transport = AsyncMock(side_effect=[
        TelegramBadRequest(method="sendVideo", message="upload failed"), None,
    ])
    holder = Message(message_id=1, date=0, chat=Chat(id=7, type="private")).as_(transport)
    await feed._show_feed_card(
        holder=holder,
        card=video_card("https://example.test/static/upload/result.mp4"),
        source="all",
        index=0,
        total=1,
    )
    assert transport.await_count == 2
    method = transport.await_args.args[0]
    assert isinstance(method, SendDocument)
    assert isinstance(method.document, FSInputFile)
    assert all(call.kwargs == {"request_timeout": 90} for call in transport.await_args_list)
    assert "request_timeout" not in method.model_extra



@pytest.mark.asyncio
async def test_missing_preview_uses_honest_text_card_instead_of_one_pixel_image(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    holder = SimpleNamespace(
        photo=None, answer_photo=AsyncMock(), edit_text=AsyncMock(), answer=AsyncMock()
    )
    prompt = SimpleNamespace(
        id=2,
        title="Synthetic prompt",
        description="Description",
        tags=[],
        uses_count=0,
        likes=0,
        preview_url="https://example.test/static/upload/missing.jpg",
    )
    await marketplace._show_prompt_card(
        holder=holder, prompt=prompt, source="top", index=0, total=1
    )
    holder.answer_photo.assert_not_awaited()
    assert "Превью недоступно" in holder.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_failed_remote_preview_is_not_relabelled_onto_previous_photo():
    holder = SimpleNamespace(
        photo=[object()],
        edit_media=AsyncMock(
            side_effect=TelegramBadRequest(
                method="editMessageMedia", message="failed to get HTTP URL content"
            )
        ),
        answer_photo=AsyncMock(
            side_effect=TelegramBadRequest(
                method="sendPhoto", message="failed to get HTTP URL content"
            )
        ),
        edit_text=AsyncMock(),
        answer=AsyncMock(),
    )
    prompt = SimpleNamespace(
        id=2,
        title="Synthetic prompt",
        description="Description",
        tags=[],
        uses_count=0,
        likes=0,
        preview_url="https://provider.test/expired.jpg",
    )
    await marketplace._show_prompt_card(
        holder=holder, prompt=prompt, source="top", index=0, total=1
    )
    holder.answer.assert_awaited_once()
    assert "Превью недоступно" in holder.answer.await_args.args[0]
    holder.edit_text.assert_not_awaited()


@pytest.mark.parametrize("kind", ["oversized", "symlink"])
def test_local_media_upload_rejects_oversize_and_path_escape(tmp_path, monkeypatch, kind):
    from bot.utils.telegram_media import local_media_path

    root = tmp_path / "public"
    root.mkdir()
    monkeypatch.setattr(public_files, "UPLOAD_ROOT", root)
    path = root / "result.mp4"
    if kind == "oversized":
        with path.open("wb") as f:
            f.truncate(51 * 1024 * 1024)
    else:
        private = tmp_path / "private"
        private.write_bytes(b"private bytes")
        path.symlink_to(private)
    assert local_media_path("https://example.test/static/upload/result.mp4") is None


@pytest.mark.asyncio
async def test_external_feed_video_edits_existing_card_in_place():
    holder = SimpleNamespace(
        photo=None, video=object(), edit_media=AsyncMock(), answer_video=AsyncMock(),
        answer=AsyncMock(),
    )
    url = "https://provider.test/video.mp4"
    await feed._show_feed_card(
        holder=holder, card=video_card(url), source="all", index=1, total=2,
    )
    holder.edit_media.assert_awaited_once()
    assert holder.edit_media.await_args.kwargs["media"].media == url
    holder.answer_video.assert_not_awaited()
    holder.answer.assert_not_awaited()
