from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

NEXUS_NANO_BANANA_PRO_MODEL = "nano-banana-pro"
NEXUS_NANO_BANANA_PRO_ASPECT_RATIOS = ("1:1", "16:9", "9:16", "4:3", "3:4")
NEXUS_NANO_BANANA_PRO_MAX_REFS = 4
NEXUS_TERMINAL_STATUSES = {"completed", "failed"}


class NexusApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        payload: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class NexusApiTimeout(NexusApiError):
    pass


@dataclass(frozen=True)
class NexusCreateResult:
    task_id: str
    status_code: int
    elapsed_ms: int
    idempotency_key: str
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]


@dataclass(frozen=True)
class NexusTaskResult:
    task_id: str
    status: str
    payload: dict[str, Any]
    elapsed_ms: int
    status_history: tuple[str, ...] = field(default_factory=tuple)

    @property
    def completed(self) -> bool:
        return self.status == "completed"

    @property
    def failed(self) -> bool:
        return self.status == "failed"


@dataclass(frozen=True)
class NexusCatalogResult:
    status_code: int
    elapsed_ms: int
    payload: Any


@dataclass(frozen=True)
class NexusSchemaResult:
    model_name: str
    schema_name: str
    schema: dict[str, Any]
    elapsed_ms: int


def _json_or_text(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        text = response.text.strip()
        return {"raw": text} if text else {}


def _error_detail(payload: Any, status_code: int) -> str:
    if isinstance(payload, dict):
        for key in ("detail", "error", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                nested = value.get("message") or value.get("detail")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
    labels = {
        401: "NexusAPI rejected the API key",
        402: "NexusAPI account has insufficient balance",
        422: "NexusAPI rejected the Nano Banana Pro parameters",
        429: "NexusAPI rate limit exceeded",
    }
    return labels.get(status_code, f"NexusAPI HTTP {status_code}")


def _validate_public_http_url(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError(f"{field_name} must not contain URL credentials")
    return cleaned


def _validate_reference_urls(values: list[str] | tuple[str, ...] | None) -> list[str]:
    refs: list[str] = []
    for raw in list(values or []):
        value = _validate_public_http_url(raw, field_name="image_urls")
        if value and value not in refs:
            refs.append(value)
    if len(refs) > NEXUS_NANO_BANANA_PRO_MAX_REFS:
        raise ValueError(
            f"Nano Banana Pro evaluation supports at most {NEXUS_NANO_BANANA_PRO_MAX_REFS} references"
        )
    return refs


def build_nano_banana_pro_params(
    *,
    prompt: str,
    aspect_ratio: str | None = None,
    seed: int | None = None,
    image_url: str | None = None,
    image_urls: list[str] | tuple[str, ...] | None = None,
    webhook_url: str | None = None,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt_value = str(prompt or "").strip()
    if not prompt_value:
        raise ValueError("prompt is required")

    ratio_value = str(aspect_ratio or "").strip() or None
    if ratio_value is not None and ratio_value not in NEXUS_NANO_BANANA_PRO_ASPECT_RATIOS:
        raise ValueError(
            "aspect_ratio must be one of: " + ", ".join(NEXUS_NANO_BANANA_PRO_ASPECT_RATIOS)
        )

    if seed is not None and isinstance(seed, bool):
        raise ValueError("seed must be an integer")
    seed_value = int(seed) if seed is not None else None

    single_ref = _validate_public_http_url(image_url, field_name="image_url")
    multi_refs = _validate_reference_urls(image_urls)
    if single_ref and multi_refs:
        raise ValueError("Use image_url or image_urls, not both")

    params: dict[str, Any] = {
        "model_name": NEXUS_NANO_BANANA_PRO_MODEL,
        "prompt": prompt_value,
    }
    if ratio_value is not None:
        params["aspect_ratio"] = ratio_value
    if seed_value is not None:
        params["seed"] = seed_value
    if single_ref:
        params["image_url"] = single_ref
    if multi_refs:
        params["image_urls"] = multi_refs

    webhook_value = _validate_public_http_url(webhook_url, field_name="webhook_url")
    if webhook_value:
        params["webhook_url"] = webhook_value

    overrides = dict(extra_params or {})
    for protected in ("model_name", "prompt"):
        overrides.pop(protected, None)
    params.update(overrides)
    return params


def _result_object(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    return result if isinstance(result, dict) else payload


def extract_result_urls(task_payload: dict[str, Any]) -> list[str]:
    result = _result_object(task_payload)
    candidates: list[Any] = []
    for key in ("image_url", "url"):
        candidates.append(result.get(key))
    for key in ("image_urls", "urls"):
        value = result.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    images = result.get("images")
    if isinstance(images, list):
        for item in images:
            if isinstance(item, str):
                candidates.append(item)
            elif isinstance(item, dict):
                candidates.append(item.get("url") or item.get("image_url"))

    urls: list[str] = []
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value and value.startswith(("http://", "https://")) and value not in urls:
            urls.append(value)
    return urls


def extract_result_base64(task_payload: dict[str, Any]) -> list[bytes]:
    result = _result_object(task_payload)
    candidates: list[Any] = [result.get("base64"), result.get("b64_json")]
    images = result.get("images")
    if isinstance(images, list):
        for item in images:
            if isinstance(item, dict):
                candidates.extend([item.get("base64"), item.get("b64_json")])

    decoded: list[bytes] = []
    for candidate in candidates:
        value = str(candidate or "").strip()
        if not value:
            continue
        if value.startswith("data:") and "," in value:
            value = value.split(",", 1)[1]
        try:
            raw = base64.b64decode(value, validate=True)
        except Exception:
            continue
        if raw:
            decoded.append(raw)
    return decoded


def find_model_in_catalog(
    payload: Any,
    model_name: str = NEXUS_NANO_BANANA_PRO_MODEL,
) -> dict[str, Any] | None:
    candidates: Any = payload
    if isinstance(payload, dict):
        for key in ("models", "data", "items", "results"):
            if isinstance(payload.get(key), list):
                candidates = payload[key]
                break
    if not isinstance(candidates, list):
        return None
    for item in candidates:
        if not isinstance(item, dict):
            continue
        key = item.get("model_name") or item.get("id") or item.get("key") or item.get("name")
        if str(key or "").strip() == model_name:
            return item
    return None


def extract_openapi_model_schema(
    openapi: Any,
    model_name: str = NEXUS_NANO_BANANA_PRO_MODEL,
) -> tuple[str, dict[str, Any]]:
    if not isinstance(openapi, dict):
        raise NexusApiError("NexusAPI OpenAPI response is not an object")
    schemas = openapi.get("components", {}).get("schemas", {})
    request_schema = schemas.get("GenerateRequest", {}) if isinstance(schemas, dict) else {}
    params = request_schema.get("properties", {}).get("params", {}) if isinstance(request_schema, dict) else {}
    mapping = params.get("discriminator", {}).get("mapping", {}) if isinstance(params, dict) else {}
    ref = mapping.get(model_name) if isinstance(mapping, dict) else None
    if not isinstance(ref, str) or not ref:
        raise NexusApiError(f"NexusAPI OpenAPI has no discriminator mapping for {model_name}")
    schema_name = ref.rsplit("/", 1)[-1]
    schema = schemas.get(schema_name) if isinstance(schemas, dict) else None
    if not isinstance(schema, dict):
        raise NexusApiError(f"NexusAPI OpenAPI schema not found: {schema_name}")
    return schema_name, schema


class NexusApiClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = str(
            api_key if api_key is not None else os.getenv("NEXUS_API_KEY", "")
        ).strip()
        self.base_url = str(
            base_url if base_url is not None else os.getenv("NEXUS_BASE_URL", "https://nexusapi.dev")
        ).strip().rstrip("/")
        self.timeout_seconds = float(timeout_seconds or os.getenv("NEXUS_HTTP_TIMEOUT", "30"))
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _auth_headers(self, *, idempotency_key: str | None = None) -> dict[str, str]:
        if not self.api_key:
            raise NexusApiError("NEXUS_API_KEY is not configured")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if self._client is not None:
            return await self._client.request(method, path, **kwargs)
        timeout = httpx.Timeout(self.timeout_seconds)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
            return await client.request(method, path, **kwargs)

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> Any:
        payload = _json_or_text(response)
        if response.status_code < 200 or response.status_code >= 300:
            raise NexusApiError(
                _error_detail(payload, response.status_code),
                status_code=response.status_code,
                payload=payload,
            )
        return payload

    async def create_params(
        self,
        params: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> NexusCreateResult:
        model_name = str(params.get("model_name") or "").strip()
        prompt = str(params.get("prompt") or "").strip()
        if not model_name or not prompt:
            raise ValueError("params must contain model_name and prompt")
        payload = {"params": dict(params)}
        idem = str(idempotency_key or uuid.uuid4()).strip()
        started = time.monotonic()
        try:
            response = await self._request(
                "POST",
                "/generate",
                headers={
                    **self._auth_headers(idempotency_key=idem),
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.RequestError as exc:
            raise NexusApiError(f"NexusAPI network error: {exc}") from exc
        elapsed_ms = round((time.monotonic() - started) * 1000)
        data = self._raise_for_status(response)
        if not isinstance(data, dict):
            raise NexusApiError(
                "NexusAPI returned a non-object create response",
                status_code=response.status_code,
                payload=data,
            )
        task_id = str(data.get("task_id") or data.get("taskId") or "").strip()
        if not task_id:
            raise NexusApiError(
                "NexusAPI native /generate response has no task_id",
                status_code=response.status_code,
                payload=data,
            )
        return NexusCreateResult(
            task_id=task_id,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            idempotency_key=idem,
            request_payload=payload,
            response_payload=data,
        )

    async def create_nano_banana_pro(
        self,
        *,
        prompt: str,
        aspect_ratio: str | None = None,
        seed: int | None = None,
        image_url: str | None = None,
        image_urls: list[str] | tuple[str, ...] | None = None,
        webhook_url: str | None = None,
        extra_params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> NexusCreateResult:
        params = build_nano_banana_pro_params(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            seed=seed,
            image_url=image_url,
            image_urls=image_urls,
            webhook_url=webhook_url,
            extra_params=extra_params,
        )
        return await self.create_params(params, idempotency_key=idempotency_key)

    async def get_task(self, task_id: str) -> dict[str, Any]:
        task_value = str(task_id or "").strip()
        if not task_value:
            raise ValueError("task_id is required")
        try:
            response = await self._request(
                "GET",
                f"/tasks/{task_value}",
                headers=self._auth_headers(),
            )
        except httpx.RequestError as exc:
            raise NexusApiError(f"NexusAPI network error: {exc}") from exc
        payload = self._raise_for_status(response)
        if not isinstance(payload, dict):
            raise NexusApiError(
                "NexusAPI returned a non-object task response",
                status_code=response.status_code,
                payload=payload,
            )
        return payload

    async def wait_for_task(
        self,
        task_id: str,
        *,
        poll_interval: float | None = None,
        timeout_seconds: float | None = None,
    ) -> NexusTaskResult:
        interval = max(0.5, float(poll_interval or os.getenv("NEXUS_POLL_INTERVAL", "1")))
        timeout = max(5.0, float(timeout_seconds or os.getenv("NEXUS_POLL_TIMEOUT", "120")))
        started = time.monotonic()
        history: list[str] = []
        while True:
            payload = await self.get_task(task_id)
            status = str(payload.get("status") or "").strip().lower()
            if status and (not history or history[-1] != status):
                history.append(status)
            if status in NEXUS_TERMINAL_STATUSES:
                return NexusTaskResult(
                    task_id=str(payload.get("task_id") or task_id),
                    status=status,
                    payload=payload,
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                    status_history=tuple(history),
                )
            if time.monotonic() - started >= timeout:
                raise NexusApiTimeout(
                    f"NexusAPI task {task_id} did not finish within {timeout:g}s",
                    payload={"task_id": task_id, "status_history": history},
                )
            await asyncio.sleep(interval)

    async def get_public_models(self) -> NexusCatalogResult:
        started = time.monotonic()
        try:
            response = await self._request("GET", "/public/models", headers={"Accept": "application/json"})
        except httpx.RequestError as exc:
            raise NexusApiError(f"NexusAPI catalog network error: {exc}") from exc
        elapsed_ms = round((time.monotonic() - started) * 1000)
        payload = self._raise_for_status(response)
        return NexusCatalogResult(status_code=response.status_code, elapsed_ms=elapsed_ms, payload=payload)

    async def get_model_schema(
        self,
        model_name: str = NEXUS_NANO_BANANA_PRO_MODEL,
    ) -> NexusSchemaResult:
        started = time.monotonic()
        try:
            response = await self._request("GET", "/openapi.json", headers={"Accept": "application/json"})
        except httpx.RequestError as exc:
            raise NexusApiError(f"NexusAPI OpenAPI network error: {exc}") from exc
        openapi = self._raise_for_status(response)
        schema_name, schema = extract_openapi_model_schema(openapi, model_name)
        return NexusSchemaResult(
            model_name=model_name,
            schema_name=schema_name,
            schema=schema,
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )


def pretty_json(value: Any, *, max_chars: int = 3500) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"
