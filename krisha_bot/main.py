from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from admin_web import create_admin_app
from config import Settings, load_settings
from db import ASTANA_TZ, BotDB, ROLE_DAYS, UserSettings
from notifier import send_daily_report, send_new_listing, send_onboarding_step, send_subscription_expired
from parser import parse_krisha

logger = logging.getLogger(__name__)


CITY_ALIASES = {
    "astana": {"астана", "astana", "нур-султан", "nur-sultan"},
    "almaty": {"алматы", "almaty"},
}


def _matches_city(listing, city: str) -> bool:
    city = city.lower().strip()
    aliases = CITY_ALIASES.get(city)
    if not aliases:
        return True

    haystack = f"{listing.address} {listing.title}".lower()
    opposite_aliases = set().union(*[vals for key, vals in CITY_ALIASES.items() if key != city])

    if any(alias in haystack for alias in aliases):
        return True
    if any(alias in haystack for alias in opposite_aliases):
        return False
    return True


def _get_onboarding_store(context: ContextTypes.DEFAULT_TYPE) -> dict[int, dict]:
    return context.application.bot_data.setdefault("onboarding", {})


async def _start_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE, db: BotDB) -> None:
    user = update.effective_user
    if not user:
        return

    await db.upsert_user(user.id, user.username)
    store = _get_onboarding_store(context)
    store[user.id] = {"step": 1}
    await update.message.reply_text("Привет! Настроим фильтры поиска.")
    await send_onboarding_step(user.id, 1, context, state=store[user.id])


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: BotDB = context.application.bot_data["db"]
    await _start_onboarding(update, context, db)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: BotDB = context.application.bot_data["db"]
    await _start_onboarding(update, context, db)


async def grant_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    db: BotDB = context.application.bot_data["db"]
    user = update.effective_user
    if not user:
        return

    if user.id != settings.admin_telegram_id:
        await update.message.reply_text("Эта команда только для администратора.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Использование: /grant USER_ID ROLE")
        return

    target_user = int(context.args[0])
    role = int(context.args[1])
    if role not in ROLE_DAYS:
        await update.message.reply_text("ROLE должен быть 1, 2 или 3")
        return

    end = await db.grant_subscription(target_user, role)
    await db.log_event("grant", f"telegram admin={user.id} user={target_user} role={role} end={end}")
    await update.message.reply_text(f"Подписка выдана user={target_user}, role={role}, до {end}")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: BotDB = context.application.bot_data["db"]
    query = update.callback_query
    if not query or not update.effective_user:
        return

    user_id = update.effective_user.id
    store = _get_onboarding_store(context)
    state = store.setdefault(user_id, {"step": 1})

    await query.answer()
    data = query.data or ""

    if data.startswith("city:"):
        state["city"] = data.split(":", 1)[1]
        state["step"] = 2
        await query.edit_message_text(f"Город: {state['city']}")
        await send_onboarding_step(user_id, 2, context, state=state)
        return

    if data.startswith("deal:"):
        state["deal_type"] = data.split(":", 1)[1]
        state["step"] = 3
        await query.edit_message_text(f"Тип сделки: {state['deal_type']}")
        await send_onboarding_step(user_id, 3, context, state=state)
        return

    if data.startswith("price:"):
        value = data.split(":", 1)[1]
        if value == "custom":
            state["step"] = "price_custom"
            await query.edit_message_text("Цена: свой диапазон")
            await context.bot.send_message(chat_id=user_id, text="Введите диапазон цены в формате 100000-500000")
            return

        bounds = _parse_range(value)
        if not bounds:
            await query.edit_message_text("Некорректный диапазон цены")
            return

        state["price_min"], state["price_max"] = bounds
        state["step"] = 4
        await query.edit_message_text(f"Цена: {state['price_min']}-{state['price_max']}")
        await send_onboarding_step(user_id, 4, context, state=state)
        return

    if data.startswith("area:"):
        value = data.split(":", 1)[1]
        if value == "custom":
            state["step"] = "area_custom"
            await query.edit_message_text("Метраж: свой диапазон")
            await context.bot.send_message(chat_id=user_id, text="Введите диапазон метража в формате 40-80")
            return

        bounds = _parse_range(value)
        if not bounds:
            await query.edit_message_text("Некорректный диапазон метража")
            return

        state["area_min"], state["area_max"] = bounds
        state["step"] = 5
        await query.edit_message_text(f"Метраж: {state['area_min']}-{state['area_max']}")
        await send_onboarding_step(user_id, 5, context, state=state)
        return

    await db.log_event("warning", f"unknown callback user={user_id} data={data}")



