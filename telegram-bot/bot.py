"""
bot.py — Entry point. Telegram bot handlers using aiogram v3.

Commands
--------
/start            — welcome message
/help             — show all commands
/status           — show current list sizes and settings
/set_sort abc     — sort domains alphabetically (default)
/set_sort domain  — sort domains by TLD first (right-to-left)
/set_list_len N   — set max records per file for domains (default 300)
/set_ip_list_len N— set max records per file for IP routes (default 1000)
/get_list [name]  — export lists; clears data after successful delivery

Documents
---------
*.txt  — domain list (one domain per line)
*.bat  — IP route list (route ADD … MASK … 0.0.0.0)
"""

import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    Document,
    Message,
)
from dotenv import load_dotenv

import database as db
import processor
import utils
from keyboards import (
    BTN_EXPORT,
    BTN_HELP,
    BTN_SORT_ABC,
    BTN_SORT_DOMAIN,
    BTN_STATUS,
    after_upload_inline,
    main_keyboard,
    status_inline,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-20s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bot & dispatcher
# ---------------------------------------------------------------------------

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in the environment.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------

HELP_TEXT = (
    "📋 <b>Доступные команды:</b>\n\n"
    "<b>Загрузка файлов:</b>\n"
    "• <code>.txt</code> — список доменов (один домен на строку)\n"
    "• <code>.bat</code> — маршруты IP (route ADD ip MASK mask 0.0.0.0)\n\n"
    "<b>Сортировка доменов:</b>\n"
    "• /set_sort abc — алфавитная с начала строки (по умолчанию)\n"
    "• /set_sort domain — по домену: TLD → субдомены\n\n"
    "<b>Экспорт:</b>\n"
    "• /get_list — с именем первого загруженного файла\n"
    "• /get_list имя — с указанным именем\n"
    "  После выгрузки данные очищаются.\n\n"
    "<b>Размер пачки:</b>\n"
    "• /set_list_len <i>N</i> — макс. доменов в файле (по умолч. 300)\n"
    "• /set_ip_list_len <i>N</i> — макс. IP-маршрутов в файле (по умолч. 1000)\n\n"
    "<b>Также доступны кнопки внизу клавиатуры.</b>\n"
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _build_status_text(
    domain_count: int, ip_count: int, settings: dict
) -> str:
    mode_label = (
        "алфавитная (abc)" if settings["sort_mode"] == "abc"
        else "по домену (domain)"
    )
    return (
        f"📊 <b>Состояние:</b>\n\n"
        f"🔤 Доменов в списке: <b>{domain_count}</b>\n"
        f"🌐 IP-маршрутов в списке: <b>{ip_count}</b>\n\n"
        f"⚙️ Настройки:\n"
        f"  Сортировка доменов: <b>{mode_label}</b>\n"
        f"  Макс. доменов в файле: <b>{settings['list_len']}</b>\n"
        f"  Макс. IP в файле: <b>{settings['ip_list_len']}</b>\n"
        f"  Первый файл доменов: <b>{settings['first_domain_filename'] or '—'}</b>\n"
        f"  Первый файл IP: <b>{settings['first_ip_filename'] or '—'}</b>"
    )


async def _do_export(user_id: int, message: Message, custom_name: str | None = None) -> None:
    settings = await db.get_settings(user_id)
    domain_count = await db.count_domains(user_id)
    ip_count = await db.count_ip_routes(user_id)

    if domain_count == 0 and ip_count == 0:
        await message.answer(
            "📭 Список пуст. Загрузите файлы с доменами (.txt) или маршрутами (.bat)."
        )
        return

    sent_domains = False
    sent_ips = False

    if domain_count > 0:
        if custom_name:
            base_name = custom_name
        elif settings["first_domain_filename"]:
            base_name = Path(settings["first_domain_filename"]).stem
        else:
            base_name = "domains"

        domains = await db.get_domains(user_id, settings["sort_mode"])

        all_fname, all_content = utils.make_all_file(domains, base_name, "txt")
        await message.answer_document(
            BufferedInputFile(all_content, filename=all_fname),
            caption=f"📋 {all_fname}  ({len(domains)} доменов, полный список)",
        )

        domain_files = utils.make_domain_files(domains, base_name, settings["list_len"])
        for filename, content in domain_files:
            await message.answer_document(
                BufferedInputFile(content, filename=filename),
                caption=f"📄 {filename}  ({len(domains)} доменов)",
            )
        sent_domains = True

    if ip_count > 0:
        if custom_name:
            base_name = custom_name
        elif settings["first_ip_filename"]:
            base_name = Path(settings["first_ip_filename"]).stem
        else:
            base_name = "routes"

        ip_routes = await db.get_ip_routes(user_id)

        all_fname, all_content = utils.make_all_file(ip_routes, base_name, "bat")
        await message.answer_document(
            BufferedInputFile(all_content, filename=all_fname),
            caption=f"📋 {all_fname}  ({len(ip_routes)} маршрутов, полный список)",
        )

        ip_files = utils.make_ip_files(ip_routes, base_name, settings["ip_list_len"])
        for filename, content in ip_files:
            await message.answer_document(
                BufferedInputFile(content, filename=filename),
                caption=f"📄 {filename}  ({len(ip_routes)} маршрутов)",
            )
        sent_ips = True

    if sent_domains:
        await db.clear_domains(user_id)
    if sent_ips:
        await db.clear_ip_routes(user_id)

    await message.answer("✅ Готово! Данные очищены — можно загружать следующую порцию файлов.")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        f"Привет! Отправляй мне файлы — я отсортирую и дедуплицирую списки.\n\n{HELP_TEXT}",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML", reply_markup=main_keyboard())


@dp.message(Command("status"))
async def cmd_status(message: Message) -> None:
    user_id = message.from_user.id
    settings = await db.get_settings(user_id)
    domain_count = await db.count_domains(user_id)
    ip_count = await db.count_ip_routes(user_id)
    text = _build_status_text(domain_count, ip_count, settings)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=status_inline(settings["sort_mode"]),
    )


@dp.message(Command("set_sort"))
async def cmd_set_sort(message: Message) -> None:
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)

    if len(parts) < 2 or parts[1].strip().lower() not in ("abc", "domain"):
        await message.answer(
            "Использование: /set_sort abc или /set_sort domain\n\n"
            "• <b>abc</b> — алфавитная сортировка с начала строки\n"
            "• <b>domain</b> — сортировка по TLD: com → google.com → mail.google.com",
            parse_mode="HTML",
        )
        return

    mode = parts[1].strip().lower()
    await db.update_setting(user_id, "sort_mode", mode)
    label = "алфавитная (abc)" if mode == "abc" else "по домену (domain)"
    await message.answer(
        f"✅ Режим сортировки изменён: <b>{label}</b>",
        parse_mode="HTML",
    )


