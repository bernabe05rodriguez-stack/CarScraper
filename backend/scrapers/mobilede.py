import re
import logging

from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class MobileDeScraper(BaseScraper):
    PLATFORM_NAME = "Mobile.de"
    BASE_URL = "https://suchen.mobile.de"

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
            "isSearchRequest": "true",
            "damageUnrepaired": "NO_DAMAGE_UNREPAIRED",
            "scopeId": "C",
            "sfmr": "false",
            "pageNumber": str(page),
        }
        # Mobile.de uses text-based search for make/model
        query_parts = []
        if make:
            query_parts.append(make)
        if model:
            query_parts.append(model)
        if query_parts:
            params["q"] = " ".join(query_parts)
        if year_from:
            params["minFirstRegistrationDate"] = str(year_from)
        if year_to:
            params["maxFirstRegistrationDate"] = str(year_to)
        if keyword:
            params["q"] = params.get("q", "") + " " + keyword

        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.BASE_URL}/fahrzeuge/search.html?{param_str}"

    def _parse_html_listing(self, card) -> dict | None:
        try:
            # Title
            title_el = card.select_one("a.link--muted, h2 a, .headline a, [data-testid='result-title']")
            if not title_el:
                title_el = card.select_one("a[href*='/fahrzeuge/details']")
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            year, make, model, trim = self._parse_title(title)

            # URL
            url = title_el.get("href", "")
            if url and not url.startswith("http"):
                url = f"https://www.mobile.de{url}"

            # Price (EUR)
            price = None
            price_el = card.select_one("[data-testid='price-label'], .price-block, .seller-currency")
            if price_el:
                price = self._parse_price_eur(price_el.get_text(strip=True))

            # Mileage (km)
            mileage = None
            mileage_el = card.select_one("[data-testid='mileage-label'], .rbt-regMil498")
            if mileage_el:
                text = mileage_el.get_text(strip=True)
                nums = re.findall(r"[\d.]+", text.replace(".", ""))
                if nums:
                    mileage = int(nums[0])

            # First registration (extract year for year field)
            reg_el = card.select_one("[data-testid='firstRegistration-label'], .rbt-regDate")
            if reg_el and not year:
                reg_text = reg_el.get_text(strip=True)
                year_match = re.search(r"(\d{4})", reg_text)
                if year_match:
                    year = int(year_match.group(1))

            # Dealer
            dealer = None
            dealer_el = card.select_one("[data-testid='seller-info'], .seller-info")
            if dealer_el:
                dealer = dealer_el.get_text(strip=True)[:100]

            # Location
            location = None
            loc_el = card.select_one("[data-testid='seller-address'], .seller-address")
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
            logger.warning(f"[Mobile.de] Error parsing card: {e}")
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
        # EUR prices: "25.900 \u20AC" or "25.900,00 \u20AC"
        text = text.replace("\u20AC", "").replace("EUR", "").strip()
        # German number format: "25.900" = 25900, "25.900,00" = 25900.00
        text = text.replace(".", "").replace(",", ".")
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

        try:
            from playwright.async_api import async_playwright
            from playwright_stealth import stealth_async
        except ImportError as e:
            logger.error(f"[Mobile.de] Playwright not available: {e}")
            return []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                locale="en-US",
            )
            page = await context.new_page()
            await stealth_async(page)

            for page_num in range(1, max_pages + 1):
                search_url = self._build_search_url(make, model, year_from, year_to, keyword, page_num)
                logger.info(f"[Mobile.de] Page {page_num}: {search_url}")

                try:
                    await page.goto(search_url, wait_until="networkidle", timeout=30000)
                except Exception as e:
                    logger.warning(f"[Mobile.de] Navigation timeout page {page_num}: {e}")

                await page.wait_for_timeout(3000)

                # Handle cookie consent
                try:
                    consent = page.locator("button:has-text('Accept'), button:has-text('Akzeptieren'), #mde-consent-accept-btn")
                    if await consent.count() > 0:
                        await consent.first.click()
                        await page.wait_for_timeout(1000)
                except Exception:
                    pass

                from bs4 import BeautifulSoup
                html = await page.content()
                soup = BeautifulSoup(html, "lxml")

                cards = soup.select(
                    "[data-testid='result-listing'], .cBox-body--resultitem, "
                    ".result-item, .search-result-entry"
                )

                if not cards:
                    links = soup.find_all("a", href=re.compile(r"/fahrzeuge/details"))
                    cards = [link.find_parent(["div", "li", "article"]) or link for link in links]

                if not cards:
                    logger.info(f"[Mobile.de] No results on page {page_num}")
                    break

                for card in cards:
                    parsed = self._parse_html_listing(card)
                    if parsed:
                        all_listings.append(parsed)

                logger.info(f"[Mobile.de] Page {page_num}: {len(cards)} cards (total: {len(all_listings)})")

                if on_progress:
                    await on_progress(page_num, max_pages, len(all_listings))

                if page_num < max_pages:
                    await self._delay()

            logger.info(f"[Mobile.de] Total listings found: {len(all_listings)}")
            await browser.close()

        return all_listings
