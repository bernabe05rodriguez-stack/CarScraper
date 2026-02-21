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


class BaTScraper(BaseScraper):
    PLATFORM_NAME = "Bring a Trailer"
    BASE_URL = "https://bringatrailer.com"

    def _build_search_url(self, make: str, model: str | None) -> str:
        # BaT uses model pages like /bmw/m3/ for browsing listings
        make_slug = make.lower().replace(" ", "-")
        if model:
            model_slug = model.lower().replace(" ", "-")
            return f"{self.BASE_URL}/{make_slug}/{model_slug}/"
        return f"{self.BASE_URL}/{make_slug}/"

    def _parse_listing_card(self, card) -> dict | None:
        try:
            # Title from h3 > a
            title_el = card.select_one("h3 a")
            if not title_el:
                title_el = card.select_one(".content-main h3 a")
            if not title_el:
                # Try image overlay link as fallback
                title_el = card.select_one("a.image-overlay")
            if not title_el:
                return None

            title = title_el.get_text(strip=True) or title_el.get("title", "")
            url = title_el.get("href", "")
            if not url:
                # Get URL from image overlay
                overlay = card.select_one("a.image-overlay")
                if overlay:
                    url = overlay.get("href", "")
            if url and not url.startswith("http"):
                url = self.BASE_URL + url

            year, make, model = self._parse_title(title)

            # Price/bid from .bid-formatted.bold (e.g., "USD $10,000")
            price = None
            price_el = card.select_one(".bid-formatted.bold, .bid-formatted")
            if price_el:
                price = self._parse_price(price_el.get_text(strip=True))

            # Bid label (shows "Bid:" for live, "Sold:" for completed)
            bid_label = ""
            label_el = card.select_one(".bid-label")
            if label_el:
                bid_label = label_el.get_text(strip=True).lower()

            # Sold text from item-results div
            sold_text = ""
            result_el = card.select_one(".item-results")
            if result_el:
                sold_text = result_el.get_text(strip=True).lower()

            # Determine sold status
            is_sold = False
            if "sold" in sold_text and "not sold" not in sold_text:
                is_sold = True
            elif "sold" in bid_label:
                is_sold = True

            # No reserve tag
            has_no_reserve = card.select_one(".item-tag-noreserve") is not None

            # Image
            img_url = None
            img_el = card.select_one(".thumbnail img")
            if img_el:
                img_url = img_el.get("src") or img_el.get("data-src")

            # Bid count (not available in card, only on listing page)
            bid_count = None

            description = title
            if has_no_reserve:
                description += " [No Reserve]"

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
                "description": description,
            }
        except Exception as e:
            logger.warning(f"[BaT] Error parsing card: {e}")
            return None

    def _parse_title(self, title: str) -> tuple[int | None, str | None, str | None]:
        match = re.match(r"(\d{4})\s+(\S+)\s+(.*)", title)
        if match:
            return int(match.group(1)), match.group(2), match.group(3).strip()
        return None, None, title

    def _parse_price(self, text: str) -> float | None:
        # Handle "USD $10,000" or "$10,000" or "10,000"
        text = text.replace(",", "").replace("$", "").replace("USD", "").strip()
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
        max_pages: int = 10,
        on_progress: callable = None,
    ) -> list[dict]:
        all_listings = []

        async with httpx.AsyncClient() as client:
            # Fetch the model page which has static listing cards
            search_url = self._build_search_url(make, model)
            logger.info(f"[BaT] Fetching: {search_url}")

            try:
                html = await self._retry(self._fetch_page, client, search_url)
            except Exception as e:
                logger.error(f"[BaT] Failed to fetch page: {e}")
                return []

            soup = BeautifulSoup(html, "lxml")

            # Parse static listing cards (listing-card-separate = server-rendered)
            cards = soup.select(".listing-card.listing-card-separate")

            if not cards:
                # Fallback: any div with data-listing_id
                cards = soup.select("div[data-listing_id]")

            if not cards:
                # Last resort: find all links to /listing/ and get parents
                links = soup.find_all("a", href=re.compile(r"/listing/"))
                seen_urls = set()
                for link in links:
                    href = link.get("href", "")
                    if href in seen_urls:
                        continue
                    seen_urls.add(href)
                    parent = link.find_parent(["div", "li", "article"])
                    if parent and parent.get("class"):
                        cards.append(parent)

            logger.info(f"[BaT] Found {len(cards)} listing cards")

            for card in cards:
                parsed = self._parse_listing_card(card)
                if parsed:
                    # Filter by year range
                    if year_from and parsed.get("year") and parsed["year"] < year_from:
                        continue
                    if year_to and parsed.get("year") and parsed["year"] > year_to:
                        continue
                    # Filter by keyword
                    if keyword:
                        desc = (parsed.get("description") or "").lower()
                        if keyword.lower() not in desc:
                            continue
                    all_listings.append(parsed)

            logger.info(f"[BaT] Total listings: {len(all_listings)}")

            if on_progress:
                await on_progress(1, 1, len(all_listings))

        return all_listings
