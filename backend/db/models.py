from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, Index
)
from backend.db.database import Base


class Platform(Base):
    __tablename__ = "platforms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    platform_type = Column(String(50), nullable=False)  # "auction" or "used_car"
    region = Column(String(50), nullable=False)  # "USA", "Germany"
    base_url = Column(String(500))
    is_active = Column(Boolean, default=True)


class AuctionListing(Base):
    __tablename__ = "auction_listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_id = Column(Integer, ForeignKey("platforms.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("scrape_jobs.id"), nullable=False)
    year = Column(Integer)
    make = Column(String(100))
    model = Column(String(200))
    starting_bid = Column(Float)
    sold_price = Column(Float)
    auction_days = Column(Integer)
    bid_count = Column(Integer)
    times_listed = Column(Integer, default=1)
    description = Column(Text)
    url = Column(String(1000))
    image_url = Column(String(1000))
    auction_end_date = Column(DateTime(timezone=True))
    is_sold = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_auction_make_model", "make", "model"),
        Index("ix_auction_year", "year"),
        Index("ix_auction_job_id", "job_id"),
    )


class UsedCarListing(Base):
    __tablename__ = "used_car_listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_id = Column(Integer, ForeignKey("platforms.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("scrape_jobs.id"), nullable=False)
    year = Column(Integer)
    make = Column(String(100))
    model = Column(String(200))
    trim = Column(String(200))
    list_price = Column(Float)
    mileage = Column(Integer)
    days_on_market = Column(Integer)
    dealer_name = Column(String(300))
    location = Column(String(300))
    description = Column(Text)
    url = Column(String(1000))
    image_url = Column(String(1000))
    listing_date = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    currency = Column(String(10), default="USD")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_usedcar_make_model", "make", "model"),
        Index("ix_usedcar_year", "year"),
        Index("ix_usedcar_job_id", "job_id"),
        Index("ix_usedcar_platform_id", "platform_id"),
    )


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    progress = Column(Integer, default=0)  # 0-100
    total_results = Column(Integer, default=0)
    platforms_requested = Column(String(500))  # comma-separated
    search_params = Column(Text)  # JSON
    job_type = Column(String(50), default="auction")  # "auction" or "used_car"
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True))


class SearchCache(Base):
    __tablename__ = "search_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cache_key = Column(String(500), unique=True, nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("scrape_jobs.id"))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)


class WatchList(Base):
    __tablename__ = "watch_list"

    id = Column(Integer, primary_key=True, autoincrement=True)
    make = Column(String(100), nullable=False)
    model = Column(String(200))
    year_from = Column(Integer)
    year_to = Column(Integer)
    platforms = Column(String(500))  # comma-separated
    interval_hours = Column(Integer, default=12)
    is_active = Column(Boolean, default=True)
    last_run_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
