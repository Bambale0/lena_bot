# db/session.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings
from core.request_identity import clear_current_user, reset_current_user
from db import repository as repo
from db.feed_engagement_guard import install_feed_engagement_guard

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

install_feed_engagement_guard(repo)


async def get_session() -> AsyncSession:
    identity_token = clear_current_user()
    try:
        async with AsyncSessionLocal() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
    finally:
        reset_current_user(identity_token)
