"""Prompt privacy guards for Mini App and public web surfaces.

Prompts may stay available server-side for generation, remix, trend and prompt-id
workflows. They must not be serialized back to the Mini App/public client after a
job or prompt object exists.
"""
from __future__ import annotations

from typing import Any


PROMPT_HIDDEN_PLACEHOLDER = ""


def hide_generation_prompt_payload(payload: Any) -> Any:
    """Remove stored generation prompts from dict/Pydantic payloads in-place."""
    if payload is None:
        return payload

    if isinstance(payload, dict):
        if "prompt" in payload:
            payload["prompt"] = PROMPT_HIDDEN_PLACEHOLDER
        if "prompt_hidden" in payload:
            payload["prompt_hidden"] = True
        if "prompt_actions_allowed" in payload:
            payload["prompt_actions_allowed"] = False
        if "session_last_prompt" in payload:
            payload["session_last_prompt"] = None
        if "base_prompt" in payload:
            payload["base_prompt"] = None
        if "last_prompt" in payload:
            payload["last_prompt"] = None
        return payload

    for field, value in {
        "prompt": PROMPT_HIDDEN_PLACEHOLDER,
        "prompt_hidden": True,
        "prompt_actions_allowed": False,
        "session_last_prompt": None,
        "base_prompt": None,
        "last_prompt": None,
    }.items():
        if hasattr(payload, field):
            try:
                setattr(payload, field, value)
            except Exception:
                # Keep this guard non-fatal for frozen/foreign payload objects.
                pass
    return payload


def hide_feed_prompt_payload(payload: Any) -> Any:
    if payload is None:
        return payload
    if isinstance(payload, dict):
        payload["prompt"] = PROMPT_HIDDEN_PLACEHOLDER
        payload["prompt_visibility"] = "hidden"
        return payload
    if hasattr(payload, "prompt"):
        try:
            setattr(payload, "prompt", PROMPT_HIDDEN_PLACEHOLDER)
        except Exception:
            pass
    if hasattr(payload, "prompt_visibility"):
        try:
            setattr(payload, "prompt_visibility", "hidden")
        except Exception:
            pass
    return payload


def hide_prompt_card_payload(payload: Any) -> Any:
    """Hide marketplace/library prompt text while keeping prompt id usable."""
    if payload is None:
        return payload
    if isinstance(payload, dict):
        if "prompt_text" in payload:
            payload["prompt_text"] = PROMPT_HIDDEN_PLACEHOLDER
        payload["prompt_hidden"] = True
        payload["prompt_visibility"] = "hidden"
        return payload
    if hasattr(payload, "prompt_text"):
        try:
            setattr(payload, "prompt_text", PROMPT_HIDDEN_PLACEHOLDER)
        except Exception:
            pass
    return payload


def install_miniapp_prompt_privacy(routes: Any) -> None:
    """Patch api.miniapp_routes serialization helpers after module import."""
    if getattr(routes, "_prompt_privacy_installed", False):
        return

    original_gen_out = getattr(routes, "_gen_out", None)
    if original_gen_out is not None:
        def private_gen_out(*args: Any, **kwargs: Any) -> Any:
            return hide_generation_prompt_payload(original_gen_out(*args, **kwargs))

        routes._gen_out = private_gen_out

    original_feed_card_out = getattr(routes, "_feed_card_out", None)
    if original_feed_card_out is not None:
        def private_feed_card_out(*args: Any, **kwargs: Any) -> dict:
            return hide_feed_prompt_payload(original_feed_card_out(*args, **kwargs))

        routes._feed_card_out = private_feed_card_out

    original_prompt_out = getattr(routes, "_prompt_out", None)
    if original_prompt_out is not None:
        def private_prompt_out(*args: Any, **kwargs: Any) -> dict:
            return hide_prompt_card_payload(original_prompt_out(*args, **kwargs))

        routes._prompt_out = private_prompt_out

    routes._prompt_privacy_installed = True


def install_web_schema_prompt_privacy() -> None:
    """Patch shared web schemas used by public history/feed/detail surfaces."""
    from api.web import schemas

    if getattr(schemas, "_prompt_privacy_installed", False):
        return

    original_generation_from_generation = schemas.GenerationCard.from_generation.__func__

    def private_generation_from_generation(cls: type, *args: Any, **kwargs: Any) -> Any:
        return hide_generation_prompt_payload(original_generation_from_generation(cls, *args, **kwargs))

    schemas.GenerationCard.from_generation = classmethod(private_generation_from_generation)

    original_feed_from_feed_card = schemas.FeedCard.from_feed_card.__func__

    def private_feed_from_feed_card(cls: type, *args: Any, **kwargs: Any) -> Any:
        return hide_feed_prompt_payload(original_feed_from_feed_card(cls, *args, **kwargs))

    schemas.FeedCard.from_feed_card = classmethod(private_feed_from_feed_card)
    schemas._prompt_privacy_installed = True
