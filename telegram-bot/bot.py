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
from aiogram.types import BufferedInputFile, Document, Message
from dotenv import load_dotenv

import database as db
import processor
import utils

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
    "<b>Статус:</b>\n"
    "• /status — размеры списков и текущие настройки\n"
)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Welcome message."""
    await message.answer(
        f"Привет! Отправляй мне файлы — я отсортирую и дедуплицирую списки.\n\n{HELP_TEXT}",
        parse_mode="HTML",
    )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")


@dp.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """Show current list sizes and user settings."""
    user_id = message.from_user.id
    settings = await db.get_settings(user_id)
    domain_count = await db.count_domains(user_id)
    ip_count = await db.count_ip_routes(user_id)

    mode_label = (
        "алфавитная (abc)" if settings["sort_mode"] == "abc"
        else "по домену (domain)"
    )
    text = (
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
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("set_sort"))
async def cmd_set_sort(message: Message) -> None:
    """
    Change domain sort mode.
    Usage: /set_sort abc  |  /set_sort domain
    """
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
    """
    Set max domain records per output file.
    Usage: /set_list_len 100
    """
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
    """
    Set max IP route records per output file.
    Usage: /set_ip_list_len 500
    """
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
    """
    Export current lists and clear data after successful delivery.
    Usage: /get_list [output_name]
    """
    user_id = message.from_user.id
    settings = await db.get_settings(user_id)
    parts = message.text.split(maxsplit=1)
    custom_name: str | None = parts[1].strip() if len(parts) > 1 else None

    domain_count = await db.count_domains(user_id)
    ip_count = await db.count_ip_routes(user_id)

    if domain_count == 0 and ip_count == 0:
        await message.answer(
            "📭 Список пуст. Загрузите файлы с доменами (.txt) или маршрутами (.bat)."
        )
        return

    sent_domains = False
    sent_ips = False

    # ── Export domains ────────────────────────────────────────────────────────
    if domain_count > 0:
        if custom_name:
            base_name = custom_name
        elif settings["first_domain_filename"]:
            base_name = Path(settings["first_domain_filename"]).stem
        else:
            base_name = "domains"

        domains = await db.get_domains(user_id, settings["sort_mode"])
        domain_files = utils.make_domain_files(domains, base_name, settings["list_len"])

        for filename, content in domain_files:
            await message.answer_document(
                BufferedInputFile(content, filename=filename),
                caption=f"📄 {filename}  ({len(domains)} доменов)",
            )
        sent_domains = True

    # ── Export IP routes ──────────────────────────────────────────────────────
    if ip_count > 0:
        if custom_name:
            base_name = custom_name
        elif settings["first_ip_filename"]:
            base_name = Path(settings["first_ip_filename"]).stem
        else:
            base_name = "routes"

        ip_routes = await db.get_ip_routes(user_id)
        ip_files = utils.make_ip_files(ip_routes, base_name, settings["ip_list_len"])

        for filename, content in ip_files:
            await message.answer_document(
                BufferedInputFile(content, filename=filename),
                caption=f"📄 {filename}  ({len(ip_routes)} маршрутов)",
            )
        sent_ips = True

    # ── Clear data after successful delivery ──────────────────────────────────
    if sent_domains:
        await db.clear_domains(user_id)
    if sent_ips:
        await db.clear_ip_routes(user_id)

    await message.answer("✅ Готово! Данные очищены — можно загружать следующую порцию файлов.")


# ---------------------------------------------------------------------------
# Document handler
# ---------------------------------------------------------------------------


@dp.message(F.document)
async def handle_document(message: Message) -> None:
    """Handle uploaded .txt (domains) and .bat (IP routes) files."""
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

    # Download
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
            f"✅ Добавлено {new_count}/{total_in_file}, всего в списке {total_in_db}"
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
            f"✅ Добавлено {new_count}/{total_in_file}, всего в списке {total_in_db}"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    await db.init_db()
    logger.info("Bot starting …")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
