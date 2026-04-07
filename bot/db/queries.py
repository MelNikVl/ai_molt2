from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Users ─────────────────────────────────────────────────────────────────────

async def upsert_user(db_path: str, user_id: int, username: str | None) -> None:
    now = _now()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO users(user_id, username, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username,
                                               updated_at = excluded.updated_at
            """,
            (user_id, username, now, now),
        )
        await db.commit()


async def get_user(db_path: str, user_id: int) -> dict[str, Any] | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
    if row is None:
        return None
    d = dict(row)
    if d.get("priorities"):
        try:
            d["priorities"] = json.loads(d["priorities"])
        except (json.JSONDecodeError, TypeError):
            d["priorities"] = []
    if d.get("rooms"):
        try:
            d["rooms"] = json.loads(d["rooms"])
        except (json.JSONDecodeError, TypeError):
            d["rooms"] = d["rooms"].split(",") if d["rooms"] else []
    return d


async def save_user_prefs(db_path: str, user_id: int, prefs: dict[str, Any]) -> None:
    now = _now()
    priorities = json.dumps(prefs.get("priorities", []), ensure_ascii=False)
    rooms = json.dumps(prefs.get("rooms", []), ensure_ascii=False)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            UPDATE users
            SET deal_type  = ?,
                city       = ?,
                district   = ?,
                budget_min = ?,
                budget_max = ?,
                rooms      = ?,
                area_min   = ?,
                move_in    = ?,
                priorities = ?,
                updated_at = ?
            WHERE user_id = ?
            """,
            (
                prefs.get("deal_type"),
                prefs.get("city"),
                prefs.get("district"),
                prefs.get("budget_min"),
                prefs.get("budget_max"),
                rooms,
                prefs.get("area_min"),
                prefs.get("move_in"),
                priorities,
                now,
                user_id,
            ),
        )
        await db.commit()


async def get_all_active_users(db_path: str) -> list[dict[str, Any]]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM users WHERE deal_type IS NOT NULL AND city IS NOT NULL"
        )
        rows = await cursor.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get("priorities"):
            try:
                d["priorities"] = json.loads(d["priorities"])
            except (json.JSONDecodeError, TypeError):
                d["priorities"] = []
        if d.get("rooms"):
            try:
                d["rooms"] = json.loads(d["rooms"])
            except (json.JSONDecodeError, TypeError):
                d["rooms"] = d["rooms"].split(",") if d["rooms"] else []
        result.append(d)
    return result


# ── Listings ──────────────────────────────────────────────────────────────────

async def save_listing(db_path: str, listing: dict[str, Any]) -> None:
    sources = json.dumps(listing.get("sources", []), ensure_ascii=False)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO listings
              (id, url, title, price, area, rooms, floor, floors_total,
               address, district, city, deal_type, phone, complex_name,
               photo_url, photo_hash, published_at, found_at, sources)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                listing.get("id"),
                listing.get("url"),
                listing.get("title"),
                listing.get("price"),
                listing.get("area"),
                listing.get("rooms"),
                listing.get("floor"),
                listing.get("floors_total"),
                listing.get("address"),
                listing.get("district"),
                listing.get("city"),
                listing.get("deal_type"),
                listing.get("phone"),
                listing.get("complex_name"),
                listing.get("photo_url"),
                listing.get("photo_hash"),
                listing.get("published_at"),
                _now(),
                sources,
            ),
        )
        await db.commit()


async def get_listing(db_path: str, listing_id: str) -> dict[str, Any] | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM listings WHERE id = ?", (listing_id,)
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    d = dict(row)
    if d.get("sources"):
        try:
            d["sources"] = json.loads(d["sources"])
        except (json.JSONDecodeError, TypeError):
            d["sources"] = []
    return d


async def is_notified(db_path: str, user_id: int, listing_id: str) -> bool:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT 1 FROM user_listing_notifications WHERE user_id=? AND listing_id=?",
            (user_id, listing_id),
        )
        return await cursor.fetchone() is not None


async def mark_notified(db_path: str, user_id: int, listing_id: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_listing_notifications(user_id, listing_id, notified_at) VALUES (?,?,?)",
            (user_id, listing_id, _now()),
        )
        await db.commit()


# ── Favorites ─────────────────────────────────────────────────────────────────

async def add_favorite(db_path: str, user_id: int, listing_id: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO favorites(user_id, listing_id, saved_at) VALUES (?,?,?)",
            (user_id, listing_id, _now()),
        )
        await db.commit()


async def remove_favorite(db_path: str, user_id: int, listing_id: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "DELETE FROM favorites WHERE user_id=? AND listing_id=?",
            (user_id, listing_id),
        )
        await db.commit()


async def is_favorite(db_path: str, user_id: int, listing_id: str) -> bool:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT 1 FROM favorites WHERE user_id=? AND listing_id=?",
            (user_id, listing_id),
        )
        return await cursor.fetchone() is not None


async def get_favorites(db_path: str, user_id: int) -> list[dict[str, Any]]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT l.* FROM favorites f
            JOIN listings l ON l.id = f.listing_id
            WHERE f.user_id = ?
            ORDER BY f.saved_at DESC
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def count_favorites(db_path: str, user_id: int) -> int:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM favorites WHERE user_id=?", (user_id,)
        )
        row = await cursor.fetchone()
    return row[0] if row else 0


# ── Blocked listings ──────────────────────────────────────────────────────────

async def block_listing(db_path: str, user_id: int, listing_id: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO blocked_listings(user_id, listing_id, blocked_at) VALUES (?,?,?)",
            (user_id, listing_id, _now()),
        )
        await db.commit()


async def is_blocked(db_path: str, user_id: int, listing_id: str) -> bool:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT 1 FROM blocked_listings WHERE user_id=? AND listing_id=?",
            (user_id, listing_id),
        )
        return await cursor.fetchone() is not None


# ── Saved searches ────────────────────────────────────────────────────────────

async def add_saved_search(db_path: str, user_id: int, listing_id: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO saved_searches(user_id, listing_id, created_at) VALUES (?,?,?)",
            (user_id, listing_id, _now()),
        )
        await db.commit()


async def is_following(db_path: str, user_id: int, listing_id: str) -> bool:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT 1 FROM saved_searches WHERE user_id=? AND listing_id=?",
            (user_id, listing_id),
        )
        return await cursor.fetchone() is not None


# ── Listing views ─────────────────────────────────────────────────────────────

async def log_view(db_path: str, user_id: int, listing_id: str, action: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO listing_views(user_id, listing_id, action, ts) VALUES (?,?,?,?)",
            (user_id, listing_id, action, _now()),
        )
        await db.commit()


# ── AI cache ──────────────────────────────────────────────────────────────────

async def get_ai_explanation(
    db_path: str, listing_id: str, user_id: int
) -> str | None:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT explanation FROM ai_cache WHERE listing_id=? AND user_id=?",
            (listing_id, user_id),
        )
        row = await cursor.fetchone()
    return row[0] if row else None


async def save_ai_explanation(
    db_path: str, listing_id: str, user_id: int, explanation: str
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO ai_cache(listing_id, user_id, explanation, created_at)
            VALUES (?,?,?,?)
            """,
            (listing_id, user_id, explanation, _now()),
        )
        await db.commit()
