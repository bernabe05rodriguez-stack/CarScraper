# CarScraper

Web application for automotive market research. Searches auction platforms and used car sites for pricing data, market trends, and arbitrage opportunities.

## Tech Stack

- **Backend**: Python FastAPI + SQLAlchemy (async SQLite)
- **Scraping**: httpx + BeautifulSoup4, Playwright (headless)
- **Frontend**: Vanilla HTML/CSS/JS
- **Export**: Excel via openpyxl

## Setup

```bash
# Install dependencies
pip install -r backend/requirements.txt
playwright install chromium

# Run dev server
uvicorn backend.main:app --reload

# Open browser
http://localhost:8000
```

## Features

### Phase 1 (Current): Auction Search
- Search **Bring a Trailer** and **Cars & Bids** for completed auctions
- Filter by make, model, year range, keyword, time period
- View sold prices, bid counts, auction duration
- Export results to Excel with hyperlinks

### Phase 2 (Planned): USA Used Cars
- Autotrader, Cars.com

### Phase 3 (Planned): German Used Cars
- Mobile.de, AutoScout24, Kleinanzeigen

### Phase 4 (Planned): Price Comparison
- Cross-region arbitrage analysis

## API

```
POST /api/v1/auctions/search    - Start auction search job
GET  /api/v1/jobs/{id}          - Check job status
GET  /api/v1/auctions/results/{id} - Get results
GET  /api/v1/export/{id}        - Download Excel
GET  /api/v1/makes              - List makes
GET  /api/v1/models/{make}      - List models
```
