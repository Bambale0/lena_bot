from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.handlers.gemini_omni_references import (
    GeminiOmniVideoModeFilter,
    upload_gemini_omni_document,
    upload_gemini_omni_photo,
    upload_gemini_omni_video,
)
from bot.states import VideoGenFSM

router = Router(name="gemini_omni_recovery")


@router.message(VideoGenFSM.video_upload, GeminiOmniVideoModeFilter(), F.video)
async def recover_gemini_omni_video(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    await state.set_state(VideoGenFSM.image_upload)
    await upload_gemini_omni_video(message, state, bot)


@router.message(VideoGenFSM.video_upload, GeminiOmniVideoModeFilter(), F.photo)
async def recover_gemini_omni_photo(message: Message, state: FSMContext) -> None:
    await state.set_state(VideoGenFSM.image_upload)
    await upload_gemini_omni_photo(message, state)


@router.message(VideoGenFSM.video_upload, GeminiOmniVideoModeFilter(), F.document)
async def recover_gemini_omni_document(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    await state.set_state(VideoGenFSM.image_upload)
    await upload_gemini_omni_document(message, state, bot)
