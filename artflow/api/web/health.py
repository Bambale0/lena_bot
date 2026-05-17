from __future__ import annotations

from fastapi import APIRouter

from api.web.deps import ok

router = APIRouter(tags=["web"])


@router.get("/health")
async def health() -> dict:
    return ok({"service": "api-web", "status": "ok"})
