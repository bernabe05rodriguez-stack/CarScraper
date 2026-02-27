import re
import json
import logging

from backend.scrapers.base import BaseScraper, PLAYWRIGHT_ARGS, apply_stealth

logger = logging.getLogger(__name__)


class AutotraderScraper(BaseScraper):
    PLATFORM_NAME = "Autotrader"
    BASE_URL = "https://www.autotrader.com"

    def _build_search_url(
        self,
        make: str,
        model: str | None,
        year_from: int | None,
        year_to: int | None,
        keyword: str | None,
        page: int,
    ) -> str:
        path = "/cars-for-sale/all-cars"
        if make:
            path += f"/{make.lower().replace(' ', '-')}"
        if model:
            path += f"/{model.lower().replace(' ', '-')}"

        params = {
            "searchRadius": "0",
            "isNewSearch": "true",
            "sortBy": "relevance",
            "numRecords": "25",
            "firstRecord": str((page - 1) * 25),
        }
        if year_from:
            params["startYear"] = str(year_from)
        if year_to:
            params["endYear"] = str(year_to)
        if keyword:
            params["keywordPhrases"] = keyword

        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.BASE_URL}{path}?{param_str}"

    def _parse_listing(self, item: dict) -> dict | None:
        try:
            title = item.get("title", "")
            year, make, model, trim = self._parse_title(title)

            price = item.get("pricingDetail", {}).get("primary")
            if isinstance(price, str):
                price = self._parse_price(price)
            elif not isinstance(price, (int, float)):
                price = item.get("price") or item.get("listPrice")
                if isinstance(price, str):
                    price = self._parse_price(price)

            mileage = item.get("specifications", {}).get("mileage", {}).get("value")
            if isinstance(mileage, str):
                mileage = int(re.sub(r"[^\d]", "", mileage)) if re.search(r"\d", mileage) else None

            return {
                "year": year,
                "make": make,
                "model": model,
                "trim": trim,
                "list_price": price,
                "mileage": mileage,
                "days_on_market": item.get("daysOnMarket"),
                "dealer_name": item.get("owner", {}).get("name"),
                "location": item.get("owner", {}).get("location", {}).get("city", ""),
                "description": title,
                "url": f"{self.BASE_URL}{item.get('href', '')}" if item.get("href") else item.get("url", ""),
                "image_url": item.get("image") or item.get("primaryPhotoUrl"),
                "is_active": True,
                "currency": "USD",
            }
        except Exception as e:
            logger.warning(f"[Autotrader] Error parsing listing: {e}")
            return None

    def _parse_html_listing(self, card) -> dict | None:
        try:
            # Title - try multiple selectors
            title_el = card.select_one("h2, h3, [data-cmp='inventoryListingTitle']")
            if not title_el:
                title_el = card.select_one("a[href*='/cars-for-sale/']")
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            if not title:
                return None
            year, make, model, trim = self._parse_title(title)

            # URL
            url = ""
            link_el = card.select_one("a[href*='/cars-for-sale/']")
            if link_el:
                href = link_el.get("href", "")
                url = href if href.startswith("http") else f"{self.BASE_URL}{href}"

            # Price
            price = None
            price_el = card.select_one(".first-price, [data-cmp='firstPrice'], .primary-price, [class*='price']")
            if price_el:
                price = self._parse_price(price_el.get_text(strip=True))

            # Mileage
            mileage = None
            for el in card.select("[class*='mileage'], [class*='specifications'], li"):
                text = el.get_text(strip=True).lower()
                if "mi" in text or "mile" in text:
                    nums = re.findall(r"[\d,]+", text)
                    if nums:
                        mileage = int(nums[0].replace(",", ""))
                        break

            # Dealer
            dealer = None
            dealer_el = card.select_one("[class*='dealer'], .dealer-name")
            if dealer_el:
                dealer = dealer_el.get_text(strip=True)

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
                "location": None,
                "description": title,
                "url": url,
                "image_url": img_url,
                "is_active": True,
                "currency": "USD",
            }
        except Exception as e:
            logger.warning(f"[Autotrader] Error parsing HTML card: {e}")
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

    def _extract_next_data(self, html: str) -> list[dict]:
        """Try to extract listings from __NEXT_DATA__ JSON (if Autotrader uses Next.js)."""
        match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>', html)
        if not match:
            return []
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []

        def find_listings(obj, depth=0):
            if depth > 6:
                return None
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ("listings", "results", "vehicles") and isinstance(v, list) and len(v) > 0:
                        return v
                    result = find_listings(v, depth + 1)
                    if result:
                        return result
            return None

        return find_listings(data) or []

    async def search(
        self,
        make: str,
        model: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        keyword: str | None = None,
        time_filter: str | None = None,
        max_pages: int = 5,
        on_progress: callable = None,
    ) -> list[dict]:
        all_listings = []
        captured_api_data = []

        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            logger.error(f"[Autotrader] Playwright not available: {e}")
            return []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=PLAYWRIGHT_ARGS)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            )
            page = await context.new_page()
            await apply_stealth(page)

            # Intercept API responses
            async def handle_response(response):
                url = response.url
                if any(p in url for p in ["/rest/searchresults", "/api/", "/rest/lsc/", "searchResults"]):
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            data = await response.json()
                            if isinstance(data, dict):
                                items = (
                                    data.get("listings") or data.get("results")
                                    or data.get("vehicles") or data.get("items")
                                )
                                if items and isinstance(items, list):
                                    captured_api_data.extend(items)
                    except Exception:
                        pass

            page.on("response", handle_response)

            for page_num in range(1, max_pages + 1):
                search_url = self._build_search_url(make, model, year_from, year_to, keyword, page_num)
                logger.info(f"[Autotrader] Page {page_num}: {search_url}")

                try:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    logger.warning(f"[Autotrader] Navigation timeout page {page_num}: {e}")

                # Wait for JS rendering
                await page.wait_for_timeout(8000)

                # Bot detection check
                page_title = await page.title()
                current_url = page.url
                logger.info(f"[Autotrader] Page {page_num} loaded: title='{page_title}' url={current_url}")
                if any(w in page_title.lower() for w in ["captcha", "blocked", "access denied", "security"]):
                    logger.warning(f"[Autotrader] Bot detection on page {page_num}, stopping")
                    break

                # Smart wait for listing elements
                try:
                    await page.wait_for_selector(
                        "[data-cmp='inventoryListing'], .inventory-listing, .vehicle-card, [data-testid='listing']",
                        timeout=10000,
                    )
                except Exception:
                    logger.debug(f"[Autotrader] No listing selector appeared on page {page_num}")

                # Strategy 1: Check API intercepted data
                if captured_api_data:
                    new_items = captured_api_data[len(all_listings):]
                    for item in new_items:
                        parsed = self._parse_listing(item)
                        if parsed:
                            all_listings.append(parsed)
                    if all_listings:
                        logger.info(f"[Autotrader] API data: {len(all_listings)} listings")
                        if on_progress:
                            await on_progress(page_num, max_pages, len(all_listings))
                        if page_num < max_pages:
                            await self._delay()
                        continue

                # Strategy 2: Try __NEXT_DATA__ JSON
                html = await page.content()
                json_listings = self._extract_next_data(html)
                if json_listings:
                    for item in json_listings:
                        parsed = self._parse_listing(item)
                        if parsed:
                            all_listings.append(parsed)
                    logger.info(f"[Autotrader] JSON data: {len(json_listings)} listings")
                    if on_progress:
                        await on_progress(page_num, max_pages, len(all_listings))
                    if page_num < max_pages:
                        await self._delay()
                    continue

                # Strategy 3: Parse HTML
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "lxml")
                cards = soup.select(
                    "[data-cmp='inventoryListing'], .inventory-listing, "
                    "[class*='listing-card'], .vehicle-card, "
                    "[data-testid='listing']"
                )
                if not cards:
                    logger.info(f"[Autotrader] No results on page {page_num}")
                    break

                for card in cards:
                    parsed = self._parse_html_listing(card)
                    if parsed:
                        all_listings.append(parsed)

                logger.info(f"[Autotrader] HTML: {len(cards)} cards (total: {len(all_listings)})")

                if on_progress:
                    await on_progress(page_num, max_pages, len(all_listings))

                if page_num < max_pages:
                    await self._delay()

            logger.info(f"[Autotrader] Total listings found: {len(all_listings)}")
            await browser.close()

        return all_listings