@dp.message(Command("set_list_len"))
async def cmd_set_list_len(message: Message) -> None:
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer("Использование: /set_list_len <число>\nПример: /set_list_len 100")
        return

    try:
        length = int(parts[1].strip())
        if length < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ Укажите целое положительное число. Пример: /set_list_len 100")
        return

    await db.update_setting(user_id, "list_len", length)
    await message.answer(
        f"✅ Макс. доменов в файле: <b>{length}</b>", parse_mode="HTML"
    )


@dp.message(Command("set_ip_list_len"))
async def cmd_set_ip_list_len(message: Message) -> None:
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer("Использование: /set_ip_list_len <число>\nПример: /set_ip_list_len 500")
        return

    try:
        length = int(parts[1].strip())
        if length < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ Укажите целое положительное число. Пример: /set_ip_list_len 500")
        return

    await db.update_setting(user_id, "ip_list_len", length)
    await message.answer(
        f"✅ Макс. IP-маршрутов в файле: <b>{length}</b>", parse_mode="HTML"
    )


@dp.message(Command("get_list"))
async def cmd_get_list(message: Message) -> None:
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)
    custom_name: str | None = parts[1].strip() if len(parts) > 1 else None
    await _do_export(user_id, message, custom_name)


# ---------------------------------------------------------------------------
# Reply-keyboard text handlers (must be AFTER command handlers)
# ---------------------------------------------------------------------------


@dp.message(F.text == BTN_STATUS)
async def btn_status(message: Message) -> None:
    await cmd_status(message)


