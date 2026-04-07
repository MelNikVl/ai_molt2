from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Config:
    bot_token: str
    db_path: str
    anthropic_api_key: str
    admin_telegram_id: int


def load_config() -> Config:
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN", "")
    if not bot_token:
        raise ValueError("BOT_TOKEN is required in .env")
    return Config(
        bot_token=bot_token,
        db_path=os.getenv("DB_PATH", "bot.db"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        admin_telegram_id=int(os.getenv("ADMIN_TELEGRAM_ID", "0")),
    )
