from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx

from core.neironych_seedance_contract import (
    SEEDANCE_MODELS,
    SeedanceContractError,
    canonical_seedance_model,
    normalize_seedance_request,
)

logger = logging.getLogger(__name__)

_SUCCESS_STATUSES = frozenset({"done", "completed", "succeeded", "success", "ready"})
_FAILURE_STATUSES = frozenset({"failed", "error", "cancelled", "canceled", "expired"})
_RANGE_CHUNK_BYTES = 1024 * 1024
_ZERO_PROGRESS_LIMIT = 4
_CONTENT_RANGE_RE = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$")
_LONG_TOKEN_RE = re.compile(r"(?i)\b[a-z0-9_-]{32,}\b")
_URL_QUERY_RE = re.compile(r"(https?://[^\s?]+)\?[^\s]*")


class NeironychSeedanceError(RuntimeError):
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


@dataclass(frozen=True, slots=True)
class VideoStatus:
    request_id: str
    status: str
    error: str
    billed_seconds: float | None
    payload: dict[str, Any]

    @property
    def done(self) -> bool:
        return self.status.lower() in _SUCCESS_STATUSES

    @property
    def failed(self) -> bool:
        return self.status.lower() in _FAILURE_STATUSES


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"td", "th"} and self._row is not None and self._cell is not None:
            value = " ".join("".join(self._cell).split())
            self._row.append(value)
            self._cell = None
        elif tag.lower() == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell = None


def parse_seedance_prices(page_html: str) -> dict[str, dict[str, float]]:
    """Extract current public ₽/second rows without hardcoding mutable prices."""

    parser = _TableParser()
    parser.feed(str(page_html or ""))
    result: dict[str, dict[str, float]] = {model: {} for model in SEEDANCE_MODELS}
    for row in parser.rows:
        combined = " | ".join(row)
        lower = combined.lower()
        model = ""
        if "seedance-2.0" in lower or "seedance 2.0" in lower or "seedance 2 " in lower:
            model = "seedance-2.0"
        if "seedance-2.5" in lower or "seedance 2.5" in lower:
            model = "seedance-2.5"
        if not model:
            continue

        resolution_match = re.search(r"\b(480p|720p|1080p|4k)\b", lower)
        if resolution_match is None:
            continue
        resolution = resolution_match.group(1)

        numeric: float | None = None
        for cell in row:
            value = cell.strip().replace("₽", "").replace(",", ".")
            if re.fullmatch(r"\d+(?:\.\d+)?", value):
                candidate = float(value)
                # Resolution/duration-like integers are not ₽/second rates here;
                # the public price table rate is a positive decimal/ruble value.
                if candidate > 0:
                    numeric = candidate
        if numeric is not None:
            result[model][resolution] = numeric
    return result


def _redact(value: str) -> str:
    clean = _URL_QUERY_RE.sub(r"\1?[REDACTED]", str(value or ""))
    return _LONG_TOKEN_RE.sub("[REDACTED]", clean)


def _safe_error(response: httpx.Response) -> NeironychSeedanceError:
    try:
        payload: Any = response.json()
    except Exception:
        payload = None

    message = ""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or error.get("detail") or "").strip()
        elif error:
            message = str(error).strip()
        if not message:
            detail = payload.get("detail")
            if isinstance(detail, str):
                message = detail.strip()
        if not message:
            message = str(payload.get("message") or "").strip()
    if not message:
        message = (response.text or "").strip()
    if not message:
        message = f"HTTP {response.status_code}"
    return NeironychSeedanceError(
        f"Нейроныч API HTTP {response.status_code}: {_redact(message)[:1000]}",
        status_code=response.status_code,
        payload=payload,
    )


