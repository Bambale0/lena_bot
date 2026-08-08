from __future__ import annotations

from fastapi import APIRouter

from api.web import (
    admin,
    assistant,
    auth,
    billing,
    feed,
    generations,
    health,
    history,
    landing,
    me,
    minimax_h3_uploads,
    models,
    prompts,
    realtime,
    referrals,
    seedance25_uploads,
    sessions,
    suno_source_audio,
)
from api.prompt_privacy import install_web_schema_prompt_privacy

install_web_schema_prompt_privacy()

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(landing.router)
router.include_router(me.router)
router.include_router(models.router)
router.include_router(generations.router)
router.include_router(minimax_h3_uploads.router)
router.include_router(seedance25_uploads.router)
router.include_router(suno_source_audio.router)
router.include_router(feed.router)
router.include_router(prompts.router)
router.include_router(realtime.router)
router.include_router(sessions.router)
router.include_router(history.router)
router.include_router(billing.router)
router.include_router(referrals.router)
router.include_router(assistant.router)
router.include_router(admin.router)
