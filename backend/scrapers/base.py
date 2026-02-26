import asyncio
import random
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from backend.config import settings

logger = logging.getLogger(__name__)

PLAYWRIGHT_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
]


class BaseScraper(ABC):
    PLATFORM_NAME: str = ""
    MIN_DELAY: int = settings.MIN_SCRAPE_DELAY
    MAX_DELAY: int = settings.MAX_SCRAPE_DELAY
    MAX_RETRIES: int = 3

    @staticmethod
    def _compute_time_cutoff(time_filter: str | None) -> datetime | None:
        """Convert time_filter string to a cutoff datetime."""
        if not time_filter or time_filter == "all":
            return None
        now = datetime.now(timezone.utc)
        mapping = {
            "5m": timedelta(days=150),
            "1y": timedelta(days=365),
            "2y": timedelta(days=730),
        }
        delta = mapping.get(time_filter)
        return (now - delta) if delta else None

    @abstractmethod
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
        """Search for listings. Returns list of listing dicts."""
        pass

    async def _delay(self):
        delay = random.uniform(self.MIN_DELAY, self.MAX_DELAY)
        logger.debug(f"[{self.PLATFORM_NAME}] Waiting {delay:.1f}s")
        await asyncio.sleep(delay)

    async def _retry(self, coro_func, *args, **kwargs):
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return await coro_func(*args, **kwargs)
            except Exception as e:
                wait = 2 ** attempt + random.uniform(0, 1)
                logger.warning(
                    f"[{self.PLATFORM_NAME}] Attempt {attempt}/{self.MAX_RETRIES} "
                    f"failed: {e}. Retrying in {wait:.1f}s"
                )
                if attempt == self.MAX_RETRIES:
                    raise
                await asyncio.sleep(wait)
