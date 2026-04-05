from __future__ import annotations

import logging
from datetime import datetime, timezone

import aiosqlite

from parser import Listing

logger = logging.getLogger(__name__)


class ListingsDB:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS listings (
                    id TEXT PRIMARY KEY,
                    url TEXT,
                    price INTEGER,
                    title TEXT,
                    address TEXT,
                    photo_url TEXT,
                    first_seen TIMESTAMP,
                    last_price INTEGER,
                    notified BOOLEAN DEFAULT FALSE
                )
                """
            )
            await db.commit()

    async def exists(self, listing_id: str) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("SELECT 1 FROM listings WHERE id = ?", (listing_id,))
                row = await cursor.fetchone()
                return row is not None
        except Exception:
            logger.exception("DB error in exists for id=%s", listing_id)
            return False

    async def save(self, listing: Listing) -> None:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO listings (
                        id, url, price, title, address, photo_url, first_seen, last_price, notified
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        listing.id,
                        listing.url,
                        listing.price,
                        listing.title,
                        listing.address,
                        listing.photo_url,
                        datetime.now(timezone.utc).isoformat(),
                        listing.price,
                        True,
                    ),
                )
                await db.commit()
        except Exception:
            logger.exception("DB error while saving listing id=%s", listing.id)

    async def get_price(self, listing_id: str) -> int | None:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("SELECT last_price FROM listings WHERE id = ?", (listing_id,))
                row = await cursor.fetchone()
                return int(row[0]) if row and row[0] is not None else None
        except Exception:
            logger.exception("DB error in get_price for id=%s", listing_id)
            return None

    async def update_price(self, listing_id: str, new_price: int) -> None:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE listings SET price = ?, last_price = ? WHERE id = ?",
                    (new_price, new_price, listing_id),
                )
                await db.commit()
        except Exception:
            logger.exception("DB error in update_price for id=%s", listing_id)
