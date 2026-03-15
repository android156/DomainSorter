"""
database.py — All SQL interactions via aiosqlite.
Isolates each user's data by user_id.
"""

import logging
import os
from pathlib import Path
from typing import Optional

import aiosqlite

DB_PATH = Path(
    os.getenv("DOMAIN_SORTER_DB_PATH", str(Path(__file__).parent / "bot_data.db"))
)

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Create all required tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                user_id         INTEGER PRIMARY KEY,
                sort_mode       TEXT    DEFAULT 'abc',
                list_len        INTEGER DEFAULT 300,
                ip_list_len     INTEGER DEFAULT 1000,
                first_domain_filename TEXT,
                first_ip_filename     TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS domain_items (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                domain  TEXT    NOT NULL,
                UNIQUE(user_id, domain)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ip_items (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                ip            TEXT    NOT NULL,
                mask          TEXT    NOT NULL,
                original_line TEXT    NOT NULL,
                sort_key      BLOB    NOT NULL,
                UNIQUE(user_id, ip, mask)
            )
        """)
        await db.commit()
    logger.info("Database initialised at %s", DB_PATH)


async def _ensure_settings(db: aiosqlite.Connection, user_id: int) -> None:
    """Insert default settings row for user if absent."""
    await db.execute(
        "INSERT OR IGNORE INTO settings (user_id) VALUES (?)", (user_id,)
    )


async def get_settings(user_id: int) -> dict:
    """Return settings dict for the user (with defaults if not yet saved)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM settings WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
    return {
        "user_id": user_id,
        "sort_mode": "abc",
        "list_len": 300,
        "ip_list_len": 1000,
        "first_domain_filename": None,
        "first_ip_filename": None,
    }


async def update_setting(user_id: int, key: str, value) -> None:
    """Update a single setting field for the user."""
    allowed = {"sort_mode", "list_len", "ip_list_len",
                "first_domain_filename", "first_ip_filename"}
    if key not in allowed:
        raise ValueError(f"Unknown setting key: {key!r}")
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_settings(db, user_id)
        await db.execute(
            f"UPDATE settings SET {key} = ? WHERE user_id = ?", (value, user_id)
        )
        await db.commit()
    logger.info("Setting %s=%r updated for user %d", key, value, user_id)


async def add_domains(
    user_id: int, domains: list[str], filename: str
) -> tuple[int, int, int]:
    """
    Insert domains (skip duplicates per user).

    Returns
    -------
    (new_count, total_in_file, total_in_db)
        new_count     — how many were actually inserted
        total_in_file — total items in the uploaded file
        total_in_db   — total domains stored for this user after insert
    """
    total_in_file = len(domains)
    new_count = 0

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_settings(db, user_id)

        async with db.execute(
            "SELECT first_domain_filename FROM settings WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if row and not row[0]:
                await db.execute(
                    "UPDATE settings SET first_domain_filename = ? WHERE user_id = ?",
                    (filename, user_id),
                )

        for domain in domains:
            try:
                await db.execute(
                    "INSERT INTO domain_items (user_id, domain) VALUES (?, ?)",
                    (user_id, domain),
                )
                new_count += 1
            except aiosqlite.IntegrityError:
                pass

        await db.commit()

        async with db.execute(
            "SELECT COUNT(*) FROM domain_items WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            total_in_db: int = row[0]

    logger.info(
        "add_domains: user=%d added=%d/%d total=%d",
        user_id, new_count, total_in_file, total_in_db,
    )
    return new_count, total_in_file, total_in_db


async def add_ip_routes(
    user_id: int, routes: list[dict], filename: str
) -> tuple[int, int, int]:
    """
    Insert IP routes (skip duplicates per user).

    Each route dict must contain: ip, mask, original_line, sort_key (bytes).

    Returns
    -------
    (new_count, total_in_file, total_in_db)
    """
    total_in_file = len(routes)
    new_count = 0

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_settings(db, user_id)

        async with db.execute(
            "SELECT first_ip_filename FROM settings WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            if row and not row[0]:
                await db.execute(
                    "UPDATE settings SET first_ip_filename = ? WHERE user_id = ?",
                    (filename, user_id),
                )

        for route in routes:
            try:
                await db.execute(
                    "INSERT INTO ip_items (user_id, ip, mask, original_line, sort_key)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (
                        user_id,
                        route["ip"],
                        route["mask"],
                        route["original_line"],
                        route["sort_key"],
                    ),
                )
                new_count += 1
            except aiosqlite.IntegrityError:
                pass

        await db.commit()

        async with db.execute(
            "SELECT COUNT(*) FROM ip_items WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            total_in_db: int = row[0]

    logger.info(
        "add_ip_routes: user=%d added=%d/%d total=%d",
        user_id, new_count, total_in_file, total_in_db,
    )
    return new_count, total_in_file, total_in_db


async def get_domains(user_id: int, sort_mode: str) -> list[str]:
    """
    Return all domains for user, sorted according to sort_mode.

    Modes
    -----
    abc    — plain alphabetical sort
    domain — right-to-left (TLD first), e.g. com.google.mail < com.google.www
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT domain FROM domain_items WHERE user_id = ?", (user_id,)
        ) as cur:
            rows = await cur.fetchall()

    domains = [row[0] for row in rows]

    if sort_mode == "abc":
        domains.sort()
    else:
        domains.sort(key=lambda d: tuple(reversed(d.split("."))))

    return domains


async def get_ip_routes(user_id: int) -> list[str]:
    """Return original_line values for all IP routes, ordered by sort_key."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT original_line FROM ip_items WHERE user_id = ? ORDER BY sort_key",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [row[0] for row in rows]


async def clear_domains(user_id: int) -> None:
    """Delete all domain records and reset first_domain_filename for user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM domain_items WHERE user_id = ?", (user_id,))
        await db.execute(
            "UPDATE settings SET first_domain_filename = NULL WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()
    logger.info("Cleared domain data for user %d", user_id)


async def clear_ip_routes(user_id: int) -> None:
    """Delete all IP route records and reset first_ip_filename for user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM ip_items WHERE user_id = ?", (user_id,))
        await db.execute(
            "UPDATE settings SET first_ip_filename = NULL WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()
    logger.info("Cleared IP route data for user %d", user_id)


async def count_domains(user_id: int) -> int:
    """Return number of domain records stored for user."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM domain_items WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0]


async def count_ip_routes(user_id: int) -> int:
    """Return number of IP route records stored for user."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM ip_items WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0]
