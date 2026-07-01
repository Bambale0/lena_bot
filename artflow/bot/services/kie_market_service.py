# bot/services/kie_market_service.py
"""
KIE Market Service — универсальный adapter для всех Market-моделей KIE.

Реализует:
- создание задачи (nano-banana-2-lite и любые другие Market-модели)
- проверка статуса
- webhook HMAC-SHA256 верификация
- загрузка файлов (Base64, stream, URL)
- проверка баланса кредитов
- получение download URL
- парсинг resultUrls из ответа
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
from typing import Any
from pathlib import Path

import aiohttp
import httpx

from core.config import settings

logger = logging.getLogger(__name__)

# ── Исключения ─────────────────────────────────────────────────────────────────


class KieApiError(Exception):
    """Ошибка KIE API."""
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        code = data.get("code", "unknown")
        msg = data.get("msg") or data.get("message") or str(data)
        super().__init__(f"KIE API error (code={code}): {msg}")


# ── Конфигурация по умолчанию ─────────────────────────────────────────────────

_API_BASE = "https://api.kie.ai"
_UPLOAD_BASE = "https://kieai.redpandaai.co"

# Допустимые aspect ratio для nano-banana-2-lite (и других Market-моделей)
VALID_ASPECT_RATIOS = {
    "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3",
    "4:5", "5:4", "8:1", "9:16", "16:9", "21:9", "auto",
}


# ── HTTP-сессия (ленивая инициализация) ───────────────────────────────────────

_client: httpx.AsyncClient | None = None
_upload_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=_API_BASE,
            headers={
                "Authorization": f"Bearer {settings.KIE_AI_KEY}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
    return _client


def _get_upload_client() -> httpx.AsyncClient:
    global _upload_client
    if _upload_client is None or _upload_client.is_closed:
        _upload_client = httpx.AsyncClient(
            base_url=_UPLOAD_BASE,
            headers={"Authorization": f"Bearer {settings.KIE_AI_KEY}"},
            timeout=120.0,
        )
    return _upload_client


async def close_client() -> None:
    """Закрыть HTTP-сессии (вызывать при shutdown)."""
    global _client, _upload_client
    if _client and not _client.is_closed:
        await _client.aclose()
    if _upload_client and not _upload_client.is_closed:
        await _upload_client.aclose()


# ── Внутренние HTTP-методы ────────────────────────────────────────────────────


async def _post_json(path: str, payload: dict[str, Any], *, base_url: str | None = None) -> dict[str, Any]:
    """POST JSON с ретраями."""
    client = _get_client() if not base_url else None
    url = f"{base_url.rstrip('/')}{path}" if base_url else path
    for attempt in range(3):
        try:
            if client:
                resp = await client.post(url, json=payload)
            else:
                async with httpx.AsyncClient(
                    headers={"Authorization": f"Bearer {settings.KIE_AI_KEY}", "Content-Type": "application/json"},
                    timeout=60.0,
                ) as temp_client:
                    resp = await temp_client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            body = e.response.text if e.response is not None else str(e)
            if e.response.status_code < 500:
                _maybe_alert_credit_issue(f"KIE Market POST {path}", body)
                raise KieApiError({"code": e.response.status_code, "msg": body[:500]})
            logger.warning("KIE Market POST %s HTTP %s (attempt %d)", path, e.response.status_code, attempt + 1)
        except httpx.RequestError as e:
            logger.warning("KIE Market POST %s error: %s (attempt %d)", path, e, attempt + 1)
        await asyncio.sleep(1.5 ** attempt)
    raise RuntimeError(f"KIE Market: max retries exceeded for POST {path}")


def _maybe_alert_credit_issue(source: str, payload: Any) -> None:
    """Отправить alert админу если не хватает кредитов."""
    message = str(payload).lower()
    markers = (
        "credits insufficient",
        "insufficient credits",
        "balance isn’t enough",
        "balance isn't enough",
        "please top up",
        "payment required",
        "current balance",
    )
    if any(marker in message for marker in markers):
        try:
            from core.admin_alerts import send_admin_alert_once
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    send_admin_alert_once(
                        alert_key=f"provider-credits:{source}",
                        title="У провайдера KIE закончились кредиты",
                        message=f"Источник: {source}\nДетали: {str(payload)[:900]}",
                    )
                )
            except RuntimeError:
                pass
        except Exception as exc:
            logger.warning("Failed to dispatch KIE credit alert: %s", exc)


# ── Публичные методы ──────────────────────────────────────────────────────────


async def create_task(
    model: str = "nano-banana-2-lite",
    prompt: str = "",
    image_urls: list[str] | None = None,
    aspect_ratio: str = "auto",
    callback_url: str | None = None,
) -> str:
    """
    Создать задачу генерации через KIE Market flow.

    Args:
        model: название модели (по умолчанию nano-banana-2-lite)
        prompt: текстовый промпт
        image_urls: ссылки на референсные изображения (до 10)
        aspect_ratio: соотношение сторон (auto или одно из VALID_ASPECT_RATIOS)
        callback_url: URL для webhook-уведомления о готовности

    Returns:
        taskId: идентификатор созданной задачи

    Raises:
        KieApiError: если API вернул ошибку
    """
    if aspect_ratio not in VALID_ASPECT_RATIOS:
        logger.warning("Invalid aspect_ratio=%s for %s, falling back to auto", aspect_ratio, model)
        aspect_ratio = "auto"

    payload: dict[str, Any] = {
        "model": model,
        "callBackUrl": callback_url or settings.KIE_WEBHOOK_PATH,
        "input": {
            "prompt": prompt.strip(),
            "image_urls": image_urls or [],
            "aspect_ratio": aspect_ratio,
        },
    }

    data = await _post_json("/api/v1/jobs/createTask", payload)

    code = data.get("code")
    if code not in (None, 200, "200", "success"):
        raise KieApiError(data)

    task_id = data.get("data", {}).get("taskId")
    if not task_id:
        raise KieApiError({"code": 500, "msg": "Empty taskId in createTask response"})

    logger.info("KIE Market task created: model=%s taskId=%s", model, task_id)
    return str(task_id)


async def get_task_details(task_id: str) -> dict[str, Any]:
    """
    Получить детали задачи (статус + результат).

    States: waiting, queuing, generating, success, fail

    Returns:
        Полный ответ API, результат в data.resultJson
    """
    client = _get_client()
    for attempt in range(3):
        try:
            resp = await client.get("/api/v1/jobs/recordInfo", params={"taskId": task_id})
            resp.raise_for_status()
            data = resp.json()
            _maybe_alert_credit_issue(f"KIE Market GET recordInfo {task_id}", data)
            return data
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                raise KieApiError({"code": e.response.status_code, "msg": e.response.text[:500]})
            logger.warning("KIE Market GET recordInfo %s HTTP %s (attempt %d)", task_id, e.response.status_code, attempt + 1)
        except httpx.RequestError as e:
            logger.warning("KIE Market GET recordInfo %s error: %s (attempt %d)", task_id, e, attempt + 1)
        await asyncio.sleep(1.5 ** attempt)
    raise RuntimeError(f"KIE Market: max retries exceeded for GET recordInfo {task_id}")


def parse_result_urls(task: dict[str, Any]) -> list[str]:
    """
    Извлечь resultUrls из ответа get_task_details или webhook.

    Парсит data.resultJson (JSON-строка) → {"resultUrls": [...]}
    """
    result_json = task.get("data", {}).get("resultJson")
    if not result_json:
        return []

    try:
        if isinstance(result_json, str):
            parsed = json.loads(result_json)
        elif isinstance(result_json, dict):
            parsed = result_json
        else:
            return []
    except json.JSONDecodeError:
        logger.warning("KIE Market: failed to parse resultJson: %s", str(result_json)[:200])
        return []

    urls: list[str] = []
    if isinstance(parsed, dict):
        urls = parsed.get("resultUrls", [])
        if not urls:
            # Fallback: ищем любые url-подобные ключи
            for key in ("result_urls", "resultUrl", "result_url", "urls", "videoUrls", "imageUrls"):
                val = parsed.get(key)
                if isinstance(val, list):
                    urls.extend(str(x) for x in val if x)
                elif isinstance(val, str) and val:
                    urls.append(val)
    return [url for url in urls if url.strip()]


def get_task_status_label(task: dict[str, Any]) -> str:
    """Извлечь статус задачи из ответа API."""
    data = task.get("data", {}) if isinstance(task, dict) else {}
    state = data.get("state") or task.get("state") or ""
    return str(state).lower()


def is_task_success(task: dict[str, Any]) -> bool:
    """Проверить, завершилась ли задача успешно."""
    return get_task_status_label(task) == "success"


def is_task_fail(task: dict[str, Any]) -> bool:
    """Проверить, завершилась ли задача с ошибкой."""
    return get_task_status_label(task) == "fail"


def get_task_error(task: dict[str, Any]) -> str:
    """Извлечь сообщение об ошибке из ответа задачи."""
    data = task.get("data", {}) if isinstance(task, dict) else {}
    return str(data.get("failMsg") or data.get("msg") or task.get("msg") or "Unknown error")


# ── Webhook HMAC-SHA256 верификация ──────────────────────────────────────────


def verify_webhook_signature(
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    *,
    webhook_hmac_key: str | None = None,
) -> bool:
    """
    Проверить HMAC-SHA256 подпись KIE webhook.

    KIE отправляет подпись в заголовках:
      X-Webhook-Timestamp
      X-Webhook-Signature

    Строка для подписи: taskId + "." + timestamp
    Подпись: base64(HMAC-SHA256(message, webhookHmacKey))
    """
    key = (webhook_hmac_key or settings.KIE_WEBHOOK_HMAC_KEY or "").strip()
    if not key:
        # Если ключ не настроен — пропускаем проверку (dev mode)
        logger.warning("KIE_WEBHOOK_HMAC_KEY not configured, skipping HMAC verification")
        return True

    if not headers:
        return False

    timestamp = headers.get("X-Webhook-Timestamp") or headers.get("x-webhook-timestamp")
    signature = headers.get("X-Webhook-Signature") or headers.get("x-webhook-signature")

    task_id = payload.get("taskId") or (payload.get("data") or {}).get("taskId") or ""
    if isinstance(task_id, dict):
        task_id = task_id.get("taskId", "")

    if not timestamp or not signature or not task_id:
        logger.warning("KIE webhook HMAC: missing required fields (taskId=%s ts=%s sig=%s)", task_id, bool(timestamp), bool(signature))
        return False

    message = f"{task_id}.{timestamp}".encode()
    secret = key.encode()

    digest = hmac.new(secret, message, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()

    result = hmac.compare_digest(expected, signature)
    if not result:
        logger.warning("KIE webhook HMAC signature mismatch for taskId=%s", task_id)
    return result


# ── Загрузка файлов ────────────────────────────────────────────────────────────


def _extract_upload_url(value: Any) -> str | None:
    """Извлечь URL загруженного файла из ответа KIE."""
    if isinstance(value, dict):
        for key in ("downloadUrl", "fileUrl", "url", "download_url", "file_url"):
            url = value.get(key)
            if isinstance(url, str) and url.startswith("http"):
                return url
        for nested in value.values():
            url = _extract_upload_url(nested)
            if url:
                return url
    if isinstance(value, list):
        for item in value:
            url = _extract_upload_url(item)
            if url:
                return url
    return None


async def upload_file_base64(
    file_data: bytes,
    file_name: str,
    upload_path: str = "images/telegram",
) -> str:
    """
    Загрузить файл через Base64 upload (для маленьких файлов).

    Endpoint: POST https://kieai.redpandaai.co/api/file-base64-upload
    """
    if len(file_data) > 10 * 1024 * 1024:
        logger.warning("File too large for base64 upload (%d bytes), use stream upload", len(file_data))

    b64_data = base64.b64encode(file_data).decode()
    payload = {
        "file": b64_data,
        "fileName": file_name,
        "uploadPath": upload_path,
    }

    client = _get_upload_client()
    for attempt in range(3):
        try:
            resp = await client.post("/api/file-base64-upload", json=payload)
            resp.raise_for_status()
            result = resp.json()
            url = _extract_upload_url(result)
            if not url:
                raise RuntimeError(f"empty upload url in response: {result!r}")
            return url
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                raise
            logger.warning("KIE base64 upload HTTP %s (attempt %d)", e.response.status_code, attempt + 1)
        except (httpx.RequestError, RuntimeError) as e:
            logger.warning("KIE base64 upload error: %s (attempt %d)", e, attempt + 1)
        await asyncio.sleep(1.5 ** attempt)
    raise RuntimeError("KIE Market: max retries exceeded for base64 upload")


async def upload_file_stream(
    file_path: str | Path,
    file_name: str | None = None,
    upload_path: str = "images/telegram",
) -> str:
    """
    Загрузить файл через Stream upload (рекомендуемый для Telegram-файлов).

    Endpoint: POST https://kieai.redpandaai.co/api/file-stream-upload
    """
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    fname = file_name or path.name
    data = path.read_bytes()
    content_type = _guess_mime(path)

    return await upload_file_stream_bytes(data, filename=fname, content_type=content_type, upload_path=upload_path)


async def upload_file_stream_bytes(
    data: bytes,
    *,
    filename: str,
    content_type: str = "image/png",
    upload_path: str = "images/telegram",
) -> str:
    """
    Загрузить файл через Stream upload (из bytes).

    Endpoint: POST https://kieai.redpandaai.co/api/file-stream-upload
    """
    client = _get_upload_client()
    files = {"file": (filename, data, content_type)}
    form = {"uploadPath": upload_path}
    for attempt in range(3):
        try:
            resp = await client.post("/api/file-stream-upload", data=form, files=files)
            resp.raise_for_status()
            payload = resp.json()
            url = _extract_upload_url(payload)
            if not url:
                raise RuntimeError(f"empty upload url in response: {payload!r}")
            return url
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                raise
            logger.warning("KIE stream upload HTTP %s (attempt %d)", e.response.status_code, attempt + 1)
        except (httpx.RequestError, RuntimeError) as e:
            logger.warning("KIE stream upload error: %s (attempt %d)", e, attempt + 1)
        await asyncio.sleep(1.5 ** attempt)
    raise RuntimeError("KIE Market: max retries exceeded for stream upload")


async def upload_file_url(
    file_url: str,
    file_name: str | None = None,
    upload_path: str = "images/telegram",
) -> str:
    """
    Загрузить файл по URL (если файл уже доступен по публичной ссылке).

    Endpoint: POST https://kieai.redpandaai.co/api/file-url-upload
    """
    payload: dict[str, Any] = {
        "url": file_url,
        "uploadPath": upload_path,
    }
    if file_name:
        payload["fileName"] = file_name

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {settings.KIE_AI_KEY}"},
        timeout=60.0,
    ) as client:
        for attempt in range(3):
            try:
                resp = await client.post(f"{_UPLOAD_BASE}/api/file-url-upload", json=payload)
                resp.raise_for_status()
                result = resp.json()
                url = _extract_upload_url(result)
                if not url:
                    raise RuntimeError(f"empty upload url in response: {result!r}")
                return url
            except httpx.HTTPStatusError as e:
                if e.response.status_code < 500:
                    raise
                logger.warning("KIE URL upload HTTP %s (attempt %d)", e.response.status_code, attempt + 1)
            except (httpx.RequestError, RuntimeError) as e:
                logger.warning("KIE URL upload error: %s (attempt %d)", e, attempt + 1)
            await asyncio.sleep(1.5 ** attempt)
    raise RuntimeError("KIE Market: max retries exceeded for URL upload")


def _guess_mime(path: Path) -> str:
    """Определить MIME-тип по расширению файла."""
    import mimetypes
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed and guessed.startswith("image/"):
        return guessed
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".mp4":
        return "video/mp4"
    if suffix in {".mp3", ".m4a"}:
        return "audio/mpeg"
    return "application/octet-stream"


# ── Баланс кредитов ───────────────────────────────────────────────────────────


async def get_remaining_credits() -> int | float:
    """
    Получить текущий баланс кредитов аккаунта.

    Endpoint: GET https://api.kie.ai/api/v1/chat/credit
    """
    client = _get_client()
    for attempt in range(3):
        try:
            resp = await client.get("/api/v1/chat/credit")
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") not in (None, 200, "200", "success"):
                raise KieApiError(data)
            return data.get("data", 0)
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                raise KieApiError({"code": e.response.status_code, "msg": e.response.text[:500]})
            logger.warning("KIE Market GET credits HTTP %s (attempt %d)", e.response.status_code, attempt + 1)
        except httpx.RequestError as e:
            logger.warning("KIE Market GET credits error: %s (attempt %d)", e, attempt + 1)
        await asyncio.sleep(1.5 ** attempt)
    raise RuntimeError("KIE Market: max retries exceeded for GET credits")


# ── Direct download URL ───────────────────────────────────────────────────────


async def get_download_url(generated_url: str) -> str:
    """
    Получить временную прямую ссылку для скачивания сгенерированного файла.

    Работает только с файлами, сгенерированными KIE.
    Ссылка живёт 20 минут.

    Endpoint: POST https://api.kie.ai/api/v1/common/download-url
    """
    data = await _post_json("/api/v1/common/download-url", {"url": generated_url})
    if data.get("code") not in (None, 200, "200", "success"):
        raise KieApiError(data)
    return str(data.get("data") or data.get("url") or generated_url)


# ── Helpers для интеграции с проектом ────────────────────────────────────────


def build_create_task_payload(
    model: str = "nano-banana-2-lite",
    prompt: str = "",
    image_urls: list[str] | None = None,
    aspect_ratio: str = "auto",
    callback_url: str | None = None,
) -> dict[str, Any]:
    """
    Собрать payload для createTask (без вызова API).
    Удобно если нужно вручную отправить запрос через существующий kieai_client.
    """
    if aspect_ratio not in VALID_ASPECT_RATIOS:
        aspect_ratio = "auto"

    payload: dict[str, Any] = {
        "model": model,
        "input": {
            "prompt": prompt.strip(),
            "image_urls": image_urls or [],
            "aspect_ratio": aspect_ratio,
        },
    }
    if callback_url:
        payload["callBackUrl"] = callback_url

    return payload


def is_kie_market_model(model: str) -> bool:
    """
    Проверить, является ли модель Market-моделью KIE (использует createTask).
    """
    return model in {
        "nano-banana-2-lite",
        "nano-banana-2",
        "nano-banana-pro",
        "google/nano-banana",
        "seedream/4.5-text-to-image",
        "seedream/4.5-edit",
        "grok-imagine/text-to-image",
        "grok-imagine/image-to-image",
        "wan/2-7-image",
        "wan/2-7-image-pro",
        "wan/2-7-text-to-video",
        "wan/2-7-image-to-video",
        "bytedance/seedance-2",
        "bytedance/seedance-2-fast",
        "grok-imagine/text-to-video",
        "grok-imagine/image-to-video",
        "kling-2.6/text-to-video",
        "kling-2.6/image-to-video",
        "kling-2.6/motion-control",
        "kling-3.0/video",
        "kling-3.0/motion-control",
        "happyhorse/text-to-video",
        "happyhorse/image-to-video",
        "qwen/text-to-image",
        "qwen/image-to-image",
        "qwen/image-edit",
        "qwen2/text-to-image",
        "qwen2/image-edit",
        "gpt-image-2-text-to-image",
        "gpt-image-2-image-to-image",
    }