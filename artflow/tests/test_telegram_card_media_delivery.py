from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile

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
    holder = SimpleNamespace(photo=None, video=None, answer_video=AsyncMock(), answer=AsyncMock())
    await feed._show_feed_card(
        holder=holder,
        card=video_card("https://example.test/static/upload/result.mp4"),
        source="all",
        index=0,
        total=1,
    )
    media = holder.answer_video.await_args.args[0]
    assert isinstance(media, FSInputFile)
    assert media.path == path
    holder.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_local_video_preview_still_delivers_original_document(monkeypatch, tmp_path):
    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    (tmp_path / "result.mp4").write_bytes(b"synthetic-mp4")
    holder = SimpleNamespace(
        photo=None,
        video=None,
        answer_video=AsyncMock(
            side_effect=TelegramBadRequest(
                method="sendVideo", message="failed to get HTTP URL content"
            )
        ),
        answer_document=AsyncMock(),
        answer=AsyncMock(),
    )
    await feed._show_feed_card(
        holder=holder,
        card=video_card("https://example.test/static/upload/result.mp4"),
        source="all",
        index=0,
        total=1,
    )
    holder.answer_document.assert_awaited_once()
    assert isinstance(holder.answer_document.await_args.args[0], FSInputFile)
    holder.answer.assert_not_awaited()


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