def _request_id(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for source in (payload, payload.get("data")):
        if not isinstance(source, dict):
            continue
        for key in ("request_id", "id", "video_id"):
            value = source.get(key)
            if value:
                return str(value).strip()
    return ""


def _status_source(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _billed_seconds(payload: dict[str, Any]) -> float | None:
    source = _status_source(payload)
    usage = source.get("usage")
    if not isinstance(usage, dict):
        usage = payload.get("usage")
    if isinstance(usage, dict):
        value = usage.get("billed_seconds")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None
    return None


class NeironychSeedanceClient:
    """Server-side client for the documented Neironych async video API."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
        storage_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.base_url = str(base_url or "").strip().rstrip("/")
        if not self.base_url.startswith("https://"):
            raise NeironychSeedanceError("NEIRONYCH_API_BASE_URL должен использовать HTTPS")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 15.0)),
            follow_redirects=False,
        )
        self._storage_client = storage_client

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _auth_headers(self) -> dict[str, str]:
        if not self.api_key:
            raise NeironychSeedanceError("NEIRONYCH_API_KEY не настроен")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    async def list_models(self) -> list[str]:
        response = await self._client.get("/v1/models", headers={"Accept": "application/json"})
        if not response.is_success:
            raise _safe_error(response)
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise NeironychSeedanceError(
                "Нейроныч API вернул некорректный JSON списка моделей",
                status_code=response.status_code,
            ) from exc
        items: Any = payload
        if isinstance(payload, dict):
            for key in ("data", "models", "items"):
                if isinstance(payload.get(key), list):
                    items = payload[key]
                    break
        result: list[str] = []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str):
                    value = item.strip()
                elif isinstance(item, dict):
                    value = str(
                        item.get("id")
                        or item.get("model")
                        or item.get("model_id")
                        or item.get("name")
                        or ""
                    ).strip()
                else:
                    value = ""
                if value and value not in result:
                    result.append(value)
        return result

    async def get_prices(self) -> dict[str, dict[str, float]]:
        response = await self._client.get("/price", headers={"Accept": "text/html"})
        if not response.is_success:
            raise _safe_error(response)
        return parse_seedance_prices(response.text)

    async def upload_media(
        self,
        *,
        model: str,
        media_type: str,
        content: bytes,
        content_type: str,
    ) -> str:
        if model not in SEEDANCE_MODELS:
            raise NeironychSeedanceError(f"Неподдерживаемая тестовая модель: {model}")
        kind = str(media_type or "").strip().lower()
        if kind not in {"image", "video", "audio"}:
            raise NeironychSeedanceError(f"Неподдерживаемый media type: {media_type}")
        if not content:
            raise NeironychSeedanceError("Нельзя загрузить пустой файл")

        mime = str(content_type or "").strip().lower()
        prefix = {"image": "image/", "video": "video/", "audio": "audio/"}[kind]
        if not mime.startswith(prefix):
            raise NeironychSeedanceError(
                f"Content-Type {mime!r} не соответствует типу {kind!r}"
            )

        response = await self._client.post(
            "/v1/media/uploads",
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            json={
                "model": model,
                "type": kind,
                "content_type": mime,
                "size_bytes": len(content),
            },
        )
        if not response.is_success:
            raise _safe_error(response)
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise NeironychSeedanceError(
                "Нейроныч API вернул некорректный media upload ticket",
                status_code=response.status_code,
            ) from exc
        source = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
        upload_url = str(source.get("upload_url") or "").strip() if isinstance(source, dict) else ""
        media_url = str(source.get("media_url") or "").strip() if isinstance(source, dict) else ""
        try:
            upload_target = httpx.URL(upload_url)
            media_target = httpx.URL(media_url)
        except Exception as exc:
            raise NeironychSeedanceError("Media upload ticket содержит некорректные URL") from exc
        if (
            upload_target.scheme != "https"
            or not upload_target.host
            or media_target.scheme != "https"
            or not media_target.host
        ):
            raise NeironychSeedanceError(
                "Media upload ticket должен содержать HTTPS upload_url и media_url"
            )

        # upload_url is pre-signed storage. Never forward the partner Bearer token.
        if self._storage_client is not None:
            uploaded = await self._storage_client.put(
                upload_target,
                content=content,
                headers={"Content-Type": mime, "Content-Length": str(len(content))},
            )
        else:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(180.0, connect=15.0),
                follow_redirects=False,
            ) as storage_client:
                uploaded = await storage_client.put(
                    upload_target,
                    content=content,
                    headers={"Content-Type": mime, "Content-Length": str(len(content))},
                )
        if not uploaded.is_success:
            raise NeironychSeedanceError(
                f"Media storage upload HTTP {uploaded.status_code}",
                status_code=uploaded.status_code,
            )
        return str(media_target)

    async def create_video(
        self,
        *,
        model: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> str:
        try:
            canonical_model = canonical_seedance_model(model)
        except SeedanceContractError as exc:
            raise NeironychSeedanceError(str(exc)) from exc
        idem = str(idempotency_key or "").strip()
        if not 8 <= len(idem) <= 160:
            raise NeironychSeedanceError("Idempotency-Key должен содержать 8–160 символов")

        try:
            body = normalize_seedance_request(canonical_model, payload)
        except SeedanceContractError as exc:
            raise NeironychSeedanceError(str(exc), status_code=422) from exc
        body["model"] = model

        response = await self._client.post(
            "/v1/videos/generations",
            headers={
                **self._auth_headers(),
                "Content-Type": "application/json",
                "Idempotency-Key": idem,
            },
            json=body,
        )
        if not response.is_success:
            raise _safe_error(response)
        try:
            response_payload = response.json()
        except json.JSONDecodeError as exc:
            raise NeironychSeedanceError(
                "Нейроныч API вернул некорректный JSON создания видео",
                status_code=response.status_code,
            ) from exc
        request_id = _request_id(response_payload)
        if not request_id:
            raise NeironychSeedanceError(
                "Нейроныч API принял запрос, но не вернул request_id"
            )
        return request_id

    async def get_video(self, request_id: str) -> VideoStatus:
        value = str(request_id or "").strip()
        if not value:
            raise NeironychSeedanceError("request_id обязателен")
        response = await self._client.get(
            f"/v1/videos/{value}",
            headers=self._auth_headers(),
        )
        if not response.is_success:
            raise _safe_error(response)
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise NeironychSeedanceError(
                "Нейроныч API вернул некорректный JSON статуса видео",
                status_code=response.status_code,
            ) from exc
        if not isinstance(payload, dict):
            raise NeironychSeedanceError("Нейроныч API вернул неожиданный статус payload")
        source = _status_source(payload)
        # The requested ID alone is not proof that the response refers to this
        # paid job. A mismatched provider request_id must never authorize refund.
        returned_ids = [
            str(part.get("request_id")).strip()
            for part in (payload, source)
            if isinstance(part, dict) and part.get("request_id") is not None
        ]
        if any(reported != value for reported in returned_ids):
            raise NeironychSeedanceError(
                "Neironych video status request_id does not match requested task",
                status_code=response.status_code,
            )
        status = str(source.get("status") or source.get("state") or "").strip().lower()
        error = source.get("error")
        if isinstance(error, dict):
            error_text = str(error.get("message") or error.get("detail") or "").strip()
        else:
            error_text = str(error or source.get("message") or "").strip()
        return VideoStatus(
            request_id=value,
            status=status,
            error=_redact(error_text)[:1000],
            billed_seconds=_billed_seconds(payload),
            payload=payload,
        )

    async def download_content_to(
        self,
        request_id: str,
        path: Path,
        *,
        max_bytes: int,
    ) -> str:
        value = str(request_id or "").strip()
        if not value:
            raise NeironychSeedanceError("request_id обязателен")
        if max_bytes <= 0:
            raise NeironychSeedanceError("max_bytes должен быть > 0")

        headers = {
            **self._auth_headers(),
            "Accept": "video/mp4,application/octet-stream",
        }
        path.unlink(missing_ok=True)
        offset = 0
        total_size: int | None = None
        content_type = "video/mp4"
        zero_progress = 0

        while total_size is None or offset < total_size:
            upper = min(
                max_bytes - 1,
                offset + _RANGE_CHUNK_BYTES - 1,
                (total_size - 1) if total_size is not None else max_bytes - 1,
            )
            before = offset
            request_headers = {**headers, "Range": f"bytes={offset}-{upper}"}
            try:
                async with self._client.stream(
                    "GET",
                    f"/v1/videos/{value}/content",
                    headers=request_headers,
                ) as response:
                    if not response.is_success:
                        raw = await response.aread()
                        buffered = httpx.Response(
                            response.status_code,
                            headers=response.headers,
                            content=raw,
                            request=response.request,
                        )
                        raise _safe_error(buffered)

                    content_type = str(
                        response.headers.get("content-type") or content_type
                    ).split(";", 1)[0]
                    if response.status_code == 206:
                        raw_range = str(response.headers.get("content-range") or "").strip()
                        match = _CONTENT_RANGE_RE.fullmatch(raw_range)
                        if match is None:
                            raise NeironychSeedanceError(
                                "Content endpoint вернул некорректный Content-Range"
                            )
                        start, end = int(match.group(1)), int(match.group(2))
                        if start != offset or end < start:
                            raise NeironychSeedanceError(
                                "Content endpoint вернул неожиданный byte range"
                            )
                        if match.group(3) != "*":
                            advertised = int(match.group(3))
                            if advertised > max_bytes:
                                raise NeironychSeedanceError(
                                    f"Видео превышает лимит тестового контура {max_bytes} байт"
                                )
                            total_size = advertised
                    elif offset:
                        raise NeironychSeedanceError(
                            "Content endpoint проигнорировал Range при resume"
                        )
                    else:
                        raw_length = str(response.headers.get("content-length") or "")
                        if raw_length.isdigit():
                            advertised = int(raw_length)
                            if advertised > max_bytes:
                                raise NeironychSeedanceError(
                                    f"Видео превышает лимит тестового контура {max_bytes} байт"
                                )
                            total_size = advertised

                    with path.open("ab" if offset else "wb") as output:
                        async for chunk in response.aiter_bytes():
                            if not chunk:
                                continue
                            offset += len(chunk)
                            if offset > max_bytes:
                                raise NeironychSeedanceError(
                                    f"Видео превышает лимит тестового контура {max_bytes} байт"
                                )
                            output.write(chunk)

                    if response.status_code == 200 and total_size is None:
                        total_size = offset
            except httpx.TransportError as exc:
                if offset > before:
                    zero_progress = 0
                    logger.warning(
                        "neironych_seedance_download_resume request_id=%s offset=%s",
                        value,
                        offset,
                    )
                    continue
                zero_progress += 1
                if zero_progress >= _ZERO_PROGRESS_LIMIT:
                    raise NeironychSeedanceError(
                        "Скачивание результата остановилось без прогресса"
                    ) from exc
                continue

            if offset > before:
                zero_progress = 0
            else:
                zero_progress += 1
                if zero_progress >= _ZERO_PROGRESS_LIMIT:
                    raise NeironychSeedanceError(
                        "Скачивание результата остановилось без прогресса"
                    )

        return content_type
