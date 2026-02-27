import re
import json
import logging

from backend.scrapers.base import BaseScraper, PLAYWRIGHT_ARGS, apply_stealth

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
            # Title - try multiple selectors
            title_el = (
                card.select_one("a.link--muted")
                or card.select_one("[data-testid='result-title']")
                or card.select_one("h2 a")
                or card.select_one(".headline a")
                or card.select_one("a[href*='/fahrzeuge/details']")
            )
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            if not title:
                return None
            year, make, model, trim = self._parse_title(title)

            url = title_el.get("href", "")
            if url and not url.startswith("http"):
                url = f"https://www.mobile.de{url}"

            # Price (EUR)
            price = None
            price_el = (
                card.select_one("[data-testid='price-label']")
                or card.select_one(".price-block")
                or card.select_one(".seller-currency")
                or card.select_one("[class*='price']")
            )
            if price_el:
                price = self._parse_price_eur(price_el.get_text(strip=True))

            # Mileage
            mileage = None
            mileage_el = (
                card.select_one("[data-testid='mileage-label']")
                or card.select_one(".rbt-regMil498")
            )
            if mileage_el:
                text = mileage_el.get_text(strip=True)
                nums = re.findall(r"[\d.]+", text.replace(".", ""))
                if nums:
                    mileage = int(nums[0])

            # If no mileage found, search in all text for km pattern
            if not mileage:
                card_text = card.get_text(" ", strip=True)
                km_match = re.search(r"([\d.]+)\s*km", card_text)
                if km_match:
                    mileage_text = km_match.group(1).replace(".", "")
                    try:
                        mileage = int(mileage_text)
                    except ValueError:
                        pass

            # Year from registration
            if not year:
                reg_el = (
                    card.select_one("[data-testid='firstRegistration-label']")
                    or card.select_one(".rbt-regDate")
                )
                if reg_el:
                    reg_text = reg_el.get_text(strip=True)
                    year_match = re.search(r"(\d{4})", reg_text)
                    if year_match:
                        year = int(year_match.group(1))
                # Fallback: find year in card text
                if not year:
                    card_text = card.get_text(" ", strip=True)
                    reg_match = re.search(r"(?:EZ|Erstzulassung)[:\s]*(\d{2})/(\d{4})", card_text)
                    if reg_match:
                        year = int(reg_match.group(2))

            # Dealer
            dealer = None
            dealer_el = (
                card.select_one("[data-testid='seller-info']")
                or card.select_one(".seller-info")
            )
            if dealer_el:
                dealer = dealer_el.get_text(strip=True)[:100]

            # Location
            location = None
            loc_el = (
                card.select_one("[data-testid='seller-address']")
                or card.select_one(".seller-address")
            )
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
        text = text.replace("\u20AC", "").replace("EUR", "").replace("€", "").strip()
        text = text.replace(".", "").replace(",", ".")
        nums = re.findall(r"[\d.]+", text)
        if nums:
            try:
                return float(nums[0])
            except ValueError:
                return None
        return None

    def _extract_json_listings(self, html: str) -> list[dict]:
        """Try to extract listings from embedded JSON data."""
        # Mobile.de sometimes embeds data in script tags
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
                    if k in ("listings", "results", "searchResults") and isinstance(v, list) and len(v) > 0:
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

        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            logger.error(f"[Mobile.de] Playwright not available: {e}")
            return []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=PLAYWRIGHT_ARGS)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                locale="de-DE",
            )
            page = await context.new_page()
            await apply_stealth(page)

            for page_num in range(1, max_pages + 1):
                search_url = self._build_search_url(make, model, year_from, year_to, keyword, page_num)
                logger.info(f"[Mobile.de] Page {page_num}: {search_url}")

                try:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    logger.warning(f"[Mobile.de] Navigation timeout page {page_num}: {e}")

                await page.wait_for_timeout(4000)

                # Handle cookie consent
                try:
                    consent = page.locator(
                        "button:has-text('Accept'), "
                        "button:has-text('Akzeptieren'), "
                        "button:has-text('Alle akzeptieren'), "
                        "#mde-consent-accept-btn, "
                        "[data-testid='gdpr-consent-accept-btn']"
                    )
                    if await consent.count() > 0:
                        await consent.first.click()
                        await page.wait_for_timeout(2000)
                except Exception:
                    pass

                from bs4 import BeautifulSoup
                html = await page.content()
                soup = BeautifulSoup(html, "lxml")

                # Try multiple card selectors
                cards = soup.select(
                    "[data-testid='result-listing'], .cBox-body--resultitem, "
                    ".result-item, .search-result-entry, "
                    "[class*='result-listing'], [class*='ResultItem']"
                )

                if not cards:
                    links = soup.find_all("a", href=re.compile(r"/fahrzeuge/details"))
                    seen = set()
                    for link in links:
                        href = link.get("href", "")
                        if href in seen:
                            continue
                        seen.add(href)
                        parent = link.find_parent(["div", "li", "article"])
                        if parent:
                            cards.append(parent)

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
