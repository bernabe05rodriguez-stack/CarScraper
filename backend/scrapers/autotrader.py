import re
import logging

from backend.scrapers.base import BaseScraper

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
        # Autotrader URL pattern
        path = f"/cars-for-sale/all-cars"
        if make:
            path += f"/{make.lower().replace(' ', '-')}"
        if model:
            path += f"/{model.lower().replace(' ', '-')}"

        params = {
            "searchRadius": "0",  # nationwide
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

            price = item.get("pricingDetail", {}).get("primary", None)
            if isinstance(price, str):
                price = self._parse_price(price)
            elif isinstance(price, (int, float)):
                pass
            else:
                # Try alternative price fields
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
            # Title
            title_el = card.select_one("h2, .inventory-listing-title, [data-cmp='inventoryListingTitle']")
            if not title_el:
                title_el = card.select_one("a[href*='/cars-for-sale/']")
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            year, make, model, trim = self._parse_title(title)

            # URL
            url = ""
            link_el = card.select_one("a[href*='/cars-for-sale/']")
            if link_el:
                href = link_el.get("href", "")
                url = href if href.startswith("http") else f"{self.BASE_URL}{href}"

            # Price
            price = None
            price_el = card.select_one(".first-price, [data-cmp='firstPrice'], .primary-price")
            if price_el:
                price = self._parse_price(price_el.get_text(strip=True))

            # Mileage
            mileage = None
            mileage_el = card.select_one("[class*='mileage'], .item-card-specifications")
            if mileage_el:
                text = mileage_el.get_text(strip=True)
                nums = re.findall(r"[\d,]+", text.replace(",", ""))
                if nums:
                    mileage = int(nums[0])

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
        # "2019 BMW M3 Competition Package" -> (2019, "BMW", "M3", "Competition Package")
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
        captured_api_data = []

        try:
            from playwright.async_api import async_playwright
            from playwright_stealth import stealth_async
        except ImportError as e:
            logger.error(f"[Autotrader] Playwright not available: {e}")
            return []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            )
            page = await context.new_page()
            await stealth_async(page)

            # Intercept API responses
            async def handle_response(response):
                url = response.url
                if "/rest/searchresults" in url or "/api/" in url:
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            data = await response.json()
                            if isinstance(data, dict):
                                items = (data.get("listings") or data.get("results")
                                         or data.get("vehicles") or data.get("items"))
                                if items and isinstance(items, list):
                                    captured_api_data.extend(items)
                    except Exception:
                        pass

            page.on("response", handle_response)

            for page_num in range(1, max_pages + 1):
                search_url = self._build_search_url(make, model, year_from, year_to, keyword, page_num)
                logger.info(f"[Autotrader] Page {page_num}: {search_url}")

                try:
                    await page.goto(search_url, wait_until="networkidle", timeout=30000)
                except Exception as e:
                    logger.warning(f"[Autotrader] Navigation timeout page {page_num}: {e}")

                await page.wait_for_timeout(3000)

                # Check API data first
                if captured_api_data:
                    new_count = len(captured_api_data) - len(all_listings)
                    for item in captured_api_data[len(all_listings):]:
                        parsed = self._parse_listing(item)
                        if parsed:
                            all_listings.append(parsed)
                else:
                    # Fallback: parse HTML
                    from bs4 import BeautifulSoup
                    html = await page.content()
                    soup = BeautifulSoup(html, "lxml")
                    cards = soup.select(
                        "[data-cmp='inventoryListing'], .inventory-listing, "
                        "[class*='listing-card'], .vehicle-card"
                    )
                    if not cards:
                        logger.info(f"[Autotrader] No results on page {page_num}")
                        break

                    for card in cards:
                        parsed = self._parse_html_listing(card)
                        if parsed:
                            all_listings.append(parsed)

                if on_progress:
                    await on_progress(page_num, max_pages, len(all_listings))

                if page_num < max_pages:
                    await self._delay()

            logger.info(f"[Autotrader] Total listings found: {len(all_listings)}")
            await browser.close()

        return all_listings
