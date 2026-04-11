"""
Background jobs for the modernised bot.

Scheduler functions use aiogram Bot directly (no PTB Application).
"""
from __future__ import annotations

import asyncio
import logging
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aiogram import Bot
    from bot.config import Config
    from bot.db.compat import BotDB, UserSettings

logger = logging.getLogger(__name__)

ASTANA_TZ = timezone(timedelta(hours=5))

# ─────────────────────────────── helpers ──────────────────────────────────────

def _matches_city(listing: Any, city: str) -> bool:
    _ALIASES: dict[str, set[str]] = {
        "astana": {"астана", "astana", "нур-султан", "nur-sultan"},
        "almaty": {"алматы", "almaty"},
    }
    city = city.lower().strip()
    aliases = _ALIASES.get(city)
    if not aliases:
        return True
    haystack = f"{listing.address} {listing.title}".lower()
    opposite = set().union(*[vals for k, vals in _ALIASES.items() if k != city])
    if any(a in haystack for a in aliases):
        return True
    if any(a in haystack for a in opposite):
        return False
    return True


def _fits_user_filters(user: "UserSettings", listing: Any) -> bool:
    if user.price_min is not None and listing.price < user.price_min:
        return False
    if user.price_max is not None and user.price_max > 0 and listing.price > user.price_max:
        return False
    if user.city and not _matches_city(listing, user.city):
        return False
    return True


# ──────────────────────────── notification senders ────────────────────────────

async def _send_new_listing(bot: "Bot", user_id: int, listing: Any, deal_type: str) -> None:
    """Send a listing card using the aiogram bot."""
    from bot.core.cards import send_listing_card

    listing_dict = listing.to_dict()
    listing_dict["deal_type"] = deal_type
    try:
        await send_listing_card(bot, user_id, listing_dict)
    except Exception:
        logger.exception("_send_new_listing failed user=%s listing=%s", user_id, listing.id)


async def _send_subscription_expired(bot: "Bot", user_id: int) -> None:
    try:
        await bot.send_message(
            chat_id=user_id,
            text="⛔️ Ваша подписка истекла. Напишите администратору для продления.",
        )
    except Exception:
        logger.exception("Failed to send expiry notice to user=%s", user_id)


