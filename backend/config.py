from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://carscraper:carscraper@localhost:5432/carscraper"
    CACHE_TTL_HOURS: int = 6
    MIN_SCRAPE_DELAY: int = 3
    MAX_SCRAPE_DELAY: int = 8
    DEBUG: bool = False
    EUR_USD_RATE: float = 1.08
    EUR_USD_API: str = "https://api.frankfurter.app/latest?from=EUR&to=USD"
    SCHEDULER_INTERVAL_HOURS: int = 12
    AUTH_USERNAME: str = "Admin-Klaus"
    AUTH_PASSWORD: str = "admin57453"
    AUTH_SECRET_KEY: str = "carscraper-secret-key-change-in-production"
    AUTH_TOKEN_MAX_AGE: int = 86400  # 24 hours in seconds

    BASE_DIR: Path = Path(__file__).resolve().parent
    DATA_DIR: Path = BASE_DIR / "data"
    FRONTEND_DIR: Path = BASE_DIR.parent / "frontend"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
