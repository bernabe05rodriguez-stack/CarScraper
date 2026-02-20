# CarScraper

Web application for automotive market research. Searches auction platforms and used car sites (USA and Germany) for pricing data, market trends, and arbitrage opportunities.

## Tech Stack

- **Backend**: Python FastAPI + SQLAlchemy (async PostgreSQL)
- **Scraping**: httpx + BeautifulSoup4, Playwright (headless)
- **Frontend**: Vanilla HTML/CSS/JS
- **Export**: Excel via openpyxl
- **Deploy**: Docker + EasyPanel

## Quick Start (Docker)

```bash
# Clone and start
docker compose up --build

# Open browser
http://localhost:8000
```

## Development Setup

```bash
# Install dependencies
pip install -r backend/requirements.txt
playwright install chromium

# Start PostgreSQL (or use docker compose up db)
# Set DATABASE_URL in .env

# Run dev server
uvicorn backend.main:app --reload
```

## Features

### Auction Search
- Search **Bring a Trailer** and **Cars & Bids** for completed auctions
- Filter by make, model, year range, keyword, time period
- View sold prices, bid counts, auction duration
- Mean and median price statistics
- Export results to Excel with hyperlinks

### USA Used Cars
- Search **Autotrader** and **Cars.com** for active listings
- Average list price, mileage, days on market
- Mean and median statistics
- Export to Excel with links

### Germany Used Cars
- Search **Mobile.de**, **AutoScout24**, and **Kleinanzeigen**
- Prices in EUR with proper formatting
- Same metrics as USA (adapted for km)
- Export to Excel with links

### Price Comparison / Arbitrage
- Compare USA vs Germany average prices for same make/model/year
- Live EUR/USD conversion
- Identifies arbitrage opportunities with price delta

### Historical Database
- Background scheduler collects data periodically
- Configurable via WatchList table
- Builds historical pricing data over time

## API

```
POST /api/v1/auctions/search         - Start auction search
GET  /api/v1/auctions/results/{id}   - Get auction results

POST /api/v1/used-cars/search        - Start used car search
GET  /api/v1/used-cars/results/{id}  - Get used car results

POST /api/v1/comparison/analyze      - Compare USA vs Germany

GET  /api/v1/jobs/{id}               - Check job status
GET  /api/v1/export/{id}             - Download Excel
GET  /api/v1/makes                   - List makes
GET  /api/v1/models/{make}           - List models
```

## Deploy to EasyPanel

1. Push code to GitHub
2. In EasyPanel: Create project "CarScraper"
3. Add PostgreSQL service (Database > PostgreSQL)
4. Add App service (Docker) connected to your GitHub repo
5. Set environment variables (copy from `.env.example`)
6. Set `DATABASE_URL` using the PostgreSQL connection string from EasyPanel
7. Assign domain and enable SSL
