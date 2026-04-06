from __future__ import annotations

import asyncio
import logging
import random
import re
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup, Tag

from config import Settings, load_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://krisha.kz"
RENT_LISTINGS_PATH = "/arenda/kvartiry/{city}/"
BUY_LISTINGS_PATH = "/prodazha/kvartiry/{city}/"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


@dataclass(slots=True)
class Listing:
    id: str
    title: str
    price: int
    address: str
    district: str
    rooms: int | None
    photo_url: str | None
    url: str
    published_at: str



def _extract_price(value: str) -> int | None:
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None



def _extract_rooms(title: str) -> int | None:
    match = re.search(r"(\d+)\s*-?\s*ком", title.lower())
    if match:
        return int(match.group(1))
    return None



def _extract_listing_id(card: Tag, listing_url: str | None) -> str | None:
    for attr in ("data-id", "data-advert-id", "id"):
        value = card.get(attr)
        if value:
            return str(value)

    if listing_url:
        match = re.search(r"/(\d{5,})", listing_url)
        if match:
            return match.group(1)

    return None



def _full_url(href: str | None) -> str | None:
    if not href:
        return None
    if href.startswith("http"):
        return href
    return f"{BASE_URL}{href}"



def _parse_card(card: Tag) -> Listing | None:
    link_tag = card.select_one("a.a-card__title") or card.select_one("a[href*='/a/show/']")
    listing_url = _full_url(link_tag.get("href") if link_tag else None)
    listing_id = _extract_listing_id(card, listing_url)

    title = ""
    if link_tag:
        title = " ".join(link_tag.get_text(" ", strip=True).split())

    price_tag = card.select_one(".a-card__price") or card.select_one(".price")
    price = _extract_price(price_tag.get_text(" ", strip=True) if price_tag else "")

    address_tag = card.select_one(".a-card__subtitle") or card.select_one(".a-card__text-preview")
    address_text = " ".join(address_tag.get_text(" ", strip=True).split()) if address_tag else ""

    district = ""
    if address_text:
        district = address_text.split(",", 1)[0].strip()

    time_tag = card.select_one(".a-card__text-date") or card.select_one(".a-card__header-left")
    published_at = " ".join(time_tag.get_text(" ", strip=True).split()) if time_tag else ""

    image_tag = card.select_one("img")
    photo_url = None
    if image_tag:
        photo_url = image_tag.get("src") or image_tag.get("data-src")
        photo_url = _full_url(photo_url) if photo_url else None

    rooms = _extract_rooms(title)

    if not (listing_id and listing_url and title and price is not None):
        return None

    return Listing(
        id=listing_id,
        title=title,
        price=price,
        address=address_text,
        district=district,
        rooms=rooms,
        photo_url=photo_url,
        url=listing_url,
        published_at=published_at,
    )



def _build_search_url(
    settings: Settings,
    deal_type: str,
    price_min: int | None,
    price_max: int | None,
    area_min: int | None,
    area_max: int | None,
) -> str:
    normalized = deal_type.lower().strip()
    if normalized in {"buy", "sale", "sell", "prodazha"}:
        path = BUY_LISTINGS_PATH
        default_price_min = 10_000_000
    else:
        path = RENT_LISTINGS_PATH
        default_price_min = None

    base = f"{BASE_URL}{path.format(city=settings.city)}"

    params: dict[str, int] = {"das[_sys.hasphoto]": 1}
    if price_min is not None:
        params["das[price][from]"] = price_min
    elif default_price_min is not None:
        params["das[price][from]"] = default_price_min

    if price_max is not None:
        params["das[price][to]"] = price_max
    else:
        params["das[price][to]"] = settings.max_price

    if area_min is not None:
        params["das[live.square][from]"] = area_min
    if area_max is not None:
        params["das[live.square][to]"] = area_max

    if settings.min_rooms == settings.max_rooms:
        params["das[live.rooms]"] = settings.max_rooms

    return f"{base}?{urlencode(params)}"


async def parse_krisha(
    settings: Settings,
    limit: int | None = None,
    deal_type: str | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    area_min: int | None = None,
    area_max: int | None = None,
) -> list[Listing]:
    await asyncio.sleep(random.uniform(1.0, 3.0))
    resolved_deal_type = deal_type or settings.deal_type
    url = _build_search_url(settings, resolved_deal_type, price_min, price_max, area_min, area_max)

    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=30.0, follow_redirects=True) as client:
        for attempt in (1, 2):
            try:
                response = await client.get(url)
                if response.status_code in (403, 429):
                    logger.warning("Krisha blocked this round with status %s", response.status_code)
                    return []
                response.raise_for_status()
                break
            except httpx.HTTPStatusError:
                if attempt == 2:
                    logger.exception("HTTP error while loading krisha page")
                    return []
                await asyncio.sleep(5)
            except httpx.HTTPError:
                if attempt == 2:
                    logger.exception("Network error while loading krisha page")
                    return []
                await asyncio.sleep(5)

    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.select("div.a-card")
    if not cards:
        cards = soup.select("section.a-card")

    listings: list[Listing] = []
    for card in cards:
        parsed = _parse_card(card)
        if not parsed:
            continue

        if parsed.rooms is not None and not (settings.min_rooms <= parsed.rooms <= settings.max_rooms):
            continue
        if parsed.price > (price_max if price_max is not None else settings.max_price):
            continue
        if price_min is not None and parsed.price < price_min:
            continue

        listings.append(parsed)
        if limit and len(listings) >= limit:
            break

    return listings


async def _demo() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    listings = await parse_krisha(settings, limit=10, deal_type=settings.deal_type)

    if not listings:
        print("Объявления не найдены или сайт временно недоступен.")
        return

    for index, listing in enumerate(listings, start=1):
        print(f"{index}. [{listing.id}] {listing.title}")
        print(f"   Цена: {listing.price} ₸")
        print(f"   Адрес: {listing.address}")
        print(f"   Время: {listing.published_at}")
        print(f"   URL: {listing.url}")
        print()


if __name__ == "__main__":
    asyncio.run(_demo())
