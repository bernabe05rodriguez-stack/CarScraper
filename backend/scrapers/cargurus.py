import re
import json
import logging
from urllib.parse import quote_plus

import httpx

from backend.config import settings
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SCRAPER_API_BASE = "https://api.scraperapi.com"

# CarGurus entity ID mappings
# Make name (lowercase) -> CarGurus make ID
MAKES = {
    "acura": "m4", "alfa romeo": "m124", "audi": "m19", "bmw": "m3",
    "buick": "m21", "cadillac": "m22", "chevrolet": "m1", "chrysler": "m23",
    "dodge": "m24", "fiat": "m98", "ford": "m2", "genesis": "m203",
    "gmc": "m26", "honda": "m6", "hyundai": "m28", "infiniti": "m84",
    "jaguar": "m31", "jeep": "m32", "kia": "m33", "land rover": "m35",
    "lexus": "m37", "lincoln": "m38", "maserati": "m40", "mazda": "m42",
    "mercedes-benz": "m43", "mini": "m45", "mitsubishi": "m46",
    "nissan": "m12", "pontiac": "m47", "porsche": "m48", "ram": "m191",
    "scion": "m52", "subaru": "m53", "toyota": "m7", "volkswagen": "m55",
    "volvo": "m56", "tesla": "m112", "aston martin": "m110",
    "ferrari": "m25", "lamborghini": "m34", "mclaren": "m141",
    "rolls-royce": "m49", "bentley": "m20", "rivian": "m233",
    "lucid": "m234", "polestar": "m219",
}

