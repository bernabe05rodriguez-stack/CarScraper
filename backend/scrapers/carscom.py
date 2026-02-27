import re
import logging
from urllib.parse import quote_plus

import httpx

from backend.config import settings
from backend.scrapers.base import BaseScraper, PLAYWRIGHT_ARGS, apply_stealth

logger = logging.getLogger(__name__)

SCRAPER_API_BASE = "https://api.scraperapi.com"


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
            # Title - multiple selector strategies
            title_el = card.select_one("h2 a, a.vehicle-card-link")
            if not title_el:
                title_el = card.select_one("a[href*='/vehicledetail/']")
            if not title_el:
                # Try any h2 inside the card
                h2 = card.select_one("h2")
                if h2:
                    title_el = h2
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            if not title:
                return None
            year, make, model, trim = self._parse_title(title)

            # URL
            url = ""
            if title_el.name == "a":
                url = title_el.get("href", "")
            else:
                link = card.select_one("a[href*='/vehicledetail/']")
                if link:
                    url = link.get("href", "")
            if url and not url.startswith("http"):
                url = f"{self.BASE_URL}{url}"

            # Price
            price = None
            price_el = card.select_one(".primary-price, span.primary-price, [class*='primary-price']")
            if not price_el:
                price_el = card.select_one("[class*='price']")
            if price_el:
                price = self._parse_price(price_el.get_text(strip=True))

            # Mileage
            mileage = None
            mileage_el = card.select_one(".mileage, [class*='mileage']")
            if mileage_el:
                text = mileage_el.get_text(strip=True)
                nums = re.findall(r"[\d,]+", text)
                if nums:
                    mileage = int(nums[0].replace(",", ""))

            # Dealer
            dealer = None
            dealer_el = card.select_one(".dealer-name, [class*='dealer-name']")
            if dealer_el:
                dealer = dealer_el.get_text(strip=True)

            # Location
            location = None
            loc_el = card.select_one(".miles-from, [class*='miles-from']")
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
        # Strip common prefixes: "Used", "New", "Certified Pre-Owned", "CPO"
        cleaned = re.sub(r'^(Used|New|Certified Pre-Owned|Certified|CPO)\s+', '', title, flags=re.IGNORECASE)
        match = re.match(r"(\d{4})\s+(\S+)\s+(\S+)\s*(.*)", cleaned)
        if match:
            return int(match.group(1)), match.group(2), match.group(3), match.group(4).strip() or None
        match = re.match(r"(\d{4})\s+(\S+)\s+(.*)", cleaned)
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
        time_filter: str | None = None,
        max_pages: int = 5,
        on_progress: callable = None,
    ) -> list[dict]:
        if settings.SCRAPER_API_KEY:
            return await self._search_via_api(
                make, model, year_from, year_to, keyword, max_pages, on_progress,
            )
        return await self._search_playwright(
            make, model, year_from, year_to, keyword, max_pages, on_progress,
        )

    async def _search_via_api(
        self,
        make: str,
        model: str | None,
        year_from: int | None,
        year_to: int | None,
        keyword: str | None,
        max_pages: int,
        on_progress: callable,
    ) -> list[dict]:
        """Search via ScraperAPI (handles anti-bot, renders JS)."""
        all_listings = []
        from bs4 import BeautifulSoup

        logger.info(f"[Cars.com] Using ScraperAPI (key={settings.SCRAPER_API_KEY[:8]}...)")

        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
            for page_num in range(1, max_pages + 1):
                target_url = self._build_search_url(make, model, year_from, year_to, keyword, page_num)
                api_url = (
                    f"{SCRAPER_API_BASE}"
                    f"?api_key={settings.SCRAPER_API_KEY}"
                    f"&url={quote_plus(target_url)}"
                    f"&render=true"
                )
                logger.info(f"[Cars.com] ScraperAPI page {page_num}: {target_url}")

                try:
                    resp = await client.get(api_url)
                    logger.info(f"[Cars.com] ScraperAPI response: status={resp.status_code}, size={len(resp.text)} bytes")
                    if resp.status_code != 200:
                        logger.warning(f"[Cars.com] ScraperAPI returned {resp.status_code}: {resp.text[:200]}")
                        break
                    html = resp.text
                    if len(html) < 1000:
                        logger.warning(f"[Cars.com] ScraperAPI tiny response: {html[:200]}")
                        break
                except Exception as e:
                    logger.error(f"[Cars.com] ScraperAPI request failed: {e}")
                    break

                soup = BeautifulSoup(html, "lxml")

                cards = soup.select(
                    ".vehicle-card, [class*='vehicle-card'], "
                    "[data-qa='results-card'], .listing-row"
                )

                if not cards:
                    links = soup.find_all("a", href=re.compile(r"/vehicledetail/"))
                    seen = set()
                    for link in links:
                        href = link.get("href", "")
                        if href in seen:
                            continue
                        seen.add(href)
                        parent = link.find_parent(["div", "section", "article"])
                        if parent:
                            cards.append(parent)

                if not cards:
                    logger.info(f"[Cars.com] No results on page {page_num}")
                    break

                for card in cards:
                    parsed = self._parse_listing_card(card)
                    if parsed:
                        all_listings.append(parsed)

                logger.info(f"[Cars.com] Page {page_num}: {len(cards)} cards (total: {len(all_listings)})")

                if on_progress:
                    await on_progress(page_num, max_pages, len(all_listings))

                if page_num < max_pages:
                    await self._delay()

        logger.info(f"[Cars.com] Total listings found: {len(all_listings)}")
        return all_listings

    async def _search_playwright(
        self,
        make: str,
        model: str | None,
        year_from: int | None,
        year_to: int | None,
        keyword: str | None,
        max_pages: int,
        on_progress: callable,
    ) -> list[dict]:
        """Fallback: Playwright-based scraping (may fail due to anti-bot)."""
        all_listings = []

        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            logger.error(f"[Cars.com] Playwright not available: {e}")
            return []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=PLAYWRIGHT_ARGS)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                locale="en-US",
            )
            page = await context.new_page()
            await apply_stealth(page)

            for page_num in range(1, max_pages + 1):
                search_url = self._build_search_url(make, model, year_from, year_to, keyword, page_num)
                logger.info(f"[Cars.com] Page {page_num}: {search_url}")

                try:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    logger.warning(f"[Cars.com] Navigation timeout page {page_num}: {e}")

                await page.wait_for_timeout(8000)

                page_title = await page.title()
                current_url = page.url
                logger.info(f"[Cars.com] Page {page_num} loaded: title='{page_title}' url={current_url}")
                if any(w in page_title.lower() for w in ["captcha", "blocked", "access denied", "security"]):
                    logger.warning(f"[Cars.com] Bot detection on page {page_num}, stopping")
                    break

                try:
                    await page.wait_for_selector(
                        ".vehicle-card, [data-qa='results-card'], .listing-row",
                        timeout=10000,
                    )
                except Exception:
                    logger.debug(f"[Cars.com] No listing selector appeared on page {page_num}")

                from bs4 import BeautifulSoup
                html = await page.content()
                soup = BeautifulSoup(html, "lxml")

                cards = soup.select(
                    ".vehicle-card, [class*='vehicle-card'], "
                    "[data-qa='results-card'], .listing-row"
                )

                if not cards:
                    links = soup.find_all("a", href=re.compile(r"/vehicledetail/"))
                    seen = set()
                    for link in links:
                        href = link.get("href", "")
                        if href in seen:
                            continue
                        seen.add(href)
                        parent = link.find_parent(["div", "section", "article"])
                        if parent:
                            cards.append(parent)

                if not cards:
                    logger.info(f"[Cars.com] No results on page {page_num}")
                    break

                for card in cards:
                    parsed = self._parse_listing_card(card)
                    if parsed:
                        all_listings.append(parsed)

                logger.info(f"[Cars.com] Page {page_num}: {len(cards)} cards (total: {len(all_listings)})")

                if on_progress:
                    await on_progress(page_num, max_pages, len(all_listings))

                if page_num < max_pages:
                    await self._delay()

            logger.info(f"[Cars.com] Total listings found: {len(all_listings)}")
            await browser.close()

        return all_listings
