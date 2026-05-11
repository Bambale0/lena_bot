from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_main_menu_keyboard(balance: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"Баланс: {balance}", callback_data="menu:balance")
        ],

        [
            InlineKeyboardButton(text="🎨 Изображение", callback_data="image"),
            InlineKeyboardButton(text="🎬 Видео", callback_data="video"),
        ],

        [
            InlineKeyboardButton(text="🎵 Песня", callback_data="menu:music")
        ],

        [
            InlineKeyboardButton(text="🧠 Midjourney", callback_data="midjourney")
        ],

        [
            InlineKeyboardButton(text="📂 Промпты", callback_data="prompts"),
            InlineKeyboardButton(text="📜 История", callback_data="history"),
        ],

        [
            InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals"),
            InlineKeyboardButton(text="❓ Помощь", callback_data="help"),
        ],
    ])