# Model name (lowercase) -> CarGurus entity ID, grouped by make
MODELS = {
    "acura": {"cl": "d191", "ilx": "d2137", "integra": "d36", "mdx": "d16", "nsx": "d17", "rdx": "d921", "rl": "d18", "rlx": "d2214", "rsx": "d3", "tl": "d19", "tlx": "d2278", "tsx": "d20", "zdx": "d2065"},
    "alfa romeo": {"4c": "d2277", "giulia": "d1751", "giulietta": "d1750", "spider": "d1149", "stelvio": "d2512"},
    "audi": {"a3": "d24", "a4": "d25", "a4 allroad": "d2149", "a5": "d1034", "a5 sportback": "d2508", "a6": "d27", "a6 allroad": "d2201", "a7": "d2113", "a8": "d29", "e-tron": "d2829", "q3": "d2129", "q5": "d1988", "q7": "d930", "q8": "d2792", "r8": "d1019", "rs 3": "d2564", "rs 5": "d2136", "rs 6 avant": "d2965", "rs 7": "d2230", "rs q8": "d2993", "s3": "d1183", "s4": "d30", "s5": "d1055", "s6": "d687", "s7": "d2156", "s8": "d688", "sq5": "d2237", "tt": "d32", "tt rs": "d2177", "tts": "d2176"},
    "bmw": {"1 series": "d1052", "2 series": "d2262", "3 series": "d1512", "4 series": "d2244", "5 series": "d1628", "6 series": "d1513", "7 series": "d1517", "8 series": "d1627", "i3": "d2263", "i4": "d2274", "i8": "d2274", "m2": "d2396", "m3": "d390", "m4": "d2258", "m5": "d391", "m6": "d825", "m8": "d2902", "x1": "d2160", "x2": "d2623", "x3": "d392", "x3 m": "d2847", "x4": "d2271", "x4 m": "d2848", "x5": "d393", "x5 m": "d2120", "x6": "d1137", "x6 m": "d2139", "x7": "d2656", "z3": "d394", "z4": "d395", "z8": "d396"},
    "buick": {"enclave": "d1029", "encore": "d2128", "encore gx": "d2901", "envision": "d2398", "lacrosse": "d272", "regal": "d277", "verano": "d2119"},
    "cadillac": {"ats": "d2138", "ct4": "d2963", "ct5": "d2876", "ct6": "d2352", "cts": "d138", "cts-v": "d139", "escalade": "d142", "escalade esv": "d143", "srx": "d148", "xt4": "d2673", "xt5": "d2393", "xt6": "d2843", "xts": "d2141"},
    "chevrolet": {"blazer": "d602", "bolt ev": "d2397", "camaro": "d606", "colorado": "d614", "corvette": "d1", "cruze": "d2076", "equinox": "d616", "impala": "d619", "malibu": "d622", "silverado 1500": "d630", "silverado 2500hd": "d634", "silverado 3500hd": "d1027", "sonic": "d2112", "spark": "d2008", "suburban": "d638", "tahoe": "d639", "trailblazer": "d642", "traverse": "d1521", "trax": "d2272"},
    "chrysler": {"200": "d2106", "300": "d165", "pacifica": "d177", "voyager": "d183"},
    "dodge": {"challenger": "d894", "charger": "d733", "dart": "d896", "durango": "d651", "grand caravan": "d653", "journey": "d1135", "ram 1500": "d665", "ram 2500": "d667", "viper": "d678"},
    "fiat": {"124 spider": "d1414", "500": "d1327", "500l": "d2199", "500x": "d2306"},
    "ford": {"bronco": "d320", "bronco sport": "d3094", "ecosport": "d2506", "edge": "d923", "escape": "d330", "expedition": "d333", "explorer": "d334", "f-150": "d337", "f-250 super duty": "d341", "f-350 super duty": "d343", "fiesta": "d1060", "flex": "d1049", "focus": "d346", "fusion": "d845", "mustang": "d2", "mustang mach-e": "d2990", "ranger": "d354", "taurus": "d355", "transit cargo": "d1067", "transit connect": "d2037"},
    "genesis": {"g70": "d2701", "g80": "d2438", "g90": "d2401", "gv80": "d3038"},
    "gmc": {"acadia": "d925", "canyon": "d103", "sierra 1500": "d116", "sierra 2500hd": "d119", "sierra 3500hd": "d973", "terrain": "d2042", "yukon": "d130", "yukon xl": "d132"},
    "honda": {"accord": "d585", "civic": "d586", "civic type r": "d2568", "cr-v": "d589", "element": "d590", "fit": "d744", "hr-v": "d1271", "insight": "d591", "odyssey": "d592", "passport": "d593", "pilot": "d594", "ridgeline": "d734", "s2000": "d596"},
    "hyundai": {"accent": "d91", "elantra": "d92", "kona": "d2663", "palisade": "d2836", "santa fe": "d94", "sonata": "d96", "tucson": "d98", "veloster": "d2124", "venue": "d2882"},
    "infiniti": {"q50": "d2207", "q60": "d2251", "qx50": "d2247", "qx55": "d3132", "qx60": "d2243", "qx80": "d2248"},
    "jaguar": {"e-pace": "d2613", "f-pace": "d2360", "f-type": "d2209", "i-pace": "d2672", "xe": "d2368", "xf": "d1136", "xj-series": "d286", "xk-series": "d288"},
    "jeep": {"cherokee": "d488", "compass": "d905", "gladiator": "d2021", "grand cherokee": "d490", "grand cherokee l": "d3108", "patriot": "d906", "renegade": "d2268", "wrangler": "d494", "wrangler unlimited": "d2412"},
    "kia": {"forte": "d2043", "k5": "d3092", "niro": "d2405", "optima": "d158", "rio": "d159", "seltos": "d2991", "sorento": "d162", "soul": "d2020", "sportage": "d164", "stinger": "d2510", "telluride": "d2830"},
    "land rover": {"defender": "d151", "discovery": "d152", "discovery sport": "d2304", "range rover": "d156", "range rover evoque": "d2121", "range rover sport": "d834", "range rover velar": "d2558"},
    "lexus": {"es": "d2720", "gs": "d2822", "gx": "d2063", "is": "d2824", "lc": "d2400", "ls": "d3040", "lx": "d3042", "nx": "d2616", "rc": "d2827", "rx": "d2647", "ux": "d2682"},
    "lincoln": {"aviator": "d524", "continental": "d526", "corsair": "d2884", "mkc": "d2259", "mkz": "d974", "nautilus": "d2680", "navigator": "d530"},
    "maserati": {"ghibli": "d1456", "granturismo": "d1465", "levante": "d2415", "quattroporte": "d402"},
    "mazda": {"cx-3": "d2301", "cx-30": "d2875", "cx-5": "d2133", "cx-9": "d1023", "mazda3": "d214", "mazda6": "d215", "miata": "d221", "mx-5 miata": "d221"},
    "mercedes-benz": {"a-class": "d1206", "amg gt": "d2282", "c-class": "d66", "cla-class": "d2216", "cls-class": "d751", "e-class": "d76", "g-class": "d78", "gla-class": "d2286", "glb-class": "d2905", "glc-class": "d2361", "gle-class": "d2317", "gls-class": "d2421", "s-class": "d82", "sl-class": "d84", "slk-class": "d87", "sprinter": "d1830"},
    "mini": {"cooper": "d436", "cooper clubman": "d1044", "countryman": "d2098"},
    "mitsubishi": {"eclipse cross": "d2666", "lancer": "d422", "mirage": "d426", "outlander": "d429", "outlander sport": "d2093"},
    "nissan": {"350z": "d236", "370z": "d2018", "altima": "d237", "armada": "d238", "frontier": "d240", "gt-r": "d1103", "juke": "d2072", "kicks": "d2660", "leaf": "d2077", "maxima": "d242", "murano": "d243", "pathfinder": "d245", "rogue": "d1047", "rogue sport": "d2513", "sentra": "d249", "titan": "d251", "versa": "d937"},
    "pontiac": {"firebird": "d466", "g6": "d467", "g8": "d979", "gto": "d470", "solstice": "d737", "vibe": "d477"},
    "porsche": {"718 boxster": "d2416", "718 cayman": "d2430", "911": "d404", "boxster": "d408", "cayenne": "d410", "cayman": "d993", "macan": "d2261", "panamera": "d1037", "taycan": "d2974"},
    "ram": {"1500": "d2110", "2500": "d2102", "3500": "d2103", "promaster": "d2229"},
    "scion": {"fr-s": "d2140", "tc": "d433", "xb": "d435"},
    "subaru": {"ascent": "d2650", "brz": "d2134", "crosstrek": "d2387", "forester": "d374", "impreza": "d375", "legacy": "d378", "outback": "d380", "wrx": "d2292", "wrx sti": "d2341"},
    "toyota": {"4runner": "d290", "86": "d2436", "avalon": "d291", "camry": "d292", "c-hr": "d2474", "corolla": "d295", "corolla hatchback": "d2697", "fj cruiser": "d826", "highlander": "d298", "land cruiser": "d299", "prius": "d15", "rav4": "d306", "sequoia": "d307", "sienna": "d308", "supra": "d309", "tacoma": "d311", "tundra": "d313", "venza": "d1516", "yaris": "d827"},
    "volkswagen": {"atlas": "d2507", "beetle": "d201", "golf": "d198", "golf gti": "d199", "golf r": "d2131", "id.4": "d3098", "jetta": "d200", "passat": "d202", "tiguan": "d1104", "touareg": "d205"},
    "volvo": {"s60": "d511", "s90": "d515", "v60": "d2266", "v90": "d520", "xc40": "d2624", "xc60": "d1629", "xc90": "d523"},
}