async def _send_daily_report(bot: "Bot", user_id: int, rows: list[tuple]) -> None:
    if not rows:
        try:
            await bot.send_message(
                chat_id=user_id,
                text="Сегодня новых объектов по вашим фильтрам не найдено",
            )
        except Exception:
            logger.exception("Failed to send empty daily report to user=%s", user_id)
        return

    lines = ["📊 <b>Ежедневная сводка</b>", "<code>Адрес | Цена | Метраж | Цена/м² | Ссылка</code>"]
    for address, price, area, url in rows[:30]:
        price_m2 = "-"
        if area and area > 0:
            price_m2 = f"{int(price / area):,}".replace(",", "\u2009")
        area_text = f"{area:.1f}" if area else "-"
        price_fmt = f"{price:,}".replace(",", "\u2009")
        lines.append(f"• {address or '-'} | {price_fmt} | {area_text} | {price_m2} | <a href='{url}'>link</a>")

    try:
        await bot.send_message(
            chat_id=user_id,
            text="\n".join(lines),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("Failed to send daily report to user=%s", user_id)


# ─────────────────────────── scheduled tasks ──────────────────────────────────

async def _get_listing_coords(listing: Any, db_path: str) -> tuple[float, float] | None:
    """
    Return (lat, lon) for a listing.
    Tries the DB cache first; geocodes via Nominatim on cache miss and stores result.
    """
    from bot.core.geo import geocode
    from bot.db.queries import get_listing_coords, save_listing_coords

    # Check cache
    cached = await get_listing_coords(db_path, listing.id)
    if cached:
        return cached

    # Geocode — use district or full address
    address = listing.district or listing.address
    if not address:
        return None

    coords = await geocode(address)
    if coords:
        await save_listing_coords(db_path, listing.id, coords[0], coords[1])
    return coords


async def check_new_listings(bot: "Bot", db: "BotDB", config: "Config") -> None:
    """Fetch new listings for all active users and send notifications."""
    from bot.core.geo import within_radius
    from bot.core.parser import parse_krisha
    from bot.db.queries import get_users_with_location

    try:
        active_users = await db.get_active_users()
        grouped: dict[tuple[str, str, int], list] = defaultdict(list)
        for user in active_users:
            if user.price_max is None or not user.city or not user.deal_type:
                continue
            grouped[(user.city, user.deal_type, user.price_max)].append(user)

        # Load geo-filter users (from the new aiogram schema)
        geo_users = await get_users_with_location(config.db_path)
        geo_by_id: dict[int, dict] = {u["user_id"]: u for u in geo_users}

        for (city, deal_type, price_max), users in grouped.items():
            price_min_vals = [u.price_min for u in users if u.price_min is not None]
            area_min_vals = [u.area_min for u in users if u.area_min is not None]
            area_max_vals = [u.area_max for u in users if u.area_max is not None]

            req_price_min = min(price_min_vals) if price_min_vals else None
            req_area_min = min(area_min_vals) if area_min_vals else None
            req_area_max = max(area_max_vals) if area_max_vals else None

            from dataclasses import replace
            local_cfg = replace(config, city=city, deal_type=deal_type, max_price=price_max)

            listings = await parse_krisha(
                local_cfg,
                deal_type=deal_type,
                price_min=req_price_min,
                price_max=price_max,
                area_min=req_area_min,
                area_max=req_area_max,
                db=db,
            )
            await db.log_event("parser", f"city={city} deal_type={deal_type} listings={len(listings)}")

            for listing in listings:
                await db.save_listing(listing, city=city, deal_type=deal_type)
                for user in users:
                    if not _fits_user_filters(user, listing):
                        continue
                    if await db.is_user_notified_about_listing(user.user_id, listing.id):
                        continue

                    # Geo filter: if user has a radius set, check distance
                    geo = geo_by_id.get(user.user_id)
                    if geo and geo.get("location_lat") is not None:
                        coords = await _get_listing_coords(listing, config.db_path)
                        if coords:
                            if not within_radius(
                                geo["location_lat"], geo["location_lon"],
                                float(geo["radius_km"]),
                                coords[0], coords[1],
                            ):
                                continue
                        # If geocoding failed, let the listing through (don't block it)

                    await _send_new_listing(bot, user.user_id, listing, deal_type=user.deal_type or "rent")
                    await db.mark_user_listing_notified(user.user_id, listing.id)

    except Exception as exc:
        logger.exception("check_new_listings failed")
        await db.log_event("error", f"parser error: {exc}")


async def check_expired_subscriptions(bot: "Bot", db: "BotDB") -> None:
    """Notify and block users whose subscriptions have expired."""
    try:
        users = await db.get_expired_users()
        for user in users:
            await _send_subscription_expired(bot, user.user_id)
            await db.set_user_blocked(user.user_id, True)
            await db.log_event("subscription", f"expired user={user.user_id}")
    except Exception:
        logger.exception("check_expired_subscriptions failed")


async def send_daily_reports(bot: "Bot", db: "BotDB") -> None:
    """Send daily listing summaries to users whose report hour has arrived."""
    try:
        users = await db.get_active_users()
        now_astana = datetime.now(ASTANA_TZ)
        today_key = now_astana.date().isoformat()

        for user in users:
            if user.daily_report_hour is None or user.daily_report_hour != now_astana.hour:
                continue
            if await db.has_daily_report_event(user.user_id, today_key):
                continue

            day_start = datetime(now_astana.year, now_astana.month, now_astana.day, tzinfo=ASTANA_TZ)
            day_end = day_start + timedelta(days=1)
            rows = await db.get_user_daily_listings(
                user.user_id,
                day_start.astimezone(timezone.utc),
                day_end.astimezone(timezone.utc),
            )
            await _send_daily_report(bot, user.user_id, rows)
            await db.log_event("daily_report", f"user:{user.user_id}|date:{today_key}|rows:{len(rows)}")
    except Exception:
        logger.exception("send_daily_reports failed")


async def parser_loop(bot: "Bot", db: "BotDB", config: "Config") -> None:
    """Run check_new_listings in an infinite loop with a random 1–5 min pause."""
    while True:
        delay = random.randint(60, 300)
        await asyncio.sleep(delay)
        await check_new_listings(bot, db, config)
