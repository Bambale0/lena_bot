from __future__ import annotations

from fastapi import APIRouter

from api.web import assistant, auth, billing, feed, generations, health, history, landing, me, models, prompts, realtime, referrals, sessions

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(landing.router)
router.include_router(me.router)
router.include_router(models.router)
router.include_router(generations.router)
router.include_router(feed.router)
router.include_router(prompts.router)
router.include_router(realtime.router)
router.include_router(sessions.router)
router.include_router(history.router)
router.include_router(billing.router)
router.include_router(referrals.router)
router.include_router(assistant.router)
