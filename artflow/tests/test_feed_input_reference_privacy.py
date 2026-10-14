"""Publishing output media must not publish the author's input photos."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from api import miniapp_routes
from api.miniapp_auth import get_miniapp_user
from api.web import feed as web_feed
from api.web.deps import get_web_user_or_none
from bot.handlers import repeat_safe
from bot.utils.feed_media import feed_source_output_id
from db import repository as repo
from db.models import (
    Base,
    Generation,
    GenerationStatus,
    GenerationType,
    ImageSession,
    ImageSessionStatus,
    User,
)
from db.session import get_session
from main import app

INPUT_REFS = [
    "https://example.test/static/upload/references/synthetic-telegram-face.jpg",
    "https://input.example.test/synthetic-private-object.jpg",
]
OUTPUTS = ["https://output.example.test/generated-1.jpg", "https://output.example.test/generated-2.jpg"]
SECRET_PROMPT = "synthetic-private-author-prompt"


class LocalSession:
    """Exercise real repository SQL against isolated SQLite, without external services."""

    def __init__(self, sync: Session) -> None:
        self.sync = sync

    def add(self, value) -> None:
        self.sync.add(value)

    async def execute(self, statement):
        return self.sync.execute(statement)

    async def commit(self) -> None:
        self.sync.commit()

    async def refresh(self, value) -> None:
        self.sync.refresh(value)


@pytest.fixture
async def published_work(monkeypatch, tmp_path):
    local_reference = tmp_path / "references" / "synthetic-telegram-face.jpg"
    local_reference.parent.mkdir()
    local_reference.write_bytes(b"synthetic-input-photo")
    monkeypatch.setattr("api.public_files.UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr("api.public_files.settings.STATIC_UPLOAD_URL_PATH", "/static/upload")
    mirror = AsyncMock(side_effect=lambda url, **kwargs: url)
    monkeypatch.setattr(web_feed, "mirror_url", mirror)
    # PostgreSQL CAST(timestamp AS DATE) is not portable to SQLite. Both ranked
    # selectors share the real repository join and public serialization seam.
    monkeypatch.setattr(repo, "get_top_day_generations", repo.get_top_generations)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[User.__table__, ImageSession.__table__, Generation.__table__])
    try:
        with Session(engine, expire_on_commit=False) as sync:
            owner = User(id=42, tg_id=4200, credits=100, referral_code="synthetic-owner")
            reader = User(id=99, tg_id=9900, credits=100, referral_code="synthetic-reader")
            image_session = ImageSession(
                id=7, user_id=owner.id, model="nano-banana-pro", mode="image", quality="2K",
                aspect_ratio="1:1", count=1, status=ImageSessionStatus.active,
                reference_url=INPUT_REFS[0], reference_urls=json.dumps(INPUT_REFS),
                last_result_url=OUTPUTS[0], last_generation_id=77, last_prompt=SECRET_PROMPT,
                prompt_provenance="user_supplied",
            )
            generation = Generation(
                id=77, user_id=owner.id, image_session_id=7, model="nano-banana-pro",
                gen_type=GenerationType.image, prompt=SECRET_PROMPT, status=GenerationStatus.done,
                result_url=OUTPUTS[0], result_urls=json.dumps(OUTPUTS), is_public_feed=False,
                credits_spent=4, created_at=datetime.now(timezone.utc),
                input_params=json.dumps({"reference_images": INPUT_REFS, "prompt": SECRET_PROMPT}),
            )
            sync.add_all([owner, reader, image_session, generation])
            sync.commit()
            work = SimpleNamespace(
                session=LocalSession(sync), owner=owner, reader=reader, viewer=owner,
                generation=generation, image_session=image_session, mirror=mirror,
            )

            async def session_override():
                yield work.session

            async def user_override():
                return work.viewer

            previous = dict(app.dependency_overrides)
            app.dependency_overrides[get_session] = session_override
            app.dependency_overrides[get_web_user_or_none] = user_override
            app.dependency_overrides[get_miniapp_user] = user_override
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    work.client = client
                    response = await client.post("/api/web/feed/generations/77/publish")
                    assert response.status_code == 200, response.text
                    assert response.json()["data"]["is_public_feed"] is True
                    assert generation.is_public_feed is True
                    assert [call.args[0] for call in mirror.await_args_list] == OUTPUTS
                    work.viewer = None
                    yield work
            finally:
                app.dependency_overrides.clear()
                app.dependency_overrides.update(previous)
    finally:
        engine.dispose()


def assert_no_inputs(payload) -> None:
    serialized = json.dumps(payload)
    for reference in INPUT_REFS:
        assert reference not in serialized
    assert SECRET_PROMPT not in serialized
    assert "reference_url" not in payload
    assert "reference_urls" not in payload
    assert "input_params" not in payload


@pytest.mark.parametrize("path", [
    "/api/web/feed",
    "/api/web/feed?source=recent",
    "/api/web/feed?source=top",
    "/api/web/feed?source=top_day",
    "/api/web/feed?compact=true",
    "/api/web/feed/top",
    "/api/web/feed/top?compact=true",
    "/api/web/feed/77",
])
async def test_published_web_feed_exposes_only_generated_media(published_work, path):
    response = await published_work.client.get(path)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    payload = data[0] if isinstance(data, list) else data
    assert_no_inputs(payload)
    assert payload["result_url"] == OUTPUTS[0]
    assert payload["result_urls"] == OUTPUTS
    assert payload["preview_url"]
    assert len(payload["preview_urls"]) == 2


@pytest.mark.parametrize("path", [
    "/api/v1/public/feed/77",
    "/api/v1/feed?source=recent",
    "/api/v1/feed?source=top",
    "/api/v1/feed?source=top_day",
])
async def test_v1_feed_privacy_parity_preserves_generated_previews(published_work, path):
    if "/public/" not in path:
        published_work.viewer = published_work.reader
    response = await published_work.client.get(path)
    assert response.status_code == 200, response.text
    data = response.json()
    payload = data[0] if isinstance(data, list) else data
    assert_no_inputs(payload)
    assert payload["preview_urls"] == [
        f"/api/v1/feed/77/preview.webp?index={index}&output_id={feed_source_output_id(published_work.generation, url)}"
        for index, url in enumerate(OUTPUTS)
    ]


async def test_publishing_keeps_inputs_in_owner_history_detail_and_session(published_work):
    work = published_work
    work.viewer = work.owner
    for path in ("/api/web/history", "/api/web/generations/77", "/api/web/image-sessions/active"):
        response = await work.client.get(path)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        payload = data[0] if isinstance(data, list) else data
        assert payload["reference_url"] == INPUT_REFS[0]
        assert payload["reference_urls"] == INPUT_REFS
    assert json.loads(work.image_session.reference_urls) == INPUT_REFS
    assert json.loads(work.generation.input_params)["reference_images"] == INPUT_REFS

    work.viewer = None
    for path in ("/api/web/history", "/api/web/generations/77", "/api/web/image-sessions/active"):
        response = await work.client.get(path)
        assert response.status_code == 401
        for reference in INPUT_REFS:
            assert reference not in response.text

    work.viewer = work.reader
    response = await work.client.get("/api/web/generations/77")
    assert response.status_code == 404


async def test_publishing_keeps_owner_internal_repeat_inputs(published_work, monkeypatch):
    work = published_work
    monkeypatch.setattr(repo, "resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=4)))
    state = AsyncMock()
    state_data = {}
    state.update_data.side_effect = lambda **values: state_data.update(values)
    state.get_data.side_effect = lambda: dict(state_data)
    call = SimpleNamespace(
        data="repeat_image_77", from_user=SimpleNamespace(id=4200), answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
    )
    await repeat_safe.open_repeat(call, work.session, state, work.owner, AsyncMock())
    assert state.update_data.await_args.kwargs["repeat_reference_images"] == INPUT_REFS
    assert json.loads(work.image_session.reference_urls) == INPUT_REFS


async def test_public_repeat_uses_reader_photo_and_creator_prompt_not_author_inputs(published_work, monkeypatch):
    work = published_work
    work.viewer = work.reader
    monkeypatch.setattr(repo, "resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=4)))
    monkeypatch.setattr(repo, "charge_image_generation", AsyncMock(return_value=SimpleNamespace(allowed=True, charged_credits=4)))
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    monkeypatch.setattr(miniapp_routes, "_reconcile_user_active_generations", AsyncMock())
    generate = AsyncMock(return_value=SimpleNamespace(task_id="synthetic-remix-task", is_async=True))
    monkeypatch.setattr(miniapp_routes.image_service, "generate_image", generate)

    response = await work.client.post("/api/v1/feed/77/remix", json={
        "model": "nano-banana-pro", "mode": "image", "quality": "2K",
        "source_image_url": OUTPUTS[1], "image_url": "https://reader.example.test/portrait.jpg",
        "reference_urls": ["https://reader.example.test/portrait.jpg", "https://reader.example.test/profile.jpg"],
        "change_request": "Make the background blue",
    })
    assert response.status_code == 202, response.text
    assert generate.await_args.kwargs["image_url"] == [
        "https://reader.example.test/portrait.jpg", "https://reader.example.test/profile.jpg",
    ]
    assert SECRET_PROMPT in generate.await_args.args[1]
    assert OUTPUTS[1] not in str(generate.await_args)
    assert_no_inputs(response.json())
    assert json.loads(work.image_session.reference_urls) == INPUT_REFS


@pytest.mark.parametrize("path", ["/api/web/feed", "/api/web/feed/77", "/api/v1/public/feed/77"])
async def test_public_video_output_does_not_expose_input_photos(published_work, path):
    work = published_work
    work.generation.gen_type = GenerationType.video
    work.generation.result_url = "https://output.example.test/generated.mp4"
    work.generation.result_urls = None
    await work.session.commit()
    response = await work.client.get(path)
    assert response.status_code == 200, response.text
    data = response.json()
    if path.startswith("/api/web/"):
        data = data["data"]
    payload = data[0] if isinstance(data, list) else data
    assert_no_inputs(payload)
    assert payload["result_url"] == "https://output.example.test/generated.mp4"
