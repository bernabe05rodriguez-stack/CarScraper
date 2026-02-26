import re
import logging

from backend.scrapers.base import BaseScraper, PLAYWRIGHT_ARGS

logger = logging.getLogger(__name__)


class KleinanzeigenScraper(BaseScraper):
    PLATFORM_NAME = "eBay Kleinanzeigen"
    BASE_URL = "https://www.kleinanzeigen.de"

    def _build_search_url(
        self,
        make: str,
        model: str | None,
        year_from: int | None,
        year_to: int | None,
        keyword: str | None,
        page: int,
    ) -> str:
        query_parts = []
        if make:
            query_parts.append(make.lower())
        if model:
            query_parts.append(model.lower())
        if keyword:
            query_parts.append(keyword)

        query = "-".join(query_parts) if query_parts else "auto"

        if page == 1:
            return f"{self.BASE_URL}/s-autos/{query}/k0c216"
        else:
            return f"{self.BASE_URL}/s-autos/seite:{page}/{query}/k0c216"

    def _parse_html_listing(self, card) -> dict | None:
        try:
            # Title - multiple selector strategies
            title_el = (
                card.select_one("a.ellipsis")
                or card.select_one("[data-testid='ad-title'] a")
                or card.select_one(".aditem-main--middle--title a")
                or card.select_one("h2 a, h3 a")
                or card.select_one("a[href*='/s-anzeige/']")
            )
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            if not title:
                return None
            year, make, model, trim = self._parse_title(title)

            url = title_el.get("href", "")
            if url and not url.startswith("http"):
                url = f"{self.BASE_URL}{url}"

            # Price (EUR)
            price = None
            price_el = (
                card.select_one("p.aditem-main--middle--price")
                or card.select_one(".aditem-main--middle--price-shipping--price")
                or card.select_one("[class*='price']")
            )
            if price_el:
                price = self._parse_price_eur(price_el.get_text(strip=True))

            # Extract mileage and year from card text
            mileage = None
            detail_text = card.get_text(" ", strip=True).lower()

            km_match = re.search(r"([\d.]+)\s*km", detail_text)
            if km_match:
                mileage_text = km_match.group(1).replace(".", "")
                try:
                    mileage = int(mileage_text)
                except ValueError:
                    pass

            if not year:
                year_match = re.search(r"\b(19\d{2}|20[0-2]\d)\b", detail_text)
                if year_match:
                    year = int(year_match.group(1))

            # Location
            location = None
            loc_el = (
                card.select_one(".aditem-main--top--left")
                or card.select_one("[class*='location']")
            )
            if loc_el:
                location = loc_el.get_text(strip=True)

            # Image
            img_url = None
            img_el = card.select_one("img")
            if img_el:
                img_url = img_el.get("src") or img_el.get("data-src") or img_el.get("srcset", "").split(" ")[0]

            return {
                "year": year,
                "make": make,
                "model": model,
                "trim": trim,
                "list_price": price,
                "mileage": mileage,
                "days_on_market": None,
                "dealer_name": None,
                "location": location,
                "description": title,
                "url": url,
                "image_url": img_url,
                "is_active": True,
                "currency": "EUR",
            }
        except Exception as e:
            logger.warning(f"[Kleinanzeigen] Error parsing card: {e}")
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
        text = text.replace("\u20AC", "").replace("EUR", "").replace("€", "").replace("VB", "").strip()
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
        time_filter: str | None = None,
        max_pages: int = 5,
        on_progress: callable = None,
    ) -> list[dict]:
        all_listings = []

        try:
            from playwright.async_api import async_playwright
            from playwright_stealth import stealth_async
        except ImportError as e:
            logger.error(f"[Kleinanzeigen] Playwright not available: {e}")
            return []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=PLAYWRIGHT_ARGS)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                locale="de-DE",
            )
            page = await context.new_page()
            await stealth_async(page)

            for page_num in range(1, max_pages + 1):
                search_url = self._build_search_url(make, model, year_from, year_to, keyword, page_num)
                logger.info(f"[Kleinanzeigen] Page {page_num}: {search_url}")

                try:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    logger.warning(f"[Kleinanzeigen] Navigation timeout page {page_num}: {e}")

                await page.wait_for_timeout(4000)

                # Handle cookie/GDPR consent
                try:
                    consent = page.locator(
                        "#gdpr-banner-accept, "
                        "button:has-text('Einverstanden'), "
                        "button:has-text('Accept'), "
                        "button:has-text('Alle akzeptieren'), "
                        "#consentAcceptAll"
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
                    "article.aditem, [data-testid='ad-listitem'], "
                    ".ad-listitem, li.ad-listitem, "
                    "[class*='aditem']"
                )

                if not cards:
                    links = soup.find_all("a", href=re.compile(r"/s-anzeige/"))
                    seen = set()
                    for link in links:
                        href = link.get("href", "")
                        if href in seen or not href:
                            continue
                        seen.add(href)
                        parent = link.find_parent(["article", "li", "div"])
                        if parent:
                            cards.append(parent)

                if not cards:
                    logger.info(f"[Kleinanzeigen] No results on page {page_num}")
                    break

                for card in cards:
                    parsed = self._parse_html_listing(card)
                    if parsed:
                        all_listings.append(parsed)

                logger.info(f"[Kleinanzeigen] Page {page_num}: {len(cards)} cards (total: {len(all_listings)})")

                if on_progress:
                    await on_progress(page_num, max_pages, len(all_listings))

                if page_num < max_pages:
                    await self._delay()

            # Filter by year range (Kleinanzeigen doesn't support year filter in URL)
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

            logger.info(f"[Kleinanzeigen] Total listings found: {len(all_listings)}")
            await browser.close()

        return all_listings
