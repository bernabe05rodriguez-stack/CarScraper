from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./carscraper.db"
    CACHE_TTL_HOURS: int = 6
    MIN_SCRAPE_DELAY: int = 3
    MAX_SCRAPE_DELAY: int = 8
    DEBUG: bool = False

    BASE_DIR: Path = Path(__file__).resolve().parent
    DATA_DIR: Path = BASE_DIR / "data"
    FRONTEND_DIR: Path = BASE_DIR.parent / "frontend"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