def _parse_range(text: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", text)
    if not match:
        return None
    left, right = int(match.group(1)), int(match.group(2))
    # right=0 означает диапазон без верхней границы (например, 100 млн+)
    if right == 0:
        return left, 0
    if left > right:
        left, right = right, left
    return left, right


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: BotDB = context.application.bot_data["db"]
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    text = update.message.text or ""
    store = _get_onboarding_store(context)
    state = store.get(user_id)

    if not state:
        return

    step = state.get("step")
    if step == "price_custom":
        parsed = _parse_range(text)
        if not parsed:
            await update.message.reply_text("Формат цены: 100000-500000")
            return
        state["price_min"], state["price_max"] = parsed
        state["step"] = 4
        await send_onboarding_step(user_id, 4, context, state=state)
        return

    if step == "area_custom":
        parsed = _parse_range(text)
        if not parsed:
            await update.message.reply_text("Формат метража: 40-80")
            return
        state["area_min"], state["area_max"] = parsed
        state["step"] = 5
        await send_onboarding_step(user_id, 5, context, state=state)
        return

    if step == 5:
        if not text.isdigit() or not (0 <= int(text) <= 23):
            await update.message.reply_text("Введите час от 0 до 23")
            return

        state["daily_report_hour"] = int(text)
        await db.set_user_filters(
            user_id=user_id,
            city=state["city"],
            deal_type=state["deal_type"],
            price_min=state["price_min"],
            price_max=state["price_max"],
            area_min=state["area_min"],
            area_max=state["area_max"],
            daily_report_hour=state["daily_report_hour"],
        )
        await db.log_event("settings", f"user={user_id} filters updated")
        store.pop(user_id, None)
        await update.message.reply_text("✅ Настройки сохранены. Теперь вы будете получать персональные уведомления.")



def _fits_user_filters(user: UserSettings, listing) -> bool:
    if user.price_min is not None and listing.price < user.price_min:
        return False
    if user.price_max is not None and user.price_max > 0 and listing.price > user.price_max:
        return False
    if user.city and not _matches_city(listing, user.city):
        return False
    return True


async def check_new_listings(app: Application) -> None:
    settings: Settings = app.bot_data["settings"]
    db: BotDB = app.bot_data["db"]

    try:
        active_users = await db.get_active_users()
        grouped: dict[tuple[str, str, int], list[UserSettings]] = defaultdict(list)
        for user in active_users:
            if user.price_max is None or not user.city or not user.deal_type:
                continue
            grouped[(user.city, user.deal_type, user.price_max)].append(user)

        for (city, deal_type, price_max), users in grouped.items():
            price_min_values = [u.price_min for u in users if u.price_min is not None]
            area_min_values = [u.area_min for u in users if u.area_min is not None]
            area_max_values = [u.area_max for u in users if u.area_max is not None]

            request_price_min = min(price_min_values) if price_min_values else None
            request_area_min = min(area_min_values) if area_min_values else None
            request_area_max = max(area_max_values) if area_max_values else None

            local_settings = Settings(**{**asdict(settings), "city": city, "deal_type": deal_type, "max_price": price_max})
            listings = await parse_krisha(
                local_settings,
                deal_type=deal_type,
                price_min=request_price_min,
                price_max=price_max,
                area_min=request_area_min,
                area_max=request_area_max,
            )
            await db.log_event("parser", f"city={city} deal_type={deal_type} listings={len(listings)}")

            for listing in listings:
                await db.save_listing(listing, city=city, deal_type=deal_type)
                for user in users:
                    if not _fits_user_filters(user, listing):
                        continue
                    sent = await db.is_user_notified_about_listing(user.user_id, listing.id)
                    if sent:
                        continue
                    await send_new_listing(app, user.user_id, listing, deal_type=user.deal_type or "rent")
                    await db.mark_user_listing_notified(user.user_id, listing.id)

    except Exception as exc:
        logger.exception("check_new_listings failed")
        await db.log_event("error", f"parser error: {exc}")


async def check_expired_subscriptions(app: Application) -> None:
    db: BotDB = app.bot_data["db"]
    users = await db.get_expired_users()
    for user in users:
        await send_subscription_expired(app, user)
        await db.set_user_blocked(user.user_id, True)
        await db.log_event("subscription", f"expired user={user.user_id}")


async def send_daily_reports(app: Application) -> None:
    db: BotDB = app.bot_data["db"]
    users = await db.get_active_users()

    now_astana = datetime.now(ASTANA_TZ)
    today_key = now_astana.date().isoformat()

    for user in users:
        if user.daily_report_hour is None or user.daily_report_hour != now_astana.hour:
            continue

        already_sent = await db.has_daily_report_event(user.user_id, today_key)
        if already_sent:
            continue

        day_start_astana = datetime(now_astana.year, now_astana.month, now_astana.day, 0, 0, 0, tzinfo=ASTANA_TZ)
        day_end_astana = day_start_astana + timedelta(days=1)
        day_start_utc = day_start_astana.astimezone(timezone.utc)
        day_end_utc = day_end_astana.astimezone(timezone.utc)

        rows = await db.get_user_daily_listings(user.user_id, day_start_utc, day_end_utc)
        await send_daily_report(app, user.user_id, rows)
        await db.log_event("daily_report", f"user:{user.user_id}|date:{today_key}|rows:{len(rows)}")


async def test_mode_once(app: Application) -> None:
    db: BotDB = app.bot_data["db"]
    users = await db.get_active_users()
    if not users:
        return

    first_user = users[0]
    settings: Settings = app.bot_data["settings"]
    local_settings = Settings(**{**asdict(settings), "city": first_user.city or settings.city, "max_price": first_user.price_max or settings.max_price})
    listings = await parse_krisha(local_settings, limit=1, deal_type=first_user.deal_type or local_settings.deal_type, price_min=first_user.price_min, price_max=first_user.price_max, area_min=first_user.area_min, area_max=first_user.area_max)
    if listings:
        await send_new_listing(app, first_user.user_id, listings[0], deal_type=first_user.deal_type or "rent")


async def run_admin_web(db: BotDB, settings: Settings) -> None:
    app = create_admin_app(db, settings.admin_password, settings.bot_version)
    config = uvicorn.Config(app=app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()

    db = BotDB(settings.db_path)
    await db.init()

    app = Application.builder().token(settings.bot_token).build()
    app.bot_data["db"] = db
    app.bot_data["settings"] = settings

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("grant", grant_command))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(check_new_listings, "interval", minutes=1, kwargs={"app": app})
    scheduler.add_job(check_expired_subscriptions, "interval", minutes=10, kwargs={"app": app})
    scheduler.add_job(send_daily_reports, "interval", minutes=10, kwargs={"app": app})
    scheduler.start()

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    if settings.test_mode:
        await test_mode_once(app)

    await asyncio.gather(run_admin_web(db, settings))


if __name__ == "__main__":
    asyncio.run(main())
