import re
import logging
from datetime import datetime, timezone
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class BaTScraper(BaseScraper):
    PLATFORM_NAME = "Bring a Trailer"
    BASE_URL = "https://bringatrailer.com"

    def _build_search_url(
        self,
        make: str,
        model: str | None,
        year_from: int | None,
        year_to: int | None,
        keyword: str | None,
        page: int,
    ) -> str:
        # BaT search URL structure: /search/<query>/
        # Results are loaded via AJAX at /wp-json/bat/v1/search
        query_parts = []
        if make:
            query_parts.append(make.lower())
        if model:
            query_parts.append(model.lower())
        if keyword:
            query_parts.append(keyword.lower())

        query = "+".join(query_parts)

        params = {
            "search": query,
            "page": page,
        }
        if year_from:
            params["yearFrom"] = year_from
        if year_to:
            params["yearTo"] = year_to

        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.BASE_URL}/auctions/?{param_str}"

    def _parse_listing_card(self, card) -> dict | None:
        try:
            # BaT listing cards have specific CSS classes
            title_el = card.select_one("h3 a, .listing-card-title a, a.listing-card-link")
            if not title_el:
                title_el = card.select_one("a[href*='/listing/']")
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            url = title_el.get("href", "")
            if url and not url.startswith("http"):
                url = self.BASE_URL + url

            # Parse year, make, model from title
            year, make, model = self._parse_title(title)

            # Price - look for sold price or bid amount
            price = None
            price_el = card.select_one(".listing-card-result, .listing-card-price, .auction-value")
            if price_el:
                price_text = price_el.get_text(strip=True)
                price = self._parse_price(price_text)

            # Image
            img_url = None
            img_el = card.select_one("img")
            if img_el:
                img_url = img_el.get("src") or img_el.get("data-src")

            # Bid count
            bid_count = None
            bids_el = card.select_one(".listing-card-bids, .bid-count")
            if bids_el:
                bids_text = bids_el.get_text(strip=True)
                nums = re.findall(r"\d+", bids_text)
                if nums:
                    bid_count = int(nums[0])

            # Determine if sold
            is_sold = True
            result_text = card.get_text(strip=True).lower()
            if "not sold" in result_text or "bid to" in result_text:
                is_sold = False

            return {
                "year": year,
                "make": make,
                "model": model,
                "sold_price": price if is_sold else None,
                "starting_bid": price if not is_sold else None,
                "bid_count": bid_count,
                "url": url,
                "image_url": img_url,
                "is_sold": is_sold,
                "description": title,
            }
        except Exception as e:
            logger.warning(f"[BaT] Error parsing card: {e}")
            return None

    def _parse_title(self, title: str) -> tuple[int | None, str | None, str | None]:
        # Typical: "2019 BMW M3 Competition"
        match = re.match(r"(\d{4})\s+(\S+)\s+(.*)", title)
        if match:
            return int(match.group(1)), match.group(2), match.group(3).strip()
        return None, None, title

    def _parse_price(self, text: str) -> float | None:
        text = text.replace(",", "").replace("$", "").strip()
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

    async def _fetch_ajax_results(
        self,
        client: httpx.AsyncClient,
        make: str,
        model: str | None,
        year_from: int | None,
        year_to: int | None,
        keyword: str | None,
        page: int,
    ) -> list[dict]:
        # BaT uses AJAX endpoint for search results
        query_parts = [make]
        if model:
            query_parts.append(model)
        if keyword:
            query_parts.append(keyword)
        query = " ".join(query_parts)

        params = {
            "s": query,
            "page": str(page),
        }
        if year_from:
            params["year_from"] = str(year_from)
        if year_to:
            params["year_to"] = str(year_to)

        # Try the AJAX search results page
        url = f"{self.BASE_URL}/auctions/"
        resp = await client.get(url, params=params, headers=HEADERS, follow_redirects=True, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        listings = []

        # Look for listing items in various possible containers
        cards = soup.select(
            ".auction-item, .listing-card, .auctions-item, "
            "li.result, .search-result-item, article.listing"
        )

        # Fallback: look for any links to /listing/
        if not cards:
            # Try broader selectors
            cards = soup.select("[data-listing], .auctions-list > *, .results-list > *")

        if not cards:
            # Last resort: find all listing links and wrap them
            links = soup.find_all("a", href=re.compile(r"/listing/"))
            seen_urls = set()
            for link in links:
                href = link.get("href", "")
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                parent = link.find_parent(["li", "div", "article"])
                if parent:
                    cards.append(parent)

        for card in cards:
            parsed = self._parse_listing_card(card)
            if parsed:
                listings.append(parsed)

        return listings

    async def search(
        self,
        make: str,
        model: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        keyword: str | None = None,
        max_pages: int = 10,
        on_progress: callable = None,
    ) -> list[dict]:
        all_listings = []
        async with httpx.AsyncClient() as client:
            for page in range(1, max_pages + 1):
                try:
                    listings = await self._retry(
                        self._fetch_ajax_results,
                        client, make, model, year_from, year_to, keyword, page,
                    )
                except Exception as e:
                    logger.error(f"[BaT] Failed to fetch page {page}: {e}")
                    break

                if not listings:
                    logger.info(f"[BaT] No results on page {page}, stopping")
                    break

                all_listings.extend(listings)
                logger.info(f"[BaT] Page {page}: {len(listings)} listings (total: {len(all_listings)})")

                if on_progress:
                    await on_progress(page, max_pages, len(all_listings))

                if page < max_pages:
                    await self._delay()

        return all_listings
