import re
import json
import logging

import httpx

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

    def _parse_json_listing(self, item: dict) -> dict | None:
        try:
            vehicle = item.get("vehicle", {})
            tracking = item.get("tracking", {})
            location = item.get("location", {})
            seller = item.get("seller", {})

            make = vehicle.get("make")
            model = vehicle.get("model")
            trim = vehicle.get("modelVersionInput")

            # Price from tracking (numeric string)
            price = None
            price_str = tracking.get("price")
            if price_str:
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    pass
            if price is None:
                price_formatted = item.get("price", {}).get("priceFormatted", "")
                price = self._parse_price_eur(price_formatted)

            # Mileage from tracking (numeric string)
            mileage = None
            mileage_str = tracking.get("mileage")
            if mileage_str:
                try:
                    mileage = int(mileage_str)
                except (ValueError, TypeError):
                    pass

            # Year from firstRegistration "MM-YYYY"
            year = None
            reg = tracking.get("firstRegistration", "")
            year_match = re.search(r"(\d{4})", reg)
            if year_match:
                year = int(year_match.group(1))

            # URL
            url = item.get("url", "")
            if url and not url.startswith("http"):
                url = f"{self.BASE_URL}{url}"

            # Location
            loc_parts = []
            if location.get("zip"):
                loc_parts.append(location["zip"])
            if location.get("city"):
                loc_parts.append(location["city"])
            loc_str = " ".join(loc_parts) if loc_parts else None

            # Image
            images = item.get("images", [])
            img_url = images[0] if images else None

            # Dealer
            dealer = seller.get("companyName")

            title = f"{make} {model}"
            if trim:
                title += f" {trim}"

            return {
                "year": year,
                "make": make,
                "model": model,
                "trim": trim,
                "list_price": price,
                "mileage": mileage,
                "days_on_market": None,
                "dealer_name": dealer,
                "location": loc_str,
                "description": title,
                "url": url,
                "image_url": img_url,
                "is_active": True,
                "currency": "EUR",
            }
        except Exception as e:
            logger.warning(f"[AutoScout24] Error parsing JSON listing: {e}")
            return None

    def _parse_price_eur(self, text: str) -> float | None:
        text = text.replace("\u20AC", "").replace("EUR", "").replace("€", "").strip()
        text = text.replace(".", "").replace(",", ".")
        nums = re.findall(r"[\d.]+", text)
        if nums:
            try:
                return float(nums[0])
            except ValueError:
                return None
        return None

    def _extract_listings_from_json(self, html: str) -> list[dict]:
        match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>', html)
        if not match:
            return []
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []

        # Navigate to find listings array
        def find_listings(obj, depth=0):
            if depth > 6:
                return None
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == "listings" and isinstance(v, list) and len(v) > 0:
                        return v
                    result = find_listings(v, depth + 1)
                    if result:
                        return result
            return None

        return find_listings(data) or []

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

                # Parse JSON from __NEXT_DATA__
                json_listings = self._extract_listings_from_json(html)

                if not json_listings:
                    logger.info(f"[AutoScout24] No results on page {page}")
                    break

                for item in json_listings:
                    parsed = self._parse_json_listing(item)
                    if parsed:
                        all_listings.append(parsed)

                logger.info(f"[AutoScout24] Page {page}: {len(json_listings)} listings (total: {len(all_listings)})")

                if on_progress:
                    await on_progress(page, max_pages, len(all_listings))

                if page < max_pages:
                    await self._delay()

        return all_listings
