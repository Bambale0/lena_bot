from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.webapp_auth import get_webapp_user
from bot.handlers.marketplace import _prompts_for_source
from db.models import Generation, GenerationStatus, GenerationType, PromptStatus, User, UserPrompt
from db.prompt_repository import COLLECTION_TAGS
from db.session import AsyncSessionLocal, get_session
from main import app

SEED_AUTHOR_TG_ID = 9900001001
MIN_PROMPTS_PER_TAG = 2


async def _load_author() -> User:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == SEED_AUTHOR_TG_ID))
        author = result.scalar_one_or_none()
        if not author:
            raise RuntimeError(f"Showcase author with tg_id={SEED_AUTHOR_TG_ID} not found")
        return author


async def _session_override():
    async with AsyncSessionLocal() as session:
        yield session


async def _check_telegram_sources() -> None:
    async with AsyncSessionLocal() as session:
        best_prompts = await _prompts_for_source(session, "best")
        print(f"telegram source=best items={len(best_prompts)}")
        if len(best_prompts) < MIN_PROMPTS_PER_TAG:
            raise RuntimeError(f"Best prompts has only {len(best_prompts)} items")

        for tag in COLLECTION_TAGS:
            prompts = await _prompts_for_source(session, f"tag-{tag}")
            print(f"telegram source=tag-{tag} items={len(prompts)}")
            if len(prompts) < MIN_PROMPTS_PER_TAG:
                raise RuntimeError(f"Collection {tag} has only {len(prompts)} items")

        feed_count = (
            await session.execute(
                select(func.count())
                .select_from(Generation)
                .where(
                    Generation.gen_type == GenerationType.image,
                    Generation.status == GenerationStatus.done,
                    Generation.is_public_feed.is_(True),
                    Generation.result_url.is_not(None),
                )
            )
        ).scalar_one()
        print(f"telegram feed public images={feed_count}")
        if feed_count < len(COLLECTION_TAGS) * MIN_PROMPTS_PER_TAG:
            raise RuntimeError("Feed has fewer public images than expected showcase minimum")


async def _check_webapp(author: User) -> None:
    async def _user_override() -> User:
        return author

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_webapp_user] = _user_override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            health = await client.get("/api/webapp/health")
            print(f"webapp /health status={health.status_code}")
            if health.status_code != 200:
                raise RuntimeError("webapp health failed")

            prompts = await client.get("/api/webapp/prompts?sort=best&limit=50")
            prompt_items = prompts.json()["items"]
            print(f"webapp /prompts items={len(prompt_items)}")
            if len(prompt_items) < len(COLLECTION_TAGS) * MIN_PROMPTS_PER_TAG:
                raise RuntimeError("webapp prompts list is smaller than expected showcase minimum")

            feed = await client.get("/api/webapp/feed?sort=trending&limit=50")
            feed_items = feed.json()["items"]
            print(f"webapp /feed items={len(feed_items)}")
            if len(feed_items) < len(COLLECTION_TAGS) * MIN_PROMPTS_PER_TAG:
                raise RuntimeError("webapp feed list is smaller than expected showcase minimum")

            if prompt_items:
                prompt_id = prompt_items[0]["id"]
                prompt_detail = await client.get(f"/api/webapp/prompts/{prompt_id}")
                print(f"webapp /prompts/{prompt_id} status={prompt_detail.status_code}")
                if prompt_detail.status_code != 200:
                    raise RuntimeError("webapp prompt detail failed")
    finally:
        app.dependency_overrides.clear()


async def _check_db_minimums() -> None:
    async with AsyncSessionLocal() as session:
        for tag in COLLECTION_TAGS:
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(UserPrompt)
                    .where(
                        UserPrompt.status == PromptStatus.approved,
                        UserPrompt.is_public.is_(True),
                        UserPrompt.tags.any(tag),
                    )
                )
            ).scalar_one()
            print(f"db tag={tag} approved_prompts={count}")
            if count < MIN_PROMPTS_PER_TAG:
                raise RuntimeError(f"DB tag {tag} has only {count} prompts")


async def main() -> None:
    author = await _load_author()
    await _check_db_minimums()
    await _check_webapp(author)
    await _check_telegram_sources()
    print("showcase surfaces ok")


if __name__ == "__main__":
    asyncio.run(main())
