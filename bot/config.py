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
    # Try .env in current dir, then repo root, then krisha_bot/ subfolder
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for candidate in [
        os.path.join(_root, ".env"),
        os.path.join(_root, "krisha_bot", ".env"),
        ".env",
    ]:
        if os.path.exists(candidate):
            load_dotenv(candidate)
            break
    else:
        load_dotenv()  # fallback: let python-dotenv search normally

    bot_token = os.getenv("BOT_TOKEN", "")
    if not bot_token:
        raise ValueError("BOT_TOKEN not found. Create .env with BOT_TOKEN=... (see .env.example)")
    return Config(
        bot_token=bot_token,
        db_path=os.getenv("DB_PATH", "bot.db"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        admin_telegram_id=int(os.getenv("ADMIN_TELEGRAM_ID", "0")),
    )
