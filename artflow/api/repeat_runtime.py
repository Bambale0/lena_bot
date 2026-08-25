from __future__ import annotations

import json
import secrets
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class RepeatLaunchContext:
    input_params_extra: dict[str, Any]
    credits_override: float | None = None


_context: ContextVar[RepeatLaunchContext | None] = ContextVar("apix_repeat_launch_context", default=None)


@contextmanager
def repeat_launch_context(
    *,
    input_params_extra: dict[str, Any] | None = None,
    credits_override: float | None = None,
) -> Iterator[None]:
    token = _context.set(
        RepeatLaunchContext(
            input_params_extra=dict(input_params_extra or {}),
            credits_override=credits_override,
        )
    )
    try:
        yield
    finally:
        _context.reset(token)


def current_repeat_launch_context() -> RepeatLaunchContext | None:
    return _context.get()


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return list(parsed) if isinstance(parsed, list) else []


def _urls_from_image_session(image_session: Any | None) -> list[str]:
    if image_session is None:
        return []
    values: list[str] = []
    many = _json_list(getattr(image_session, "reference_urls", None))
    for item in many:
        clean = str(item or "").strip()
        if clean and clean not in values:
            values.append(clean)
    single = str(getattr(image_session, "reference_url", "") or "").strip()
    if single and single not in values:
        values.insert(0, single)
    return values


def _merge_aliases(payload: dict[str, Any], *values: Any) -> None:
    aliases: list[str] = []
    for item in payload.get("task_id_aliases") or []:
        clean = str(item or "").strip()
        if clean and clean not in aliases:
            aliases.append(clean)
    for item in values:
        clean = str(item or "").strip()
        if clean and clean not in aliases:
            aliases.append(clean)
    payload["task_id_aliases"] = aliases


class _CostView:
    def __init__(self, source: Any, credits: float) -> None:
        self._source = source
        self.credits = float(credits)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._source, name)


def install_repeat_runtime(repository: Any) -> None:
    if getattr(repository, "_safe_repeat_runtime_installed", False):
        return

    original_create_generation = repository.create_generation
    original_update_generation_task = repository.update_generation_task
    original_resolve_image_model_cost = repository.resolve_image_model_cost

    async def create_generation_with_snapshot(
        session,
        user_id: int,
        model: str,
        gen_type,
        prompt: str,
        credits_spent: int | float,
        image_session_id: int | None = None,
        parent_generation_id: int | None = None,
        action_type=None,
        source_feed_gen_id: int | None = None,
        input_params: dict | list | str | None = None,
    ):
        payload = _json_dict(input_params)
        gen_type_value = str(getattr(gen_type, "value", gen_type) or "")
        context = current_repeat_launch_context()

        if gen_type_value == "image":
            image_session = None
            if image_session_id:
                try:
                    image_session = await repository.get_image_session(session, int(image_session_id), int(user_id))
                except Exception:
                    image_session = None

            payload.setdefault("prompt", prompt)
            payload.setdefault("img_service", model)
            payload.setdefault("model", model)
            payload.setdefault("img_ratio", getattr(image_session, "aspect_ratio", None))
            payload.setdefault("img_quality", getattr(image_session, "quality", None))
            payload.setdefault("img_count", int(getattr(image_session, "count", 1) or 1))
            payload.setdefault("reference_images", _urls_from_image_session(image_session))
            payload.setdefault("img_nsfw_checker", bool(payload.get("img_nsfw_checker", False)))
            payload.setdefault("nsfw_enabled", bool(payload.get("nsfw_enabled", False)))
            payload.setdefault("parent_generation_id", parent_generation_id)
            payload.setdefault("source_feed_gen_id", source_feed_gen_id)
            payload.setdefault("action_type", str(getattr(action_type, "value", action_type) or "initial"))
            payload.setdefault("cost", float(credits_spent or 0))
            public_task_id = str(payload.get("public_task_id") or "").strip() or f"img_{secrets.token_hex(6)}"
            payload["public_task_id"] = public_task_id
            _merge_aliases(payload, public_task_id)

            if context is not None:
                payload.update(context.input_params_extra)
                payload["cost"] = float(credits_spent or 0)
                _merge_aliases(payload, public_task_id, *(context.input_params_extra.get("task_id_aliases") or []))

        return await original_create_generation(
            session,
            user_id,
            model,
            gen_type,
            prompt,
            credits_spent,
            image_session_id=image_session_id,
            parent_generation_id=parent_generation_id,
            action_type=action_type,
            source_feed_gen_id=source_feed_gen_id,
            input_params=payload if gen_type_value == "image" else input_params,
        )

    async def update_generation_task_with_aliases(session, gen_id: int, task_id: str) -> None:
        await original_update_generation_task(session, gen_id, task_id)
        generation = await repository.get_generation_by_id(session, gen_id)
        if generation is None:
            return
        payload = _json_dict(getattr(generation, "input_params", None))
        if str(getattr(getattr(generation, "gen_type", None), "value", getattr(generation, "gen_type", ""))) == "image":
            provider_id = str(task_id or "").strip()
            _merge_aliases(payload, payload.get("public_task_id"), provider_id)
            if provider_id.startswith("web:"):
                _merge_aliases(payload, provider_id[len("web:") :])
            generation.input_params = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            await session.commit()

    async def resolve_image_model_cost_with_override(*args, **kwargs):
        result = await original_resolve_image_model_cost(*args, **kwargs)
        context = current_repeat_launch_context()
        if result is None or context is None or context.credits_override is None:
            return result
        return _CostView(result, context.credits_override)

    repository.create_generation = create_generation_with_snapshot
    repository.update_generation_task = update_generation_task_with_aliases
    repository.resolve_image_model_cost = resolve_image_model_cost_with_override
    repository._safe_repeat_runtime_installed = True
