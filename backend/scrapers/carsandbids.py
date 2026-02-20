import re
import json
import logging
from datetime import datetime, timezone

from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class CarsAndBidsScraper(BaseScraper):
    PLATFORM_NAME = "Cars & Bids"
    BASE_URL = "https://carsandbids.com"

    def _parse_title(self, title: str) -> tuple[int | None, str | None, str | None]:
        match = re.match(r"(\d{4})\s+(\S+)\s+(.*)", title)
        if match:
            return int(match.group(1)), match.group(2), match.group(3).strip()
        return None, None, title

    def _parse_price(self, text: str) -> float | None:
        if not text:
            return None
        text = text.replace(",", "").replace("$", "").strip()
        nums = re.findall(r"[\d.]+", text)
        if nums:
            try:
                return float(nums[0])
            except ValueError:
                return None
        return None

    def _parse_api_listing(self, item: dict) -> dict | None:
        try:
            title = item.get("title", "")
            year, make, model = self._parse_title(title)

            # Determine sold status first
            is_sold = item.get("status", "").lower() in ("sold", "completed")

            # Parse sold_price, handling text values like "Not Sold" or "Bid to $X"
            sold_price_raw = item.get("sold_price") or item.get("price")
            if isinstance(sold_price_raw, str):
                if "not sold" in sold_price_raw.lower() or "bid to" in sold_price_raw.lower():
                    is_sold = False
                    sold_price = self._parse_price(sold_price_raw)  # extract bid amount
                else:
                    sold_price = self._parse_price(sold_price_raw)
            else:
                sold_price = sold_price_raw

            bid_count = item.get("bid_count") or item.get("bids")
            if isinstance(bid_count, str):
                nums = re.findall(r"\d+", bid_count)
                bid_count = int(nums[0]) if nums else None

            url = item.get("url", "")
            if url and not url.startswith("http"):
                url = f"{self.BASE_URL}{url}"

            return {
                "year": year or item.get("year"),
                "make": make or item.get("make"),
                "model": model or item.get("model"),
                "sold_price": sold_price if is_sold else None,
                "starting_bid": sold_price if not is_sold else None,  # bid amount for unsold
                "bid_count": bid_count,
                "url": url,
                "image_url": item.get("image") or item.get("photo_url") or item.get("thumbnail"),
                "is_sold": is_sold,
                "description": title,
                "auction_end_date": item.get("end_date"),
            }
        except Exception as e:
            logger.warning(f"[Cars&Bids] Error parsing API item: {e}")
            return None

    def _parse_html_listing(self, card) -> dict | None:
        try:
            title_el = card.select_one("a h3, .auction-title a, a.hero-link")
            if not title_el:
                title_el = card.select_one("a[href*='/auctions/']")
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            url = title_el.get("href", "")
            if not url:
                parent_a = title_el.find_parent("a")
                if parent_a:
                    url = parent_a.get("href", "")
            if url and not url.startswith("http"):
                url = f"{self.BASE_URL}{url}"

            year, make, model = self._parse_title(title)

            price = None
            price_el = card.select_one(".auction-result, .sold-price, .current-bid")
            if price_el:
                price = self._parse_price(price_el.get_text(strip=True))

            img_url = None
            img_el = card.select_one("img")
            if img_el:
                img_url = img_el.get("src") or img_el.get("data-src")

            bid_count = None
            bids_el = card.select_one(".bid-number, .bids")
            if bids_el:
                nums = re.findall(r"\d+", bids_el.get_text(strip=True))
                if nums:
                    bid_count = int(nums[0])

            is_sold = "sold" in card.get_text(strip=True).lower()

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
            logger.warning(f"[Cars&Bids] Error parsing HTML card: {e}")
            return None

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
        captured_api_data = []

        try:
            from playwright.async_api import async_playwright
            from playwright_stealth import stealth_async
        except ImportError as e:
            logger.error(f"[Cars&Bids] Playwright not available: {e}")
            return []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            )
            page = await context.new_page()
            await stealth_async(page)

            # Intercept API calls to capture JSON data
            async def handle_response(response):
                url = response.url
                if "/api/" in url or "/search" in url or "/auctions" in url:
                    try:
                        if "application/json" in (response.headers.get("content-type", "")):
                            data = await response.json()
                            if isinstance(data, dict):
                                items = data.get("results") or data.get("auctions") or data.get("data") or data.get("items")
                                if items and isinstance(items, list):
                                    captured_api_data.extend(items)
                            elif isinstance(data, list):
                                captured_api_data.extend(data)
                    except Exception:
                        pass

            page.on("response", handle_response)

            # Build search query
            query_parts = [make]
            if model:
                query_parts.append(model)
            query = " ".join(query_parts)

            # Navigate to past results/search page
            search_url = f"{self.BASE_URL}/past-auctions/?q={query}"
            if year_from:
                search_url += f"&yearFrom={year_from}"
            if year_to:
                search_url += f"&yearTo={year_to}"

            logger.info(f"[Cars&Bids] Navigating to {search_url}")

            try:
                await page.goto(search_url, wait_until="networkidle", timeout=30000)
            except Exception as e:
                logger.warning(f"[Cars&Bids] Navigation timeout (continuing): {e}")

            await page.wait_for_timeout(3000)

            # If we captured API data, use that
            if captured_api_data:
                logger.info(f"[Cars&Bids] Captured {len(captured_api_data)} items via API interception")
                for item in captured_api_data:
                    parsed = self._parse_api_listing(item)
                    if parsed:
                        all_listings.append(parsed)
            else:
                # Fallback: parse the rendered HTML
                from bs4 import BeautifulSoup
                html = await page.content()
                soup = BeautifulSoup(html, "lxml")

                cards = soup.select(
                    ".auction-card, .past-auction, .search-result, "
                    "[class*='auction'], [class*='listing']"
                )

                if not cards:
                    cards = soup.find_all("a", href=re.compile(r"/auctions/"))
                    cards = [
                        link.find_parent(["div", "li", "article"]) or link
                        for link in cards
                    ]

                for card in cards:
                    parsed = self._parse_html_listing(card)
                    if parsed:
                        all_listings.append(parsed)

            # Try to load more pages by scrolling
            for page_num in range(2, max_pages + 1):
                if not all_listings:
                    break

                await self._delay()

                # Try clicking "Load More" or scrolling
                try:
                    load_more = page.locator(
                        "button:has-text('Load More'), "
                        "button:has-text('Show More'), "
                        "a:has-text('Next'), "
                        "[class*='load-more'], [class*='pagination'] a:last-child"
                    )
                    if await load_more.count() > 0:
                        prev_count = len(captured_api_data)
                        await load_more.first.click()
                        await page.wait_for_timeout(3000)

                        # Check if new API data was captured
                        new_items = captured_api_data[prev_count:]
                        if new_items:
                            for item in new_items:
                                parsed = self._parse_api_listing(item)
                                if parsed:
                                    all_listings.append(parsed)
                        else:
                            break
                    else:
                        break
                except Exception:
                    break

                if on_progress:
                    await on_progress(page_num, max_pages, len(all_listings))

            logger.info(f"[Cars&Bids] Total listings found: {len(all_listings)}")
            await browser.close()

        # Filter by keyword if provided
        if keyword and all_listings:
            keyword_lower = keyword.lower()
            all_listings = [
                l for l in all_listings
                if keyword_lower in (l.get("description", "") or "").lower()
            ]

        # Filter by year range
        if year_from or year_to:
            filtered = []
            for l in all_listings:
                y = l.get("year")
                if y is None:
                    filtered.append(l)
                    continue
                if year_from and y < year_from:
                    continue
                if year_to and y > year_to:
                    continue
                filtered.append(l)
            all_listings = filtered

        return all_listings
