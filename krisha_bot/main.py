from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import load_settings
from db import ListingsDB
from notifier import TelegramNotifier
from parser import Listing, parse_krisha

logger = logging.getLogger(__name__)


async def check_new_listings(db: ListingsDB, notifier: TelegramNotifier) -> None:
    settings = load_settings()

    try:
        listings = await parse_krisha(settings)
    except Exception:
        logger.exception("Unexpected parser error")
        return

    for listing in listings:
        try:
            if not await db.exists(listing.id):
                await db.save(listing)
                await notifier.send_new(listing)
            else:
                old_price = await db.get_price(listing.id)
                if old_price is not None and listing.price < old_price:
                    await db.update_price(listing.id, listing.price)
                    await notifier.send_price_drop(listing, old_price)
        except Exception:
            logger.exception("Failed to process listing id=%s", listing.id)


async def run_test_mode(db: ListingsDB, notifier: TelegramNotifier) -> None:
    settings = load_settings()
    logger.info("TEST=true detected. Sending one listing immediately.")

    listings = await parse_krisha(settings, limit=1)
    if not listings:
        logger.warning("Test mode: no listings found.")
        return

    listing: Listing = listings[0]
    if not await db.exists(listing.id):
        await db.save(listing)
    await notifier.send_new(listing)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    settings = load_settings()
    db = ListingsDB(settings.db_path)
    await db.init()

    notifier = TelegramNotifier(settings.bot_token, settings.chat_id)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        check_new_listings,
        trigger="interval",
        minutes=settings.check_interval_minutes,
        kwargs={"db": db, "notifier": notifier},
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()

    logger.info("Scheduler started. Interval: %s min", settings.check_interval_minutes)

    if settings.test_mode:
        await run_test_mode(db, notifier)

    await check_new_listings(db, notifier)

    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