@dp.message(F.text == BTN_EXPORT)
async def btn_export(message: Message) -> None:
    await _do_export(message.from_user.id, message)


@dp.message(F.text == BTN_HELP)
async def btn_help(message: Message) -> None:
    await cmd_help(message)


@dp.message(F.text == BTN_SORT_ABC)
async def btn_sort_abc(message: Message) -> None:
    user_id = message.from_user.id
    await db.update_setting(user_id, "sort_mode", "abc")
    await message.answer("✅ Сортировка: <b>алфавитная (abc)</b>", parse_mode="HTML")


@dp.message(F.text == BTN_SORT_DOMAIN)
async def btn_sort_domain(message: Message) -> None:
    user_id = message.from_user.id
    await db.update_setting(user_id, "sort_mode", "domain")
    await message.answer("✅ Сортировка: <b>по домену (domain)</b>", parse_mode="HTML")


# ---------------------------------------------------------------------------
# Inline callback handlers
# ---------------------------------------------------------------------------


@dp.callback_query(F.data.startswith("sort:"))
async def cb_sort(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    mode = callback.data.split(":")[1]

    if mode not in ("abc", "domain"):
        await callback.answer("Неизвестный режим")
        return

    current = await db.get_settings(user_id)
    if current["sort_mode"] == mode:
        label = "алфавитная (abc)" if mode == "abc" else "по домену (domain)"
        await callback.answer(f"Уже выбрано: {label}")
        return

    await db.update_setting(user_id, "sort_mode", mode)

    settings = await db.get_settings(user_id)
    domain_count = await db.count_domains(user_id)
    ip_count = await db.count_ip_routes(user_id)
    text = _build_status_text(domain_count, ip_count, settings)

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=status_inline(mode),
    )
    label = "алфавитная (abc)" if mode == "abc" else "по домену (domain)"
    await callback.answer(f"Сортировка: {label}")


@dp.callback_query(F.data == "get_list")
async def cb_get_list(callback: CallbackQuery) -> None:
    await callback.answer()
    await _do_export(callback.from_user.id, callback.message)


@dp.callback_query(F.data == "show_status")
async def cb_show_status(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    settings = await db.get_settings(user_id)
    domain_count = await db.count_domains(user_id)
    ip_count = await db.count_ip_routes(user_id)
    text = _build_status_text(domain_count, ip_count, settings)
    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=status_inline(settings["sort_mode"]),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Document handler
# ---------------------------------------------------------------------------


@dp.message(F.document)
async def handle_document(message: Message) -> None:
    user_id = message.from_user.id
    document: Document = message.document
    filename: str = document.file_name or "unknown"
    ext = Path(filename).suffix.lower()

    if ext not in (".txt", ".bat"):
        await message.answer(
            f"❌ Неподдерживаемый тип файла: <code>{ext}</code>\n"
            "Принимаю: <code>.txt</code> (домены) и <code>.bat</code> (IP-маршруты).",
            parse_mode="HTML",
        )
        return

    file_info = await bot.get_file(document.file_id)
    raw = await bot.download_file(file_info.file_path)
    content = raw.read().decode("utf-8", errors="replace")

    if ext == ".txt":
        domains = processor.parse_txt(content)
        if not domains:
            await message.answer("⚠️ Файл не содержит доменных имён.")
            return

        new_count, total_in_file, total_in_db = await db.add_domains(
            user_id, domains, filename
        )
        await message.answer(
            f"✅ Добавлено {new_count}/{total_in_file}, всего в списке {total_in_db}",
            reply_markup=after_upload_inline(),
        )

    elif ext == ".bat":
        routes = processor.parse_bat(content)
        if not routes:
            await message.answer(
                "⚠️ Файл не содержит IP-маршрутов в формате "
                "<code>route ADD ip MASK mask 0.0.0.0</code>.",
                parse_mode="HTML",
            )
            return

        new_count, total_in_file, total_in_db = await db.add_ip_routes(
            user_id, routes, filename
        )
        await message.answer(
            f"✅ Добавлено {new_count}/{total_in_file}, всего в списке {total_in_db}",
            reply_markup=after_upload_inline(),
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    await db.init_db()
    logger.info("Bot starting …")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