class CarGurusScraper(BaseScraper):
    PLATFORM_NAME = "CarGurus"
    BASE_URL = "https://www.cargurus.com"

    def _resolve_entity(self, make: str, model: str | None) -> str | None:
        """Resolve make/model to CarGurus entity ID."""
        make_lower = make.lower().strip()

        # Try to find model entity first (more specific)
        if model:
            model_lower = model.lower().strip()
            make_models = MODELS.get(make_lower, {})
            if model_lower in make_models:
                return make_models[model_lower]

            # Fuzzy match: try partial match
            for name, eid in make_models.items():
                if model_lower in name or name in model_lower:
                    return eid

        # Fall back to make entity
        if make_lower in MAKES:
            return MAKES[make_lower]

        # Try partial make match (e.g. "mercedes" -> "mercedes-benz")
        for name, mid in MAKES.items():
            if make_lower in name or name.startswith(make_lower):
                return mid

        return None

    def _build_search_url(
        self,
        make: str,
        model: str | None,
        year_from: int | None,
        year_to: int | None,
        entity_id: str,
    ) -> str:
        """Build CarGurus listing search URL."""
        # Use the listing page URL which embeds JSON data in the HTML
        make_fmt = make.replace(" ", "-")
        if model:
            model_fmt = model.replace(" ", "-")
            slug = f"l-Used-{make_fmt}-{model_fmt}-{entity_id}"
        else:
            slug = f"l-Used-{make_fmt}-{entity_id}"

        url = f"{self.BASE_URL}/Cars/{slug}"

        params = []
        if year_from:
            params.append(f"minYear={year_from}")
        if year_to:
            params.append(f"maxYear={year_to}")
        if params:
            url += "#" + "&".join(params)

        return url

    def _parse_listings_from_html(self, html: str) -> list[dict]:
        """Extract structured listing data from CarGurus rendered HTML."""
        listings = []
        seen_ids = set()

        # CarGurus embeds listing data in JSON within the HTML
        # Each listing has ontologyData, priceData, mileageData, etc.
        for m in re.finditer(r'"listingTitle":"([^"]*)"', html):
            title = m.group(1)
            start = max(0, m.start() - 2000)
            end = min(len(html), m.end() + 2000)
            window = html[start:end]

            # Extract listing ID to deduplicate
            id_m = re.search(r'"id":(\d{6,})', window)
            listing_id = id_m.group(1) if id_m else None
            if listing_id:
                if listing_id in seen_ids:
                    continue
                seen_ids.add(listing_id)

            # Extract fields from ontologyData
            year_m = re.search(r'"carYear":"(\d+)"', window)
            make_m = re.search(r'"makeName":"([^"]+)"', window)
            model_m = re.search(r'"modelName":"([^"]+)"', window)
            trim_m = re.search(r'"trimName":"([^"]+)"', window)

            # Price from priceData
            price_m = re.search(r'"priceData":\{[^}]*"current":(\d+)', window)
            if not price_m:
                price_m = re.search(r'"price":(\d+)', window)

            # Mileage
            mileage_m = re.search(r'"mileageData":\{"value":(\d+)', window)
            mileage_str = re.search(r'"localizedMileage":"([^"]+)"', window)

            # Location
            location_m = re.search(r'"displayLocation":"([^"]+)"', window)
            city_m = re.search(r'"sellerData":\{[^}]*"city":"([^"]+)"', window)

            # Image
            img_m = re.search(r'"pictureData":\{"url":"([^"]+)"', window)

            # Dealer
            dealer_m = re.search(r'"serviceProviderName":"([^"]+)"', window)

            # Days on market
            dom_m = re.search(r'"daysOnMarket":(\d+)', window)

            year = int(year_m.group(1)) if year_m else None
            make = make_m.group(1) if make_m else None
            model = model_m.group(1) if model_m else None
            trim = trim_m.group(1) if trim_m else None
            price = int(price_m.group(1)) if price_m else None
            mileage = int(mileage_m.group(1)) if mileage_m else None

            # Build URL
            url = ""
            if listing_id:
                url = f"{self.BASE_URL}/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action?entitySelectingHelper.selectedEntity=d{listing_id}"
                # Try to find a proper detail URL
                detail_m = re.search(rf'"url":"(https://www\.cargurus\.com/Cars/inventorylisting/[^"]*{listing_id}[^"]*)"', window)
                if not detail_m:
                    detail_m = re.search(rf'/Cars/l-Used[^"]*?{listing_id}', window)
                url = f"https://www.cargurus.com/details/{listing_id}"

            listing = {
                "year": year,
                "make": make,
                "model": model,
                "trim": trim,
                "list_price": float(price) if price else None,
                "mileage": mileage,
                "days_on_market": int(dom_m.group(1)) if dom_m else None,
                "dealer_name": dealer_m.group(1) if dealer_m else None,
                "location": location_m.group(1) if location_m else (city_m.group(1) if city_m else None),
                "description": title,
                "url": url,
                "image_url": img_m.group(1) if img_m else None,
                "is_active": True,
                "currency": "USD",
            }

            # Only add if we have at least year and make
            if year and make:
                listings.append(listing)

        return listings

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
        """Search CarGurus for used car listings."""
        entity_id = self._resolve_entity(make, model)
        if not entity_id:
            logger.warning(f"[CarGurus] Could not resolve entity for {make} {model}")
            return []

        logger.info(f"[CarGurus] Resolved {make} {model or ''} -> entity {entity_id}")

        if settings.SCRAPER_API_KEY:
            return await self._search_via_api(
                make, model, year_from, year_to, entity_id, on_progress,
            )
        return await self._search_playwright(
            make, model, year_from, year_to, entity_id, on_progress,
        )

    async def _search_via_api(
        self,
        make: str,
        model: str | None,
        year_from: int | None,
        year_to: int | None,
        entity_id: str,
        on_progress: callable,
    ) -> list[dict]:
        """Search via ScraperAPI with render=true."""
        target_url = self._build_search_url(make, model, year_from, year_to, entity_id)
        api_url = (
            f"{SCRAPER_API_BASE}"
            f"?api_key={settings.SCRAPER_API_KEY}"
            f"&url={quote_plus(target_url)}"
            f"&render=true"
            f"&country_code=us"
        )

        logger.info(f"[CarGurus] ScraperAPI request: {target_url}")

        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            try:
                resp = await client.get(api_url)
                logger.info(f"[CarGurus] ScraperAPI response: status={resp.status_code}, size={len(resp.text)} bytes")

                if resp.status_code != 200:
                    logger.warning(f"[CarGurus] ScraperAPI returned {resp.status_code}: {resp.text[:200]}")
                    return []

                html = resp.text
                if len(html) < 5000:
                    logger.warning(f"[CarGurus] ScraperAPI response too small: {len(html)} bytes")
                    return []

                listings = self._parse_listings_from_html(html)
                logger.info(f"[CarGurus] Parsed {len(listings)} listings from rendered HTML")

                # Filter by year if specified (URL hash params may not be applied)
                if year_from or year_to:
                    filtered = []
                    for l in listings:
                        if l["year"]:
                            if year_from and l["year"] < year_from:
                                continue
                            if year_to and l["year"] > year_to:
                                continue
                        filtered.append(l)
                    logger.info(f"[CarGurus] After year filter: {len(filtered)} listings")
                    listings = filtered

                if on_progress:
                    await on_progress(1, 1, len(listings))

                return listings

            except Exception as e:
                logger.error(f"[CarGurus] ScraperAPI request failed: {e}")
                return []

    async def _search_playwright(
        self,
        make: str,
        model: str | None,
        year_from: int | None,
        year_to: int | None,
        entity_id: str,
        on_progress: callable,
    ) -> list[dict]:
        """Fallback: Playwright-based scraping."""
        from backend.scrapers.base import PLAYWRIGHT_ARGS, apply_stealth

        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            logger.error(f"[CarGurus] Playwright not available: {e}")
            return []

        target_url = self._build_search_url(make, model, year_from, year_to, entity_id)
        logger.info(f"[CarGurus] Playwright request: {target_url}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=PLAYWRIGHT_ARGS)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                locale="en-US",
            )
            page = await context.new_page()
            await apply_stealth(page)

            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.warning(f"[CarGurus] Navigation timeout: {e}")

            await page.wait_for_timeout(8000)

            page_title = await page.title()
            logger.info(f"[CarGurus] Page loaded: title='{page_title}'")
            if any(w in page_title.lower() for w in ["captcha", "blocked", "access denied", "security"]):
                logger.warning("[CarGurus] Bot detection, stopping")
                await browser.close()
                return []

            html = await page.content()
            await browser.close()

            listings = self._parse_listings_from_html(html)
            logger.info(f"[CarGurus] Parsed {len(listings)} listings")

            if year_from or year_to:
                filtered = []
                for l in listings:
                    if l["year"]:
                        if year_from and l["year"] < year_from:
                            continue
                        if year_to and l["year"] > year_to:
                            continue
                    filtered.append(l)
                listings = filtered

            if on_progress:
                await on_progress(1, 1, len(listings))

            return listings
