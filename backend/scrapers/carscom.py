import re
import logging

import httpx
from bs4 import BeautifulSoup

from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class CarsComScraper(BaseScraper):
    PLATFORM_NAME = "Cars.com"
    BASE_URL = "https://www.cars.com"

    def _build_search_url(
        self,
        make: str,
        model: str | None,
        year_from: int | None,
        year_to: int | None,
        keyword: str | None,
        page: int,
    ) -> str:
        params = {
            "stock_type": "used",
            "maximum_distance": "all",
            "sort": "best_match_desc",
            "page_size": "20",
            "page": str(page),
        }
        if make:
            params["makes[]"] = make.lower().replace(" ", "_")
        if model:
            make_slug = make.lower().replace(" ", "_")
            model_slug = model.lower().replace(" ", "_")
            params["models[]"] = f"{make_slug}-{model_slug}"
        if year_from:
            params["year_min"] = str(year_from)
        if year_to:
            params["year_max"] = str(year_to)
        if keyword:
            params["keyword"] = keyword

        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.BASE_URL}/shopping/results/?{param_str}"

    def _parse_listing_card(self, card) -> dict | None:
        try:
            # Title
            title_el = card.select_one("h2 a, .vehicle-card-link, a.vehicle-card-visited-tracking-link")
            if not title_el:
                title_el = card.select_one("a[href*='/vehicledetail/']")
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            year, make, model, trim = self._parse_title(title)

            # URL
            url = title_el.get("href", "")
            if url and not url.startswith("http"):
                url = f"{self.BASE_URL}{url}"

            # Price
            price = None
            price_el = card.select_one(".primary-price, [class*='primary-price'], .listing-row__price")
            if price_el:
                price = self._parse_price(price_el.get_text(strip=True))

            # Mileage
            mileage = None
            mileage_el = card.select_one("[class*='mileage'], .mileage")
            if mileage_el:
                text = mileage_el.get_text(strip=True)
                nums = re.findall(r"[\d,]+", text)
                if nums:
                    mileage = int(nums[0].replace(",", ""))

            # Dealer
            dealer = None
            dealer_el = card.select_one("[class*='dealer-name'], .dealer-name")
            if dealer_el:
                dealer = dealer_el.get_text(strip=True)

            # Location
            location = None
            loc_el = card.select_one("[class*='miles-from'], .miles-from")
            if loc_el:
                location = loc_el.get_text(strip=True)

            # Image
            img_url = None
            img_el = card.select_one("img")
            if img_el:
                img_url = img_el.get("src") or img_el.get("data-src")

            return {
                "year": year,
                "make": make,
                "model": model,
                "trim": trim,
                "list_price": price,
                "mileage": mileage,
                "days_on_market": None,
                "dealer_name": dealer,
                "location": location,
                "description": title,
                "url": url,
                "image_url": img_url,
                "is_active": True,
                "currency": "USD",
            }
        except Exception as e:
            logger.warning(f"[Cars.com] Error parsing card: {e}")
            return None

    def _parse_title(self, title: str) -> tuple:
        match = re.match(r"(\d{4})\s+(\S+)\s+(\S+)\s*(.*)", title)
        if match:
            return int(match.group(1)), match.group(2), match.group(3), match.group(4).strip() or None
        match = re.match(r"(\d{4})\s+(\S+)\s+(.*)", title)
        if match:
            return int(match.group(1)), match.group(2), match.group(3).strip(), None
        return None, None, title, None

    def _parse_price(self, text: str) -> float | None:
        text = text.replace(",", "").replace("$", "").strip()
        nums = re.findall(r"[\d.]+", text)
        if nums:
            try:
                return float(nums[0])
            except ValueError:
                return None
        return None

    async def search(
        self,
        make: str,
        model: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        keyword: str | None = None,
        max_pages: int = 5,
        on_progress: callable = None,
    ) -> list[dict]:
        all_listings = []

        async with httpx.AsyncClient() as client:
            for page in range(1, max_pages + 1):
                url = self._build_search_url(make, model, year_from, year_to, keyword, page)
                logger.info(f"[Cars.com] Page {page}: {url}")

                try:
                    resp = await self._retry(
                        self._fetch_page, client, url,
                    )
                except Exception as e:
                    logger.error(f"[Cars.com] Failed to fetch page {page}: {e}")
                    break

                soup = BeautifulSoup(resp, "lxml")

                # Find listing cards
                cards = soup.select(
                    ".vehicle-card, [class*='vehicle-card'], "
                    ".listing-row, [data-qa='results-card']"
                )

                if not cards:
                    logger.info(f"[Cars.com] No results on page {page}")
                    break

                for card in cards:
                    parsed = self._parse_listing_card(card)
                    if parsed:
                        all_listings.append(parsed)

                logger.info(f"[Cars.com] Page {page}: {len(cards)} cards (total: {len(all_listings)})")

                if on_progress:
                    await on_progress(page, max_pages, len(all_listings))

                if page < max_pages:
                    await self._delay()

        return all_listings

    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> str:
        resp = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=30)
        resp.raise_for_status()
        return resp.text
