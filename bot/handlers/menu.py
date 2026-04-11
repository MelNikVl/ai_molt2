"""
Reply keyboard menu handler.

Provides a persistent bottom menu for the bot with quick-access buttons.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from bot.db import queries

logger = logging.getLogger(__name__)
router = Router()

MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🏠 Главная"), KeyboardButton(text="📋 Мои фильтры")],
        [KeyboardButton(text="⏹ Пауза уведомлений"), KeyboardButton(text="▶️ Возобновить уведомления")],
        [KeyboardButton(text="🔄 Настроить заново"), KeyboardButton(text="🗺 Последние на карте")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


# ── 🏠 Главная ────────────────────────────────────────────────────────────────

@router.message(F.text == "🏠 Главная")
async def menu_home(message: Message, db_path: str) -> None:
    if not message.from_user:
        return
    user = await queries.get_user(db_path, message.from_user.id)
    if not user or not user.get("deal_type"):
        await message.answer(
            "Добро пожаловать! Настройки не заданы. Используйте /start для настройки.",
            reply_markup=MAIN_MENU,
        )
        return

    deal = "Аренда" if user.get("deal_type") == "rent" else "Покупка"
    city = user.get("city") or "не указан"
    bmax = user.get("budget_max")
    budget = f"до {bmax:,} ₸".replace(",", "\u2009") if bmax else "без ограничений"
    paused = bool(user.get("is_paused"))
    status = "⏹ Уведомления на паузе" if paused else "▶️ Уведомления активны"

    await message.answer(
        f"🏠 <b>Главная</b>\n\n"
        f"<b>Тип:</b> {deal}\n"
        f"<b>Город:</b> {city}\n"
        f"<b>Бюджет:</b> {budget}\n"
        f"<b>Статус:</b> {status}\n\n"
        f"Используйте меню ниже для управления ботом.",
        parse_mode="HTML",
        reply_markup=MAIN_MENU,
    )


# ── 📋 Мои фильтры ────────────────────────────────────────────────────────────

@router.message(F.text == "📋 Мои фильтры")
async def menu_my_filters(message: Message, db_path: str) -> None:
    # Delegate to cmd_card logic
    from bot.handlers.start import _show_card
    await _show_card(message, db_path)


# ── ⏹ Пауза уведомлений ──────────────────────────────────────────────────────

@router.message(F.text == "⏹ Пауза уведомлений")
async def menu_pause(message: Message, db_path: str) -> None:
    if not message.from_user:
        return
    await queries.set_user_paused(db_path, message.from_user.id, paused=True)
    await message.answer(
        "⏹ <b>Уведомления приостановлены.</b>\n\n"
        "Бот не будет присылать новые объявления. "
        "Нажмите «▶️ Возобновить уведомления», чтобы снова получать их.",
        parse_mode="HTML",
        reply_markup=MAIN_MENU,
    )


# ── ▶️ Возобновить уведомления ────────────────────────────────────────────────

@router.message(F.text == "▶️ Возобновить уведомления")
async def menu_resume(message: Message, db_path: str) -> None:
    if not message.from_user:
        return
    await queries.set_user_paused(db_path, message.from_user.id, paused=False)
    await message.answer(
        "▶️ <b>Уведомления возобновлены!</b>\n\n"
        "Бот снова будет присылать подходящие объявления.",
        parse_mode="HTML",
        reply_markup=MAIN_MENU,
    )


# ── 🔄 Настроить заново ───────────────────────────────────────────────────────

@router.message(F.text == "🔄 Настроить заново")
async def menu_restart(message: Message, state: FSMContext, db_path: str) -> None:
    from bot.handlers.start import _start_onboarding
    await state.clear()
    await _start_onboarding(message, state, db_path)


# ── 🗺 Последние на карте ─────────────────────────────────────────────────────

@router.message(F.text == "🗺 Последние на карте")
async def menu_last_on_map(message: Message, db_path: str) -> None:
    if not message.from_user:
        return
    listings = await queries.get_last_sent_listings(db_path, message.from_user.id, n=5)
    if not listings:
        await message.answer(
            "У вас пока нет отправленных объявлений.",
            reply_markup=MAIN_MENU,
        )
        return

    lines = ["🗺 <b>Последние объявления:</b>\n"]
    for item in listings:
        price = item.get("price") or 0
        price_str = f"{price:,}".replace(",", "\u2009")
        address = item.get("address") or "адрес не указан"
        url = item.get("url") or ""
        title = item.get("title") or "Объявление"
        lines.append(f"• <b>{price_str} ₸</b> — {address}\n  <a href='{url}'>{title}</a>")

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=MAIN_MENU,
    )
