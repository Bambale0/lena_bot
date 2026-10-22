"""Authoritative KIE reads; callback bodies never settle a Kling 4 wallet."""

from fastapi import HTTPException

from api import kieai_client


async def canonical_kling4_status(task_id: str, *, expected_model: str | None = None) -> dict:
    try:
        payload = await kieai_client.get_task_status(task_id)
        data = payload.get("data") if isinstance(payload, dict) else None
        if (
            payload.get("code") != 200
            or not isinstance(data, dict)
            or data.get("taskId") != task_id
        ):
            raise ValueError("Invalid canonical KIE task")
        if expected_model is not None and data.get("model") != expected_model:
            raise ValueError("Canonical KIE model mismatch")
        if data.get("state") not in {"waiting", "queuing", "generating", "success", "fail"}:
            raise ValueError("Unknown canonical KIE state")
        # Existing reducer understands processing, success and fail.
        if data["state"] in {"waiting", "queuing", "generating"}:
            data = {**data, "state": "processing"}
        clean = {
            key: data[key]
            for key in ("taskId", "state", "resultJson", "failCode", "failMsg", "creditsConsumed")
            if key in data
        }
        return {"code": 200, "data": clean}
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Kling 4 status unavailable; retry callback later"
        ) from exc
