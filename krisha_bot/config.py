from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    bot_token: str
    chat_id: str
    max_price: int
    min_rooms: int
    max_rooms: int
    city: str
    check_interval_minutes: int
    test_mode: bool
    db_path: str = "krisha_bot/krisha.db"



def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}



def load_settings() -> Settings:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "")
    chat_id = os.getenv("CHAT_ID", "")

    if not bot_token:
        raise ValueError("BOT_TOKEN is required in .env")
    if not chat_id:
        raise ValueError("CHAT_ID is required in .env")

    return Settings(
        bot_token=bot_token,
        chat_id=chat_id,
        max_price=int(os.getenv("MAX_PRICE", "200000")),
        min_rooms=int(os.getenv("MIN_ROOMS", "1")),
        max_rooms=int(os.getenv("MAX_ROOMS", "5")),
        city=os.getenv("CITY", "astana"),
        check_interval_minutes=int(os.getenv("CHECK_INTERVAL_MINUTES", "15")),
        test_mode=_parse_bool(os.getenv("TEST"), default=False),
        db_path=os.getenv("DB_PATH", "krisha_bot/krisha.db"),
    )
