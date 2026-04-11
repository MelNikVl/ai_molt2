from __future__ import annotations

import aiosqlite

# Unified schema covering both the aiogram onboarding tables and the
# subscription / scheduler / admin tables (formerly in krisha_bot/db.py).
DDL = """
CREATE TABLE IF NOT EXISTS users (
    user_id           INTEGER PRIMARY KEY,
    username          TEXT,
    -- aiogram onboarding prefs
    deal_type         TEXT,
    city              TEXT,
    district          TEXT,
    budget_min        INTEGER,
    budget_max        INTEGER,
    rooms             TEXT,
    area_min          REAL,
    move_in           TEXT,
    priorities        TEXT,
    -- subscription / scheduler fields
    role              INTEGER DEFAULT 1,
    subscription_end  TIMESTAMP,
    price_min         INTEGER,
    price_max         INTEGER,
    area_max          REAL,
    daily_report_hour INTEGER,
    is_blocked        INTEGER DEFAULT 0,
    -- geo / radius filter
    location_lat      REAL,
    location_lon      REAL,
    radius_km         INTEGER,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    sources       TEXT,
    -- geocoded coordinates (cached from Nominatim)
    lat           REAL,
    lon           REAL
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

-- Scheduler / admin tables
CREATE TABLE IF NOT EXISTS user_listings (
    user_id       INTEGER,
    listing_id    TEXT,
    notified_at   TIMESTAMP,
    PRIMARY KEY (user_id, listing_id)
);

CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    type          TEXT,
    description   TEXT,
    created_at    TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bot_requests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER,
    ts            TIMESTAMP
);

CREATE TABLE IF NOT EXISTS parse_errors (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TIMESTAMP,
    error_type    TEXT,
    message       TEXT,
    url           TEXT
);
"""


async def init_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        for statement in DDL.strip().split(";"):
            stmt = statement.strip()
            # Skip comment-only lines
            lines = [ln for ln in stmt.splitlines() if not ln.strip().startswith("--")]
            stmt_clean = "\n".join(lines).strip()
            if stmt_clean:
                await db.execute(stmt_clean)
        await db.commit()

    # Migrations: add columns that may be absent in existing DBs
    _migrations = [
        ("users",    "location_lat",     "REAL"),
        ("users",    "location_lon",     "REAL"),
        ("users",    "radius_km",        "INTEGER"),
        ("listings", "lat",              "REAL"),
        ("listings", "lon",              "REAL"),
    ]
    async with aiosqlite.connect(db_path) as db:
        for table, column, col_type in _migrations:
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                await db.commit()
            except Exception:
                pass  # column already exists — that's fine
