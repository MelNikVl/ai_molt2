from __future__ import annotations

import aiosqlite

DDL = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY,
    username      TEXT,
    deal_type     TEXT,
    city          TEXT,
    district      TEXT,
    budget_min    INTEGER,
    budget_max    INTEGER,
    rooms         TEXT,
    area_min      REAL,
    move_in       TEXT,
    priorities    TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS listings (
    id            TEXT PRIMARY KEY,
    url           TEXT,
    title         TEXT,
    price         INTEGER,
    area          REAL,
    rooms         INTEGER,
    floor         INTEGER,
    floors_total  INTEGER,
    address       TEXT,
    district      TEXT,
    city          TEXT,
    deal_type     TEXT,
    phone         TEXT,
    complex_name  TEXT,
    photo_url     TEXT,
    photo_hash    TEXT,
    published_at  TEXT,
    found_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sources       TEXT
);

CREATE TABLE IF NOT EXISTS favorites (
    user_id       INTEGER,
    listing_id    TEXT,
    saved_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, listing_id)
);

CREATE TABLE IF NOT EXISTS blocked_listings (
    user_id       INTEGER,
    listing_id    TEXT,
    blocked_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, listing_id)
);

CREATE TABLE IF NOT EXISTS saved_searches (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER,
    listing_id    TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_listing_notifications (
    user_id       INTEGER,
    listing_id    TEXT,
    notified_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, listing_id)
);

CREATE TABLE IF NOT EXISTS listing_views (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER,
    listing_id    TEXT,
    action        TEXT,
    ts            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_cache (
    listing_id    TEXT,
    user_id       INTEGER,
    explanation   TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (listing_id, user_id)
);
"""


async def init_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        for statement in DDL.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                await db.execute(stmt)
        await db.commit()
