from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    bot_token: str
    check_interval_minutes: int
    city: str
    deal_type: str
    max_price: int
    min_rooms: int
    max_rooms: int
    test_mode: bool
    db_path: str
    admin_telegram_id: int
    admin_password: str
    bot_version: str



def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}



def load_settings() -> Settings:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "")
    if not bot_token:
        raise ValueError("BOT_TOKEN is required in .env")

    admin_telegram_id = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
    admin_password = os.getenv("ADMIN_PASSWORD", "admin")

    return Settings(
        bot_token=bot_token,
        check_interval_minutes=int(os.getenv("CHECK_INTERVAL_MINUTES", "1")),
        city=os.getenv("CITY", "astana"),
        deal_type=os.getenv("DEAL_TYPE", "rent"),
        max_price=int(os.getenv("MAX_PRICE", "200000")),
        min_rooms=int(os.getenv("MIN_ROOMS", "2")),
        max_rooms=int(os.getenv("MAX_ROOMS", "2")),
        test_mode=_parse_bool(os.getenv("TEST"), default=False),
        db_path=os.getenv("DB_PATH", "krisha_bot/krisha.db"),
        admin_telegram_id=admin_telegram_id,
        admin_password=admin_password,
        bot_version=os.getenv("BOT_VERSION", "0.1.0"),
    )
