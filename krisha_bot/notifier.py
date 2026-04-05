from __future__ import annotations

import logging

from telegram import Bot

from parser import Listing

logger = logging.getLogger(__name__)



def _format_price(price: int) -> str:
    return f"{price:,}".replace(",", " ")


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id

    async def send_new(self, listing: Listing) -> None:
        title_line = f"🏠 *{listing.title} • {_format_price(listing.price)} ₸/мес*"
        address = listing.address or "Адрес не указан"
        time_line = listing.published_at or "не указано"
        text = (
            f"{title_line}\n"
            f"📍 {address}\n"
            f"⏱ Опубликовано {time_line}\n"
            f"🔗 [Смотреть объявление]({listing.url})"
        )

        try:
            if listing.photo_url:
                await self.bot.send_photo(
                    chat_id=self.chat_id,
                    photo=listing.photo_url,
                    caption=text,
                    parse_mode="Markdown",
                )
            else:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode="Markdown",
                    disable_web_page_preview=False,
                )
        except Exception:
            logger.exception("Failed to send new listing notification id=%s", listing.id)

    async def send_price_drop(self, listing: Listing, old_price: int) -> None:
        text = (
            "📉 *Снижение цены!*\n"
            f"Было: ~{_format_price(old_price)} ₸~ → Стало: *{_format_price(listing.price)} ₸*\n"
            f"📍 {listing.address or 'Адрес не указан'}\n"
            f"🔗 [Смотреть]({listing.url})"
        )

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="Markdown",
                disable_web_page_preview=False,
            )
        except Exception:
            logger.exception("Failed to send price drop notification id=%s", listing.id)
