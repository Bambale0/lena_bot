"""Bounded OpenAI-compatible Qwen 3.8 chat adapter for Neironych.

No automatic retry: a timed-out synchronous POST may already be billable.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


class Qwen38ProviderError(RuntimeError):
    def __init__(self, kind: str, *, ambiguous: bool, status: int | None = None) -> None:
        super().__init__(f"Neironych Qwen 3.8 {kind}")
        self.kind = kind
        self.ambiguous = ambiguous
        self.status = status


def extract_chat_text(data: Any) -> str:
    if not isinstance(data, dict) or data.get("error"):
        raise Qwen38ProviderError("invalid_response", ambiguous=True)
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise Qwen38ProviderError("empty_response", ambiguous=True)
    if choices[0].get("finish_reason") in {"content_filter", "length"}:
        raise Qwen38ProviderError("filtered_or_truncated", ambiguous=True)
    message = choices[0].get("message")
    if not isinstance(message, dict) or message.get("refusal"):
        raise Qwen38ProviderError("refused_or_invalid", ambiguous=True)
    content = message.get("content")
    if isinstance(content, list) and any(
        isinstance(item, dict) and (item.get("type") == "refusal" or item.get("refusal"))
        for item in content
    ):
        raise Qwen38ProviderError("refused_or_invalid", ambiguous=True)
    if isinstance(content, str):
        result = content.strip()
    elif isinstance(content, list):
        result = "\n".join(
            item["text"].strip() for item in content
            if isinstance(item, dict) and item.get("type") in {"text", "output_text"}
            and isinstance(item.get("text"), str) and item["text"].strip()
        ).strip()
    else:
        result = ""
    if not result:
        raise Qwen38ProviderError("empty_response", ambiguous=True)
    return result


class NeironychQwen38Service:
    def __init__(
        self, *, api_key: str | None = None, base_url: str | None = None,
        model: str | None = None, timeout_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = str(api_key if api_key is not None else settings.NEIRONYCH_API_KEY).strip()
        self.base_url = str(base_url if base_url is not None else settings.NEIRONYCH_API_BASE_URL).rstrip("/")
        self.model = str(model if model is not None else settings.NEIRONYCH_QWEN38_MODEL).strip()
        self.timeout_seconds = float(
            timeout_seconds if timeout_seconds is not None else settings.NEIRONYCH_QWEN38_TIMEOUT_SECONDS
        )
        self.transport = transport
        if not math.isfinite(self.timeout_seconds) or not 1 <= self.timeout_seconds <= 180:
            raise ValueError("Qwen timeout must be between 1 and 180 seconds")

    async def _complete(self, *, mode: str, messages: list[dict[str, Any]]) -> str:
        if not self.api_key or not self.base_url or not self.model:
            raise Qwen38ProviderError("not_configured", ambiguous=False)
        started = time.monotonic()
        status: int | None = None
        request_id = str(uuid.uuid4())
        failure_kind = "none"
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
                    response = await client.post(
                        f"{self.base_url}/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Idempotency-Key": request_id,
                            "X-Client-Request-Id": request_id,
                        },
                        json={"model": self.model, "stream": False, "messages": messages},
                    )
            status = response.status_code
            if status >= 400:
                raise Qwen38ProviderError("http_error", ambiguous=status >= 500 or status in {408, 409, 425, 429}, status=status)
            try:
                data = response.json()
            except ValueError as exc:
                raise Qwen38ProviderError("invalid_json", ambiguous=True, status=status) from exc
            result = extract_chat_text(data)
        except (TimeoutError, httpx.TimeoutException, httpx.TransportError) as exc:
            failure_kind = "transport_error"
            raise Qwen38ProviderError("transport_error", ambiguous=True, status=status) from exc
        except Qwen38ProviderError as exc:
            failure_kind = exc.kind
            raise
        except Exception as exc:
            failure_kind = "unexpected_error"
            raise Qwen38ProviderError("unexpected_error", ambiguous=True, status=status) from exc
        finally:
            # Do not log provider bodies, prompts, media URLs, tokens or request headers.
            logger.info(
                "qwen38 provider=neironych model=%s mode=%s latency_ms=%d status=%s request_id=%s result=%s failure=%s",
                self.model, mode, int((time.monotonic() - started) * 1000), status, request_id,
                "success" if failure_kind == "none" else "failure", failure_kind,
            )
        return result

    async def analyze_text(
        self, *, user_instruction: str, system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        instruction = str(user_instruction or "").strip()
        if not instruction:
            raise ValueError("user_instruction is required")
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": str(system_prompt)})
        for item in history or []:
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": instruction})
        return await self._complete(mode="text", messages=messages)

    async def analyze_image(
        self, *, image_url: str, user_instruction: str, system_prompt: str | None = None,
    ) -> str:
        url = str(image_url or "").strip()
        instruction = str(user_instruction or "").strip()
        if not url or not instruction:
            raise ValueError("image_url and user_instruction are required")
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": str(system_prompt)})
        messages.append({"role": "user", "content": [
            {"type": "text", "text": instruction},
            {"type": "image_url", "image_url": {"url": url}},
        ]})
        return await self._complete(mode="image", messages=messages)

    async def analyze_video(
        self, *, video_url: str, user_instruction: str, system_prompt: str | None = None,
        fps: float | int | None = None,
    ) -> str:
        url = str(video_url or "").strip()
        instruction = str(user_instruction or "").strip()
        if not url or not instruction:
            raise ValueError("video_url and user_instruction are required")
        sample_fps = float(2.0 if fps is None else fps)
        if not math.isfinite(sample_fps) or not 0.1 <= sample_fps <= 10:
            raise ValueError("Video prompt FPS must be between 0.1 and 10")
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": str(system_prompt)})
        messages.append({"role": "user", "content": [
            {"type": "text", "text": instruction},
            {"type": "video_url", "video_url": {"url": url}, "fps": sample_fps},
        ]})
        return await self._complete(mode="video", messages=messages)
