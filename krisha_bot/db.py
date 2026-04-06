from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import aiosqlite

from parser import Listing

logger = logging.getLogger(__name__)

ASTANA_TZ = timezone(timedelta(hours=5))
ROLE_DAYS = {1: 1, 2: 7, 3: 30}


@dataclass(slots=True)
class UserSettings:
    user_id: int
    username: str | None
    role: int
    subscription_end: str | None
    city: str | None
    deal_type: str | None
    price_min: int | None
    price_max: int | None
    area_min: int | None
    area_max: int | None
    daily_report_hour: int | None
    is_blocked: int


class BotDB:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    role INTEGER DEFAULT 1,
                    subscription_end TIMESTAMP,
                    city TEXT,
                    deal_type TEXT,
                    price_min INTEGER,
                    price_max INTEGER,
                    area_min INTEGER,
                    area_max INTEGER,
                    daily_report_hour INTEGER,
                    is_blocked INTEGER DEFAULT 0,
                    created_at TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS listings (
                    id TEXT PRIMARY KEY,
                    url TEXT,
                    title TEXT,
                    price INTEGER,
                    area REAL,
                    address TEXT,
                    city TEXT,
                    deal_type TEXT,
                    found_at TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_listings (
                    user_id INTEGER,
                    listing_id TEXT,
                    notified_at TIMESTAMP,
                    PRIMARY KEY(user_id, listing_id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT,
                    description TEXT,
                    created_at TIMESTAMP
                )
                """
            )
            await db.commit()

    async def log_event(self, event_type: str, description: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO events(type, description, created_at) VALUES (?, ?, ?)",
                (event_type, description, datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()

    async def upsert_user(self, user_id: int, username: str | None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        default_end = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO users(user_id, username, role, subscription_end, created_at)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
                """,
                (user_id, username, default_end, now),
            )
            await db.commit()

    async def set_user_filters(
        self,
        user_id: int,
        city: str,
        deal_type: str,
        price_min: int,
        price_max: int,
        area_min: int,
        area_max: int,
        daily_report_hour: int,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE users
                SET city=?, deal_type=?, price_min=?, price_max=?, area_min=?, area_max=?, daily_report_hour=?
                WHERE user_id=?
                """,
                (city, deal_type, price_min, price_max, area_min, area_max, daily_report_hour, user_id),
            )
            await db.commit()

    async def get_user(self, user_id: int) -> UserSettings | None:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT user_id, username, role, subscription_end, city, deal_type, price_min, price_max,
                       area_min, area_max, daily_report_hour, is_blocked
                FROM users WHERE user_id=?
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
        if not row:
            return None
        return UserSettings(*row)

    async def get_active_users(self) -> list[UserSettings]:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT user_id, username, role, subscription_end, city, deal_type, price_min, price_max,
                       area_min, area_max, daily_report_hour, is_blocked
                FROM users
                WHERE is_blocked=0
                  AND city IS NOT NULL
                  AND deal_type IS NOT NULL
                  AND subscription_end IS NOT NULL
                  AND subscription_end > ?
                """,
                (now,),
            )
            rows = await cursor.fetchall()
        return [UserSettings(*r) for r in rows]

    async def get_expired_users(self) -> list[UserSettings]:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT user_id, username, role, subscription_end, city, deal_type, price_min, price_max,
                       area_min, area_max, daily_report_hour, is_blocked
                FROM users
                WHERE is_blocked=0 AND subscription_end IS NOT NULL AND subscription_end <= ?
                """,
                (now,),
            )
            rows = await cursor.fetchall()
        return [UserSettings(*r) for r in rows]

    async def is_user_notified_about_listing(self, user_id: int, listing_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM user_listings WHERE user_id=? AND listing_id=?",
                (user_id, listing_id),
            )
            row = await cursor.fetchone()
        return row is not None

    async def save_listing(self, listing: Listing, city: str, deal_type: str) -> None:
        area = _extract_area_from_title(listing.title)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO listings(id, url, title, price, area, address, city, deal_type, found_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    listing.id,
                    listing.url,
                    listing.title,
                    listing.price,
                    area,
                    listing.address,
                    city,
                    deal_type,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()

    async def mark_user_listing_notified(self, user_id: int, listing_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO user_listings(user_id, listing_id, notified_at) VALUES (?, ?, ?)",
                (user_id, listing_id, datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()

    async def grant_subscription(self, user_id: int, role: int) -> str:
        if role not in ROLE_DAYS:
            raise ValueError("Role must be 1, 2, or 3")

        await self.upsert_user(user_id, None)
        end_date = datetime.now(timezone.utc) + timedelta(days=ROLE_DAYS[role])
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET role=?, subscription_end=? WHERE user_id=?",
                (role, end_date.isoformat(), user_id),
            )
            await db.commit()
        return end_date.isoformat()

    async def set_user_blocked(self, user_id: int, blocked: bool) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET is_blocked=? WHERE user_id=?", (1 if blocked else 0, user_id))
            await db.commit()

    async def get_recent_events(self, limit: int = 100) -> list[tuple]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id, type, description, created_at FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return await cursor.fetchall()

    async def get_dashboard_stats(self) -> dict[str, int | str | None]:
        async with aiosqlite.connect(self.db_path) as db:
            now = datetime.now(timezone.utc)
            since_day = (now - timedelta(days=1)).isoformat()
            now_iso = now.isoformat()
            total_users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
            active_users = (
                await (
                    await db.execute(
                        "SELECT COUNT(*) FROM users WHERE is_blocked=0 AND subscription_end IS NOT NULL AND subscription_end > ?",
                        (now_iso,),
                    )
                ).fetchone()
            )[0]
            new_day = (
                await (await db.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (since_day,))).fetchone()
            )[0]
            parsed_today = (
                await (await db.execute("SELECT COUNT(*) FROM listings WHERE found_at >= ?", (since_day,))).fetchone()
            )[0]
            last_parser = (await (await db.execute("SELECT MAX(found_at) FROM listings")).fetchone())[0]
        return {
            "total_users": total_users,
            "active_users": active_users,
            "new_users_day": new_day,
            "parsed_today": parsed_today,
            "last_parser": last_parser,
        }

    async def get_users_admin(self) -> list[tuple]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT user_id, username, role, subscription_end,
                       city, deal_type, price_min, price_max, area_min, area_max,
                       daily_report_hour, is_blocked
                FROM users
                ORDER BY created_at DESC
                """
            )
            return await cursor.fetchall()

    async def get_user_daily_listings(self, user_id: int, day_start_utc: datetime, day_end_utc: datetime) -> list[tuple]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT l.address, l.price, l.area, l.url
                FROM user_listings ul
                JOIN listings l ON l.id = ul.listing_id
                WHERE ul.user_id=? AND ul.notified_at >= ? AND ul.notified_at < ?
                ORDER BY ul.notified_at DESC
                """,
                (user_id, day_start_utc.isoformat(), day_end_utc.isoformat()),
            )
            return await cursor.fetchall()

    async def has_daily_report_event(self, user_id: int, day_key: str) -> bool:
        marker = f"user:{user_id}|date:{day_key}"
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM events WHERE type='daily_report' AND description LIKE ? LIMIT 1",
                (f"%{marker}%",),
            )
            return await cursor.fetchone() is not None


def _extract_area_from_title(title: str) -> float | None:
    match = re.search(r"(\d+[\.,]?\d*)\s*м²", title.lower())
    if not match:
        return None
    value = match.group(1).replace(",", ".")
    try:
        return float(value)
    except ValueError:
        logger.warning("Failed to parse area from title: %s", title)
        return None
