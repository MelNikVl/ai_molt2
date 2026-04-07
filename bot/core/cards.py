"""
Listing card formatter.

Builds Telegram message text and InlineKeyboardMarkup for a listing card.
"""
from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.core.scorer import score, top_positive_reasons


def _fmt_price(price: int | None, deal_type: str | None) -> str:
    if price is None:
        return "Цена не указана"
    formatted = f"{price:,}".replace(",", "\u2009")  # thin space
    suffix = "₸/мес" if deal_type == "rent" else "₸"
    return f"{formatted} {suffix}"


def _fmt_area(area: float | None) -> str:
    if area is None:
        return "—"
    return f"{area:.0f} м²"


def _fmt_floor(floor: int | None, floors_total: int | None) -> str:
    if floor is None:
        return ""
    if floors_total:
        return f"{floor}/{floors_total} эт."
    return f"{floor} эт."


def _fmt_rooms(rooms: int | None) -> str:
    if rooms is None:
        return ""
    if rooms >= 4:
        return "4+ комн."
    return f"{rooms}-комн."


def _fmt_date(published_at: str | None) -> str:
    if not published_at:
        return "дата неизвестна"
    # Try to shorten common Krisha date formats; fall back to raw string
    text = published_at.lower()
    replacements = [
        ("сегодня", "сегодня"),
        ("вчера", "вчера"),
    ]
    for kw, out in replacements:
        if kw in text:
            return out
    return published_at[:16] if len(published_at) > 16 else published_at


def _fmt_source(sources: list[str] | None) -> str:
    if not sources:
        return "источник неизвестен"
    return ", ".join(sources[:2])


def build_card_text(listing: dict[str, Any], prefs: dict[str, Any] | None = None) -> str:
    """
    Build the Telegram message text for a listing card.

    Format:
        💰 25 000 ₸/мес
        📍 Алмалинский р-н, 65 м², 2-комн., 5/12 эт.
        📅 krisha.kz • сегодня

        ✅ Почему подходит:
        • Цена в бюджете
        • Район совпадает
        • Площадь соответствует
    """
    deal_type = listing.get("deal_type")
    price_line = f"💰 {_fmt_price(listing.get('price'), deal_type)}"

    parts = []
    if listing.get("district"):
        parts.append(listing["district"])
    elif listing.get("address"):
        parts.append(listing["address"])
    if listing.get("area"):
        parts.append(_fmt_area(listing["area"]))
    if listing.get("rooms"):
        parts.append(_fmt_rooms(listing["rooms"]))
    floor_str = _fmt_floor(listing.get("floor"), listing.get("floors_total"))
    if floor_str:
        parts.append(floor_str)
    location_line = "📍 " + (", ".join(parts) if parts else "адрес не указан")

    source_str = _fmt_source(listing.get("sources") or ([listing["source"]] if listing.get("source") else None))
    date_str = _fmt_date(listing.get("published_at"))
    meta_line = f"📅 {source_str} • {date_str}"

    lines = [price_line, location_line, meta_line]

    if prefs:
        _, reasons = score(listing, prefs)
        positives = top_positive_reasons(reasons, n=3)
        if positives:
            lines.append("")
            lines.append("✅ <b>Почему подходит:</b>")
            for r in positives:
                lines.append(f"• {r}")

    return "\n".join(lines)


def build_card_keyboard(listing_id: str) -> InlineKeyboardMarkup:
    """Build the InlineKeyboardMarkup for a listing card."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❤️ В избранное", callback_data=f"fav:{listing_id}"),
                InlineKeyboardButton(text="👎 Не моё", callback_data=f"skip:{listing_id}"),
            ],
            [
                InlineKeyboardButton(text="🔔 Следить", callback_data=f"follow:{listing_id}"),
                InlineKeyboardButton(text="📞 Связаться", callback_data=f"contact:{listing_id}"),
            ],
        ]
    )


async def send_listing_card(
    bot: Any,
    chat_id: int,
    listing: dict[str, Any],
    prefs: dict[str, Any] | None = None,
) -> None:
    """
    Send a formatted listing card to the user.
    Sends a photo with caption if photo_url is available, otherwise plain text.
    Never raises — bad listing data is logged and skipped.
    """
    import logging
    from aiogram.enums import ParseMode

    logger = logging.getLogger(__name__)

    try:
        text = build_card_text(listing, prefs)
        keyboard = build_card_keyboard(listing["id"])
        photo_url = listing.get("photo_url")

        if photo_url:
            try:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_url,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
                return
            except Exception as exc:
                logger.debug("Failed to send photo for listing %s: %s", listing.get("id"), exc)

        # Fallback: text-only card
        title = listing.get("title") or ""
        url = listing.get("url") or ""
        link_line = f'\n🔗 <a href="{url}">Смотреть объявление</a>' if url else ""
        await bot.send_message(
            chat_id=chat_id,
            text=f"{text}{link_line}",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.exception("send_listing_card failed for user=%s listing=%s: %s", chat_id, listing.get("id"), exc)
