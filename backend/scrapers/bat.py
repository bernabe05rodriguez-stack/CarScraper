import re
import logging
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from backend.scrapers.base import BaseScraper, PLAYWRIGHT_ARGS

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Patterns for detecting non-car items (parts, accessories, memorabilia)
_NON_CAR_KEYWORDS = re.compile(
    r'\b(seats?|wheel set|engine|motor|hood|bumper|exhaust|steering wheel|'
    r'literature|brochure|luggage|tool kit|manuals?|memorabilia|sign|poster|'
    r'helmet|jacket|watch|model car|diecast|pedal car|go[- ]kart|trailer|'
    r'hardtop|soft top|roof rack)\b',
    re.IGNORECASE,
)

# Month name mapping for parsing dates like "December 15, 2023"
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


class BaTScraper(BaseScraper):
    PLATFORM_NAME = "Bring a Trailer"
    BASE_URL = "https://bringatrailer.com"

    def _build_search_url(self, make: str, model: str | None) -> str:
        make_slug = make.lower().replace(" ", "-")
        if model:
            model_slug = model.lower().replace(" ", "-")
            return f"{self.BASE_URL}/{make_slug}/{model_slug}/"
        return f"{self.BASE_URL}/{make_slug}/"

    def _parse_title(self, title: str) -> tuple[int | None, str | None, str | None]:
        """Extract year, make, model from BaT title.

        Handles formats like:
          - "2011 BMW M3 Sedan"
          - "13k-Mile 2011 BMW M3 Sedan Competition Package"
          - "No Reserve: 1995 BMW M3 Lightweight"
        """
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', title)
        if not year_match:
            return None, None, title

        year = int(year_match.group(1))
        after_year = title[year_match.end():].strip()
        parts = after_year.split(None, 1)
        if len(parts) >= 2:
            return year, parts[0], parts[1].strip()
        elif len(parts) == 1:
            return year, parts[0], None
        return year, None, None

    def _parse_price(self, text: str) -> float | None:
        text = text.replace(",", "").replace("$", "").replace("USD", "").strip()
        nums = re.findall(r"[\d.]+", text)
        if nums:
            try:
                return float(nums[0])
            except ValueError:
                return None
        return None

    def _parse_date(self, text: str) -> datetime | None:
        """Parse date from text like 'Sold for $25,000 on December 15, 2023'."""
        date_match = re.search(
            r'(\w+)\s+(\d{1,2}),?\s+(\d{4})', text
        )
        if not date_match:
            return None
        month_str = date_match.group(1).lower()
        day = int(date_match.group(2))
        year = int(date_match.group(3))
        month = _MONTHS.get(month_str)
        if not month:
            return None
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None

    def _is_non_car_item(self, parsed: dict) -> bool:
        """Detect parts, accessories, and memorabilia listings."""
        title = parsed.get("description") or ""
        # Pattern: "X for BMW M3" = likely a part
        if re.search(r'\bfor\s+\w+\s+\w+\b', title, re.IGNORECASE):
            if _NON_CAR_KEYWORDS.search(title):
                return True
        # No year + non-car keyword = definitely not a car
        if parsed.get("year") is None and _NON_CAR_KEYWORDS.search(title):
            return True
        return False

    def _matches_filters(
        self, parsed: dict,
        year_from: int | None, year_to: int | None,
        keyword: str | None,
    ) -> bool:
        """Return True if listing passes all filters."""
        # Exclude listings with unknown year when year range is specified
        if (year_from or year_to) and parsed.get("year") is None:
            return False
        if year_from and parsed.get("year") and parsed["year"] < year_from:
            return False
        if year_to and parsed.get("year") and parsed["year"] > year_to:
            return False
        # Filter non-car items
        if self._is_non_car_item(parsed):
            return False
        # Keyword filter: check title AND URL slug
        if keyword:
            kw = keyword.lower()
            desc = (parsed.get("description") or "").lower()
            url_slug = (parsed.get("url") or "").lower()
            if kw not in desc and kw not in url_slug:
                return False
        return True

    def _parse_listing_card(self, card) -> dict | None:
        try:
            title_el = card.select_one("h3 a")
            if not title_el:
                title_el = card.select_one(".content-main h3 a")
            if not title_el:
                title_el = card.select_one("a.image-overlay")
            if not title_el:
                return None

            title = title_el.get_text(strip=True) or title_el.get("title", "")
            url = title_el.get("href", "")
            if not url:
                overlay = card.select_one("a.image-overlay")
                if overlay:
                    url = overlay.get("href", "")
            if url and not url.startswith("http"):
                url = self.BASE_URL + url

            year, make, model = self._parse_title(title)

            price = None
            price_el = card.select_one(".bid-formatted.bold, .bid-formatted")
            if price_el:
                price = self._parse_price(price_el.get_text(strip=True))

            bid_label = ""
            label_el = card.select_one(".bid-label")
            if label_el:
                bid_label = label_el.get_text(strip=True).lower()

            sold_text = ""
            result_el = card.select_one(".item-results")
            if result_el:
                sold_text = result_el.get_text(strip=True).lower()

            is_sold = False
            if "sold" in sold_text and "not sold" not in sold_text:
                is_sold = True
            elif "sold" in bid_label:
                is_sold = True

            # Parse auction end date from result text
            auction_end_date = None
            if result_el:
                auction_end_date = self._parse_date(result_el.get_text(strip=True))

            has_no_reserve = card.select_one(".item-tag-noreserve") is not None

            img_url = None
            img_el = card.select_one(".thumbnail img")
            if img_el:
                img_url = img_el.get("src") or img_el.get("data-src")

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
                "auction_end_date": auction_end_date,
            }
        except Exception as e:
            logger.warning(f"[BaT] Error parsing card: {e}")
            return None

    def _parse_cards_from_soup(self, soup) -> list:
        """Find listing cards using multiple selector strategies."""
        cards = soup.select(".listing-card.listing-card-separate")
        if not cards:
            cards = soup.select("div[data-listing_id]")
        if not cards:
            cards = []
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
        return cards

    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> str:
        resp = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=30)
        resp.raise_for_status()
        return resp.text

    async def _search_static(
        self,
        make: str,
        model: str | None,
        year_from: int | None,
        year_to: int | None,
        keyword: str | None,
        on_progress: callable,
    ) -> list[dict]:
        """Fallback: httpx-based static HTML scraping (no pagination)."""
        all_listings = []
        async with httpx.AsyncClient() as client:
            search_url = self._build_search_url(make, model)
            logger.info(f"[BaT] Static fallback: {search_url}")
            try:
                html = await self._retry(self._fetch_page, client, search_url)
            except Exception as e:
                logger.error(f"[BaT] Failed to fetch page: {e}")
                return []

            soup = BeautifulSoup(html, "lxml")
            cards = self._parse_cards_from_soup(soup)
            logger.info(f"[BaT] Static: found {len(cards)} cards")

            for card in cards:
                parsed = self._parse_listing_card(card)
                if parsed and self._matches_filters(parsed, year_from, year_to, keyword):
                    all_listings.append(parsed)

            if on_progress:
                await on_progress(1, 1, len(all_listings))

        return all_listings

    async def search(
        self,
        make: str,
        model: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        keyword: str | None = None,
        time_filter: str | None = None,
        max_pages: int = 10,
        on_progress: callable = None,
    ) -> list[dict]:
        all_listings = []

        try:
            from playwright.async_api import async_playwright
            from playwright_stealth import stealth_async
        except ImportError:
            logger.warning("[BaT] Playwright not available, using static fallback")
            all_listings = await self._search_static(
                make, model, year_from, year_to, keyword, on_progress,
            )
            return self._apply_time_filter(all_listings, time_filter)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=PLAYWRIGHT_ARGS,
            )
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=HEADERS["User-Agent"],
            )
            page = await context.new_page()
            await stealth_async(page)

            search_url = self._build_search_url(make, model)
            logger.info(f"[BaT] Navigating to {search_url}")

            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.warning(f"[BaT] Navigation timeout (continuing): {e}")

            await page.wait_for_timeout(3000)

            # Try to load more results
            for page_num in range(1, max_pages + 1):
                try:
                    load_more = page.locator(
                        "button:has-text('Load More'), "
                        "a:has-text('Load More'), "
                        "button:has-text('Show More'), "
                        "[class*='load-more']"
                    )
                    if await load_more.count() > 0:
                        await load_more.first.click()
                        await page.wait_for_timeout(2000)
                        if on_progress:
                            await on_progress(page_num, max_pages, 0)
                    else:
                        # Try scrolling to trigger lazy loading
                        prev_height = await page.evaluate("document.body.scrollHeight")
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await page.wait_for_timeout(1500)
                        new_height = await page.evaluate("document.body.scrollHeight")
                        if new_height == prev_height:
                            break
                except Exception:
                    break

            # Parse all cards from fully rendered page
            html = await page.content()
            soup = BeautifulSoup(html, "lxml")
            cards = self._parse_cards_from_soup(soup)
            logger.info(f"[BaT] Found {len(cards)} listing cards (after pagination)")

            for card in cards:
                parsed = self._parse_listing_card(card)
                if parsed and self._matches_filters(parsed, year_from, year_to, keyword):
                    all_listings.append(parsed)

            logger.info(f"[BaT] Total listings after filtering: {len(all_listings)}")
            await browser.close()

        all_listings = self._apply_time_filter(all_listings, time_filter)

        if on_progress:
            await on_progress(max_pages, max_pages, len(all_listings))

        return all_listings

    def _apply_time_filter(self, listings: list[dict], time_filter: str | None) -> list[dict]:
        """Filter listings by auction date."""
        time_cutoff = self._compute_time_cutoff(time_filter)
        if not time_cutoff or not listings:
            return listings
        before = len(listings)
        filtered = []
        for l in listings:
            end_date = l.get("auction_end_date")
            if end_date is None:
                # Keep listings without date (conservative)
                filtered.append(l)
                continue
            if isinstance(end_date, datetime):
                if end_date.tzinfo is None:
                    end_date = end_date.replace(tzinfo=timezone.utc)
                if end_date >= time_cutoff:
                    filtered.append(l)
        logger.info(f"[BaT] Time filter ({time_filter}): {before} -> {len(filtered)}")
        return filtered
