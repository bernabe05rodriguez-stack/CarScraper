import re
import json
import logging

from backend.scrapers.base import BaseScraper, PLAYWRIGHT_ARGS, apply_stealth

logger = logging.getLogger(__name__)


class CarsAndBidsScraper(BaseScraper):
    PLATFORM_NAME = "Cars & Bids"
    BASE_URL = "https://carsandbids.com"

    def _parse_title(self, title: str) -> tuple[int | None, str | None, str | None]:
        """Extract year, make, model — search year anywhere in title."""
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

            is_sold = item.get("status", "").lower() in ("sold", "completed")

            sold_price_raw = item.get("sold_price") or item.get("price") or item.get("currentBid")
            if isinstance(sold_price_raw, str):
                if "not sold" in sold_price_raw.lower() or "bid to" in sold_price_raw.lower():
                    is_sold = False
                sold_price = self._parse_price(sold_price_raw)
            else:
                sold_price = sold_price_raw

            bid_count = item.get("bid_count") or item.get("bids") or item.get("bidCount")
            if isinstance(bid_count, str):
                nums = re.findall(r"\d+", bid_count)
                bid_count = int(nums[0]) if nums else None

            url = item.get("url") or item.get("link", "")
            if url and not url.startswith("http"):
                url = f"{self.BASE_URL}{url}"

            img = item.get("image") or item.get("photo_url") or item.get("thumbnail") or item.get("primaryPhotoUrl")

            return {
                "year": year or item.get("year"),
                "make": make or item.get("make"),
                "model": model or item.get("model"),
                "sold_price": sold_price if is_sold else None,
                "starting_bid": sold_price if not is_sold else None,
                "bid_count": bid_count,
                "url": url,
                "image_url": img,
                "is_sold": is_sold,
                "description": title,
                "auction_end_date": item.get("end_date") or item.get("endDate"),
            }
        except Exception as e:
            logger.warning(f"[Cars&Bids] Error parsing API item: {e}")
            return None

    def _parse_html_listing(self, card) -> dict | None:
        try:
            # Title - multiple selector strategies
            title_el = (
                card.select_one("a h3")
                or card.select_one(".auction-title a, .auction-title")
                or card.select_one("a.hero-link")
                or card.select_one("h2 a, h3 a")
                or card.select_one("a[href*='/auctions/']")
            )
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            if not title:
                return None

            url = title_el.get("href", "")
            if not url:
                parent_a = title_el.find_parent("a")
                if parent_a:
                    url = parent_a.get("href", "")
            if url and not url.startswith("http"):
                url = f"{self.BASE_URL}{url}"

            year, make, model = self._parse_title(title)

            # Price
            price = None
            price_el = (
                card.select_one(".auction-result, .sold-price, .current-bid")
                or card.select_one("[class*='price'], [class*='bid']")
            )
            if price_el:
                price = self._parse_price(price_el.get_text(strip=True))

            # Image
            img_url = None
            img_el = card.select_one("img")
            if img_el:
                img_url = img_el.get("src") or img_el.get("data-src")

            # Bid count
            bid_count = None
            bids_el = card.select_one(".bid-number, .bids, [class*='bid-count']")
            if bids_el:
                nums = re.findall(r"\d+", bids_el.get_text(strip=True))
                if nums:
                    bid_count = int(nums[0])

            card_text = card.get_text(strip=True).lower()
            is_sold = "sold" in card_text and "not sold" not in card_text

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
        time_filter: str | None = None,
        max_pages: int = 10,
        on_progress: callable = None,
    ) -> list[dict]:
        all_listings = []
        captured_api_data = []

        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            logger.error(f"[Cars&Bids] Playwright not available: {e}")
            return []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=PLAYWRIGHT_ARGS)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            )
            page = await context.new_page()
            await apply_stealth(page)

            # Intercept API calls
            async def handle_response(response):
                url = response.url
                if any(p in url for p in ["/api/", "/search", "/auctions", "graphql"]):
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            data = await response.json()
                            if isinstance(data, dict):
                                items = (
                                    data.get("results") or data.get("auctions")
                                    or data.get("data") or data.get("items")
                                    or data.get("content")
                                )
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

            search_url = f"{self.BASE_URL}/past-auctions/?q={query}"
            if year_from:
                search_url += f"&yearFrom={year_from}"
            if year_to:
                search_url += f"&yearTo={year_to}"

            logger.info(f"[Cars&Bids] Navigating to {search_url}")

            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.warning(f"[Cars&Bids] Navigation timeout (continuing): {e}")

            await page.wait_for_timeout(5000)

            # Strategy 1: API intercepted data
            if captured_api_data:
                logger.info(f"[Cars&Bids] Captured {len(captured_api_data)} items via API")
                for item in captured_api_data:
                    parsed = self._parse_api_listing(item)
                    if parsed:
                        all_listings.append(parsed)

            # Strategy 2: Try __NEXT_DATA__ JSON
            if not all_listings:
                html = await page.content()
                match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>', html)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        def find_auctions(obj, depth=0):
                            if depth > 6:
                                return None
                            if isinstance(obj, dict):
                                for k, v in obj.items():
                                    if k in ("auctions", "results", "listings") and isinstance(v, list) and len(v) > 0:
                                        return v
                                    result = find_auctions(v, depth + 1)
                                    if result:
                                        return result
                            return None
                        items = find_auctions(data) or []
                        for item in items:
                            parsed = self._parse_api_listing(item)
                            if parsed:
                                all_listings.append(parsed)
                        if items:
                            logger.info(f"[Cars&Bids] JSON data: {len(items)} items")
                    except json.JSONDecodeError:
                        pass

            # Strategy 3: Parse HTML
            if not all_listings:
                from bs4 import BeautifulSoup
                html = await page.content()
                soup = BeautifulSoup(html, "lxml")

                cards = soup.select(
                    ".auction-card, .past-auction, .search-result, "
                    "[class*='auction-card'], [class*='AuctionCard'], "
                    "a[href*='/auctions/']"
                )

                if not cards:
                    links = soup.find_all("a", href=re.compile(r"/auctions/"))
                    seen = set()
                    for link in links:
                        href = link.get("href", "")
                        if href in seen or not href:
                            continue
                        seen.add(href)
                        parent = link.find_parent(["div", "li", "article"])
                        if parent:
                            cards.append(parent)

                for card in cards:
                    parsed = self._parse_html_listing(card)
                    if parsed:
                        all_listings.append(parsed)

            # Try to load more pages
            for page_num in range(2, max_pages + 1):
                if not all_listings:
                    break

                await self._delay()

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

        # Filter by keyword (search in title AND URL slug)
        if keyword and all_listings:
            keyword_lower = keyword.lower()
            all_listings = [
                l for l in all_listings
                if keyword_lower in (l.get("description", "") or "").lower()
                or keyword_lower in (l.get("url", "") or "").lower()
            ]

        # Filter by year range — EXCLUDE listings with unknown year
        if year_from or year_to:
            filtered = []
            for l in all_listings:
                y = l.get("year")
                if y is None:
                    continue
                if year_from and y < year_from:
                    continue
                if year_to and y > year_to:
                    continue
                filtered.append(l)
            all_listings = filtered

        # Filter by time period
        time_cutoff = self._compute_time_cutoff(time_filter)
        if time_cutoff and all_listings:
            before_count = len(all_listings)
            all_listings = [
                l for l in all_listings
                if l.get("auction_end_date") is None
                or (isinstance(l["auction_end_date"], str) and True)  # keep string dates we can't parse
                or l["auction_end_date"] >= time_cutoff
            ]
            logger.info(f"[Cars&Bids] Time filter ({time_filter}): {before_count} -> {len(all_listings)}")

        return all_listings
