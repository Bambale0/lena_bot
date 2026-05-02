# bot/filters/admin.py
from aiogram.filters import BaseFilter
from aiogram.types import Message

from core.config import settings


class IsAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user is not None and message.from_user.id in settings.ADMIN_IDS
