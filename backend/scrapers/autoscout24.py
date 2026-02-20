import re
import logging

import httpx
from bs4 import BeautifulSoup

from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
}


class AutoScout24Scraper(BaseScraper):
    PLATFORM_NAME = "AutoScout24"
    BASE_URL = "https://www.autoscout24.de"

    def _build_search_url(
        self,
        make: str,
        model: str | None,
        year_from: int | None,
        year_to: int | None,
        keyword: str | None,
        page: int,
    ) -> str:
        make_slug = make.lower().replace(" ", "-")
        path = f"/lst/{make_slug}"
        if model:
            model_slug = model.lower().replace(" ", "-")
            path += f"/{model_slug}"

        params = {
            "sort": "standard",
            "desc": "0",
            "ustate": "N,U",
            "size": "20",
            "page": str(page),
            "cy": "D",
            "atype": "C",
        }
        if year_from:
            params["fregfrom"] = str(year_from)
        if year_to:
            params["fregto"] = str(year_to)
        if keyword:
            params["search_query"] = keyword

        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.BASE_URL}{path}?{param_str}"

    def _parse_listing_card(self, card) -> dict | None:
        try:
            # Title
            title_el = card.select_one("h2 a, a[data-item-name='detail-page-link'], .ListItem_title__ndA4s a")
            if not title_el:
                title_el = card.select_one("a[href*='/angebote/']")
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            year, make, model, trim = self._parse_title(title)

            # URL
            url = title_el.get("href", "")
            if url and not url.startswith("http"):
                url = f"{self.BASE_URL}{url}"

            # Price (EUR)
            price = None
            price_el = card.select_one("[data-testid='price-label'], .ListItem_price__APlgs, [class*='Price']")
            if price_el:
                price = self._parse_price_eur(price_el.get_text(strip=True))

            # Mileage
            mileage = None
            details = card.select("[data-testid='VehicleDetailTable'] span, .VehicleDetailTable_item__4n35N")
            for d in details:
                text = d.get_text(strip=True).lower()
                if "km" in text:
                    nums = re.findall(r"[\d.]+", text.replace(".", ""))
                    if nums:
                        mileage = int(nums[0])
                if not year and re.match(r"\d{2}/\d{4}", text):
                    year_match = re.search(r"/(\d{4})", text)
                    if year_match:
                        year = int(year_match.group(1))

            # Dealer
            dealer = None
            dealer_el = card.select_one("[data-testid='seller-info'], .SellerInfo_name__uhRbP")
            if dealer_el:
                dealer = dealer_el.get_text(strip=True)[:100]

            # Location
            location = None
            loc_el = card.select_one("[data-testid='seller-address'], .SellerInfo_address__leRMu")
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
                "currency": "EUR",
            }
        except Exception as e:
            logger.warning(f"[AutoScout24] Error parsing card: {e}")
            return None

    def _parse_title(self, title: str) -> tuple:
        match = re.match(r"(\d{4})\s+(\S+)\s+(\S+)\s*(.*)", title)
        if match:
            return int(match.group(1)), match.group(2), match.group(3), match.group(4).strip() or None
        match = re.match(r"(\S+)\s+(\S+)\s*(.*)", title)
        if match:
            return None, match.group(1), match.group(2), match.group(3).strip() or None
        return None, None, title, None

    def _parse_price_eur(self, text: str) -> float | None:
        text = text.replace("\u20AC", "").replace("EUR", "").strip()
        text = text.replace(".", "").replace(",", ".")
        nums = re.findall(r"[\d.]+", text)
        if nums:
            try:
                return float(nums[0])
            except ValueError:
                return None
        return None

    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> str:
        resp = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=30)
        resp.raise_for_status()
        return resp.text

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
                logger.info(f"[AutoScout24] Page {page}: {url}")

                try:
                    html = await self._retry(self._fetch_page, client, url)
                except Exception as e:
                    logger.error(f"[AutoScout24] Failed to fetch page {page}: {e}")
                    break

                soup = BeautifulSoup(html, "lxml")
                cards = soup.select(
                    "[data-testid='listing'], article.cldt-summary-full-item, "
                    ".ListItem_wrapper__TxHWu, [class*='ListItem']"
                )

                if not cards:
                    links = soup.find_all("a", href=re.compile(r"/angebote/"))
                    cards = [link.find_parent(["div", "li", "article"]) or link for link in links]

                if not cards:
                    logger.info(f"[AutoScout24] No results on page {page}")
                    break

                for card in cards:
                    parsed = self._parse_listing_card(card)
                    if parsed:
                        all_listings.append(parsed)

                logger.info(f"[AutoScout24] Page {page}: {len(cards)} cards (total: {len(all_listings)})")

                if on_progress:
                    await on_progress(page, max_pages, len(all_listings))

                if page < max_pages:
                    await self._delay()

        return all_listings
