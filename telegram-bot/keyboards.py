"""
keyboards.py — Reply and inline keyboard builders for the Telegram bot.
"""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BTN_STATUS = "📊 Статус"
BTN_EXPORT = "📤 Выгрузить"
BTN_SORT_ABC = "🔤 Сортировка: abc"
BTN_SORT_DOMAIN = "🌐 Сортировка: domain"
BTN_HELP = "❓ Помощь"


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_STATUS), KeyboardButton(text=BTN_EXPORT)],
            [KeyboardButton(text=BTN_SORT_ABC), KeyboardButton(text=BTN_SORT_DOMAIN)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def status_inline(sort_mode: str) -> InlineKeyboardMarkup:
    abc_label = "🔤 abc ✓" if sort_mode == "abc" else "🔤 abc"
    domain_label = "🌐 domain ✓" if sort_mode == "domain" else "🌐 domain"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=abc_label, callback_data="sort:abc"),
                InlineKeyboardButton(text=domain_label, callback_data="sort:domain"),
            ],
            [
                InlineKeyboardButton(text="📤 Выгрузить список", callback_data="get_list"),
            ],
        ]
    )


def after_upload_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Показать статус", callback_data="show_status")],
        ]
    )
