from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Sequence

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, InputMediaPhoto, Message, URLInputFile
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ImageDeliveryResult:
    delivered: bool
    mode: str | None = None  # photo | document | media_group


TELEGRAM_PHOTO_TARGET_BYTES = 9 * 1024 * 1024
TELEGRAM_PHOTO_MAX_DIMENSION_SUM = 10000
_JPEG_QUALITIES = (88, 82, 76, 70, 64, 58, 52, 46, 40, 34, 28)


def _result_extension(result_url: str) -> str:
    filename = result_url.split("?", 1)[0].rsplit("/", 1)[-1]
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"


def _flatten_for_jpeg(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def _fit_photo_dimensions(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width + height <= TELEGRAM_PHOTO_MAX_DIMENSION_SUM:
        return image
    scale = TELEGRAM_PHOTO_MAX_DIMENSION_SUM / float(width + height)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _encode_jpeg_under_limit(image: Image.Image, *, target_bytes: int) -> bytes:
    current = _fit_photo_dimensions(_flatten_for_jpeg(image))
    smallest: bytes | None = None
    for _ in range(6):
        for quality in _JPEG_QUALITIES:
            buffer = io.BytesIO()
            current.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
            data = buffer.getvalue()
            if smallest is None or len(data) < len(smallest):
                smallest = data
            if len(data) <= target_bytes:
                return data
        width, height = current.size
        if width <= 1 or height <= 1:
            break
        current = current.resize((max(1, int(width * 0.85)), max(1, int(height * 0.85))), Image.Resampling.LANCZOS)
    return smallest or b""


async def download_image_bytes(url: str, *, timeout_seconds: int = 20) -> bytes | None:
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.get(url) as resp:
                if resp.status != 200:
                    logger.warning("Failed to download image url=%s status=%s", url, resp.status)
                    return None
                return await resp.read()
    except Exception as exc:
        logger.warning("Failed to download image url=%s error=%s", url, exc)
        return None


def prepare_photo_upload(
    *,
    data: bytes,
    result_url: str,
    generation_id: int | str,
    target_bytes: int = TELEGRAM_PHOTO_TARGET_BYTES,
) -> BufferedInputFile:
    ext = _result_extension(result_url)
    filename = f"gen_{generation_id}.{ext}"
    if len(data) <= target_bytes:
        return BufferedInputFile(data, filename=filename)
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image)
            image.load()
            preview = _encode_jpeg_under_limit(image, target_bytes=target_bytes)
    except (OSError, UnidentifiedImageError) as exc:
        logger.warning("Failed to prepare image preview gen=%s url=%s error=%s", generation_id, result_url, exc)
        return BufferedInputFile(data, filename=filename)
    if not preview:
        return BufferedInputFile(data, filename=filename)
    return BufferedInputFile(preview, filename=f"gen_{generation_id}.jpg")


def image_process_failed(exc: Exception) -> bool:
    return isinstance(exc, TelegramBadRequest) and "IMAGE_PROCESS_FAILED" in str(exc)


def fallback_document_caption(caption: str | None) -> str:
    base = caption or ""
    suffix = (
        "\n\n📎 <b>Оригинал без сжатия.</b> "
        "Telegram не принял превью как фото, поэтому отправляю результат файлом — качество сохранено."
    )
    return (base + suffix).strip()


async def _send_with_downloaded_payload(
    *,
    send_photo: Callable[[Any], Awaitable[Any]],
    send_document: Callable[[Any, str | None], Awaitable[Any]],
    result_url: str,
    generation_id: int | str,
    caption: str | None,
    log_prefix: str,
) -> ImageDeliveryResult:
    data = await download_image_bytes(result_url)
    if data:
        try:
            photo = prepare_photo_upload(data=data, result_url=result_url, generation_id=generation_id)
            await send_photo(photo)
            return ImageDeliveryResult(delivered=True, mode="photo")
        except TelegramBadRequest as exc:
            logger.warning("%s photo-upload failed gen=%s url=%s error=%s", log_prefix, generation_id, result_url, exc)
            try:
                await send_document(
                    BufferedInputFile(data, filename=f"gen_{generation_id}.{_result_extension(result_url)}"),
                    fallback_document_caption(caption),
                )
                return ImageDeliveryResult(delivered=True, mode="document")
            except Exception as doc_exc:
                logger.warning("%s document-upload failed gen=%s url=%s error=%s", log_prefix, generation_id, result_url, doc_exc)
                return ImageDeliveryResult(delivered=False, mode=None)
        except Exception as exc:
            logger.warning("%s unexpected photo-upload error gen=%s url=%s error=%s", log_prefix, generation_id, result_url, exc)
            try:
                await send_document(
                    BufferedInputFile(data, filename=f"gen_{generation_id}.{_result_extension(result_url)}"),
                    fallback_document_caption(caption),
                )
                return ImageDeliveryResult(delivered=True, mode="document")
            except Exception as doc_exc:
                logger.warning("%s document-upload failed gen=%s url=%s error=%s", log_prefix, generation_id, result_url, doc_exc)
    return ImageDeliveryResult(delivered=False, mode=None)


async def _prepare_media_group_items(
    *,
    result_urls: Sequence[str],
    generation_prefix: int | str,
    caption: str | None,
) -> list[InputMediaPhoto] | None:
    media: list[InputMediaPhoto] = []
    for idx, url in enumerate(result_urls):
        data = await download_image_bytes(url)
        if not data:
            return None
        upload = prepare_photo_upload(data=data, result_url=url, generation_id=f"{generation_prefix}_{idx + 1}")
        media.append(
            InputMediaPhoto(
                media=upload,
                caption=caption if idx == 0 else None,
                parse_mode="HTML" if idx == 0 and caption else None,
            )
        )
    return media


async def send_image_group_to_message(
    *,
    message: Message,
    result_urls: Sequence[str],
    generation_prefix: int | str,
    caption: str | None = None,
    log_prefix: str = "telegram-image-group",
) -> ImageDeliveryResult:
    media = await _prepare_media_group_items(result_urls=result_urls, generation_prefix=generation_prefix, caption=caption)
    if not media:
        return ImageDeliveryResult(delivered=False, mode=None)
    try:
        await message.answer_media_group(media)
        return ImageDeliveryResult(delivered=True, mode="media_group")
    except Exception as exc:
        logger.warning("%s media-group failed gen=%s error=%s", log_prefix, generation_prefix, exc)
        return ImageDeliveryResult(delivered=False, mode=None)


async def send_image_group_to_chat(
    *,
    bot: Bot,
    chat_id: int,
    result_urls: Sequence[str],
    generation_prefix: int | str,
    caption: str | None = None,
    log_prefix: str = "telegram-image-group",
) -> ImageDeliveryResult:
    media = await _prepare_media_group_items(result_urls=result_urls, generation_prefix=generation_prefix, caption=caption)
    if not media:
        return ImageDeliveryResult(delivered=False, mode=None)
    try:
        await bot.send_media_group(chat_id=chat_id, media=media)
        return ImageDeliveryResult(delivered=True, mode="media_group")
    except Exception as exc:
        logger.warning("%s media-group failed gen=%s error=%s", log_prefix, generation_prefix, exc)
        return ImageDeliveryResult(delivered=False, mode=None)


async def send_original_document_to_message(
    *,
    message: Message,
    result_url: str,
    generation_id: int | str,
    caption: str | None = None,
    reply_markup: Any = None,
    log_prefix: str = "telegram-original",
) -> bool:
    data = await download_image_bytes(result_url)
    ext = _result_extension(result_url)
    if data:
        try:
            await message.answer_document(
                BufferedInputFile(data, filename=f"source_{generation_id}.{ext}"),
                caption=caption,
                reply_markup=reply_markup,
            )
            return True
        except Exception as exc:
            logger.warning("%s document-upload failed gen=%s url=%s error=%s", log_prefix, generation_id, result_url, exc)
    try:
        await message.answer_document(URLInputFile(result_url, filename=f"source_{generation_id}.{ext}"), caption=caption, reply_markup=reply_markup)
        return True
    except Exception as exc:
        logger.warning("%s remote-document failed gen=%s url=%s error=%s", log_prefix, generation_id, result_url, exc)
        return False


async def send_original_document_to_chat(
    *,
    bot: Bot,
    chat_id: int,
    result_url: str,
    generation_id: int | str,
    caption: str | None = None,
    reply_markup: Any = None,
    log_prefix: str = "telegram-original",
) -> bool:
    data = await download_image_bytes(result_url)
    ext = _result_extension(result_url)
    if data:
        try:
            await bot.send_document(
                chat_id=chat_id,
                document=BufferedInputFile(data, filename=f"source_{generation_id}.{ext}"),
                caption=caption,
                reply_markup=reply_markup,
            )
            return True
        except Exception as exc:
            logger.warning("%s document-upload failed gen=%s url=%s error=%s", log_prefix, generation_id, result_url, exc)
    try:
        await bot.send_document(
            chat_id=chat_id,
            document=URLInputFile(result_url, filename=f"source_{generation_id}.{ext}"),
            caption=caption,
            reply_markup=reply_markup,
        )
        return True
    except Exception as exc:
        logger.warning("%s remote-document failed gen=%s url=%s error=%s", log_prefix, generation_id, result_url, exc)
        return False


async def send_image_to_message(
    *,
    message: Message,
    result_url: str,
    generation_id: int | str,
    caption: str | None = None,
    reply_markup: Any = None,
    log_prefix: str = "telegram-image",
) -> ImageDeliveryResult:
    async def _photo(media: Any) -> Any:
        return await message.answer_photo(media, caption=caption, reply_markup=reply_markup)

    async def _document(media: Any, doc_caption: str | None) -> Any:
        return await message.answer_document(media, caption=doc_caption, reply_markup=reply_markup)

    preload_result = await _send_with_downloaded_payload(
        send_photo=_photo,
        send_document=_document,
        result_url=result_url,
        generation_id=generation_id,
        caption=caption,
        log_prefix=log_prefix,
    )
    if preload_result.delivered:
        return preload_result

    try:
        await message.answer_photo(result_url, caption=caption, reply_markup=reply_markup)
        return ImageDeliveryResult(delivered=True, mode="photo")
    except TelegramBadRequest as exc:
        logger.warning("%s remote-photo failed gen=%s url=%s error=%s", log_prefix, generation_id, result_url, exc)
        data = await download_image_bytes(result_url)
        if data:
            try:
                await message.answer_document(
                    BufferedInputFile(data, filename=f"gen_{generation_id}.{_result_extension(result_url)}"),
                    caption=fallback_document_caption(caption),
                    reply_markup=reply_markup,
                )
                return ImageDeliveryResult(delivered=True, mode="document")
            except Exception as doc_exc:
                logger.warning("%s remote-document failed gen=%s url=%s error=%s", log_prefix, generation_id, result_url, doc_exc)
        return ImageDeliveryResult(delivered=False, mode=None)
    except Exception as exc:
        logger.warning("%s remote-photo unexpected error gen=%s url=%s error=%s", log_prefix, generation_id, result_url, exc)
        data = await download_image_bytes(result_url)
        if data:
            try:
                await message.answer_document(
                    BufferedInputFile(data, filename=f"gen_{generation_id}.{_result_extension(result_url)}"),
                    caption=fallback_document_caption(caption),
                    reply_markup=reply_markup,
                )
                return ImageDeliveryResult(delivered=True, mode="document")
            except Exception as doc_exc:
                logger.warning("%s remote-document failed gen=%s url=%s error=%s", log_prefix, generation_id, result_url, doc_exc)
        return ImageDeliveryResult(delivered=False, mode=None)


async def send_image_to_chat(
    *,
    bot: Bot,
    chat_id: int,
    result_url: str,
    generation_id: int | str,
    caption: str | None = None,
    reply_markup: Any = None,
    log_prefix: str = "telegram-image",
) -> ImageDeliveryResult:
    async def _photo(media: Any) -> Any:
        return await bot.send_photo(chat_id=chat_id, photo=media, caption=caption, reply_markup=reply_markup)

    async def _document(media: Any, doc_caption: str | None) -> Any:
        return await bot.send_document(chat_id=chat_id, document=media, caption=doc_caption, reply_markup=reply_markup)

    preload_result = await _send_with_downloaded_payload(
        send_photo=_photo,
        send_document=_document,
        result_url=result_url,
        generation_id=generation_id,
        caption=caption,
        log_prefix=log_prefix,
    )
    if preload_result.delivered:
        return preload_result

    try:
        await bot.send_photo(chat_id=chat_id, photo=result_url, caption=caption, reply_markup=reply_markup)
        return ImageDeliveryResult(delivered=True, mode="photo")
    except TelegramBadRequest as exc:
        logger.warning("%s remote-photo failed gen=%s url=%s error=%s", log_prefix, generation_id, result_url, exc)
        data = await download_image_bytes(result_url)
        if data:
            try:
                await bot.send_document(
                    chat_id=chat_id,
                    document=BufferedInputFile(data, filename=f"gen_{generation_id}.{_result_extension(result_url)}"),
                    caption=fallback_document_caption(caption),
                    reply_markup=reply_markup,
                )
                return ImageDeliveryResult(delivered=True, mode="document")
            except Exception as doc_exc:
                logger.warning("%s remote-document failed gen=%s url=%s error=%s", log_prefix, generation_id, result_url, doc_exc)
        return ImageDeliveryResult(delivered=False, mode=None)
    except Exception as exc:
        logger.warning("%s remote-photo unexpected error gen=%s url=%s error=%s", log_prefix, generation_id, result_url, exc)
        data = await download_image_bytes(result_url)
        if data:
            try:
                await bot.send_document(
                    chat_id=chat_id,
                    document=BufferedInputFile(data, filename=f"gen_{generation_id}.{_result_extension(result_url)}"),
                    caption=fallback_document_caption(caption),
                    reply_markup=reply_markup,
                )
                return ImageDeliveryResult(delivered=True, mode="document")
            except Exception as doc_exc:
                logger.warning("%s remote-document failed gen=%s url=%s error=%s", log_prefix, generation_id, result_url, doc_exc)
        return ImageDeliveryResult(delivered=False, mode=None)
