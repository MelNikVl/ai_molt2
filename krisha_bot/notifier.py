from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from typing import Any

from db import UserSettings
from parser import Listing

logger = logging.getLogger(__name__)


CITY_KEYBOARD = InlineKeyboardMarkup(
    [[InlineKeyboardButton("Астана", callback_data="city:astana"), InlineKeyboardButton("Алматы", callback_data="city:almaty")]]
)

DEAL_KEYBOARD = InlineKeyboardMarkup(
    [[InlineKeyboardButton("Аренда", callback_data="deal:rent"), InlineKeyboardButton("Покупка", callback_data="deal:sale")]]
)


def _format_price(price: int) -> str:
    return f"{price:,}".replace(",", " ")


async def send_onboarding_step(chat_id: int, step: int, context: Any) -> None:
    bot = context.bot
    if step == 1:
        await bot.send_message(chat_id=chat_id, text="Шаг 1/5: Выберите город", reply_markup=CITY_KEYBOARD)
    elif step == 2:
        await bot.send_message(chat_id=chat_id, text="Шаг 2/5: Выберите тип сделки", reply_markup=DEAL_KEYBOARD)
    elif step == 3:
        await bot.send_message(chat_id=chat_id, text="Шаг 3/5: Введите диапазон цены: 100000-500000")
    elif step == 4:
        await bot.send_message(chat_id=chat_id, text="Шаг 4/5: Введите диапазон метража (м²): 40-80")
    elif step == 5:
        await bot.send_message(chat_id=chat_id, text="Шаг 5/5: Введите час ежедневной сводки (0-23, по Астане UTC+5)")


async def send_new_listing(context: Any, user_id: int, listing: Listing) -> None:
    title_line = f"🏠 *{listing.title} • {_format_price(listing.price)} ₸/мес*"
    text = (
        f"{title_line}\n"
        f"📍 {listing.address or 'Адрес не указан'}\n"
        f"⏱ Опубликовано {listing.published_at or 'не указано'}\n"
        f"🔗 [Смотреть объявление]({listing.url})"
    )

    try:
        if listing.photo_url:
            await context.bot.send_photo(
                chat_id=user_id,
                photo=listing.photo_url,
                caption=text,
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await context.bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        logger.exception("Failed to send listing to user=%s", user_id)


async def send_subscription_expired(context: Any, user: UserSettings) -> None:
    await context.bot.send_message(
        chat_id=user.user_id,
        text="⛔️ Ваша подписка истекла. Напишите администратору для продления.",
    )


async def send_daily_report(context: Any, user_id: int, rows: list[tuple]) -> None:
    if not rows:
        await context.bot.send_message(chat_id=user_id, text="Сегодня новых объектов по вашим фильтрам не найдено")
        return

    lines = ["📊 *Ежедневная сводка*", "`Адрес | Цена | Метраж | Цена/м² | Ссылка`"]
    for address, price, area, url in rows[:30]:
        price_m2 = "-"
        if area and area > 0:
            price_m2 = f"{int(price / area):,}".replace(",", " ")
        area_text = f"{area:.1f}" if area else "-"
        lines.append(
            f"• {address or '-'} | {price:,} | {area_text} | {price_m2} | [link]({url})".replace(",", " ")
        )

    await context.bot.send_message(chat_id=user_id, text="\n".join(lines), parse_mode=ParseMode.MARKDOWN)
