"""
Bot entry point.

Sets up the aiogram dispatcher, registers routers, initialises the DB,
runs the admin web panel (FastAPI on :8080), and launches the random-interval
parser loop and APScheduler-based subscription/daily-report jobs.
"""
from __future__ import annotations

import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.admin_web import create_admin_app
from bot.config import load_config
from bot.db.compat import BotDB
from bot.db.models import init_db
from bot.handlers import alerts as alerts_handler
from bot.handlers import location as location_handler
from bot.handlers import menu as menu_handler
from bot.handlers import start as start_handler
from bot.jobs.scheduler import check_expired_subscriptions, check_price_changes, parser_loop, send_daily_reports

logger = logging.getLogger(__name__)


def _make_db_middleware(db_path: str):
    """Inject db_path into every handler via the data dict."""
    from aiogram import BaseMiddleware
    from aiogram.types import TelegramObject

    class DbMiddleware(BaseMiddleware):
        async def __call__(self, handler, event: TelegramObject, data: dict):
            data["db_path"] = db_path
            return await handler(event, data)

    return DbMiddleware()


def _make_request_counter_middleware(compat_db: BotDB):
    """Middleware that records every incoming update in bot_requests table."""
    from aiogram import BaseMiddleware
    from aiogram.types import TelegramObject

    class RequestCounterMiddleware(BaseMiddleware):
        async def __call__(self, handler, event: TelegramObject, data: dict):
            user = data.get("event_from_user")
            user_id = user.id if user else None
            try:
                await compat_db.log_bot_request(user_id)
            except Exception:
                pass  # never crash the bot over metrics
            return await handler(event, data)

    return RequestCounterMiddleware()


async def _run_admin_web(compat_db: BotDB, admin_password: str, bot_version: str, db_path: str) -> None:
    app = create_admin_app(compat_db, admin_password, bot_version, db_path=db_path)
    config = uvicorn.Config(app=app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("bot.log", encoding="utf-8"),
        ],
    )

    cfg = load_config()

    # Initialise aiogram DB tables
    await init_db(cfg.db_path)

    # Initialise compat DB (subscription / scheduler / admin tables)
    compat_db = BotDB(cfg.db_path)
    await compat_db.init()

    logger.info("Database initialised at %s", cfg.db_path)

    bot = Bot(
        token=cfg.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())

    # Middleware: inject db_path + count requests (all relevant update types)
    db_mw = _make_db_middleware(cfg.db_path)
    counter_mw = _make_request_counter_middleware(compat_db)
    for obs in (dp.message, dp.callback_query, dp.edited_message):
        obs.middleware(db_mw)
        obs.outer_middleware(counter_mw)

    # Register routers
    dp.include_router(start_handler.router)
    dp.include_router(menu_handler.router)
    dp.include_router(alerts_handler.router)
    dp.include_router(location_handler.router)

    # APScheduler: subscription expiry + daily reports (every 10 min)
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        check_expired_subscriptions, "interval", minutes=10,
        kwargs={"bot": bot, "db": compat_db},
    )
    scheduler.add_job(
        send_daily_reports, "interval", minutes=10,
        kwargs={"bot": bot, "db": compat_db},
    )
    scheduler.add_job(
        check_price_changes, "interval", minutes=30,
        kwargs={"bot": bot, "db_path": cfg.db_path},
    )
    scheduler.start()

    logger.info("Starting bot polling…")

    await asyncio.gather(
        dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()),
        _run_admin_web(compat_db, cfg.admin_password, cfg.bot_version, cfg.db_path),
        parser_loop(bot, compat_db, cfg),
    )


if __name__ == "__main__":
    asyncio.run(main())
