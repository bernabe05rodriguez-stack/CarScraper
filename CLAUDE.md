# CarScraper - CLAUDE.md

## Descripcion
Aplicacion web para investigacion de mercado automotriz. Busca en plataformas de subastas y sitios de autos usados (USA y Alemania) para analisis de precios, time on market, y arbitraje cross-region.

## Tech Stack
- **Backend**: Python 3.12+, FastAPI, SQLAlchemy (async), PostgreSQL
- **Scraping**: httpx + BeautifulSoup4 (BaT, Cars.com, AutoScout24), Playwright (Cars & Bids, Autotrader, Mobile.de, Kleinanzeigen)
- **Frontend**: HTML/CSS/JS vanilla (sin frameworks)
- **Export**: openpyxl para Excel
- **Deploy**: Docker + EasyPanel

## Rutas
- **Repo**: /mnt/c/Users/berna/OneDrive/Documentos/GitHub/CarScraper/
- **Backend**: backend/
- **Frontend**: frontend/ (servido como static files por FastAPI)

## Comandos
```bash
# Desarrollo local con Docker
docker compose up --build

# Acceder
http://localhost:8000

# Sin Docker (necesita PostgreSQL corriendo)
pip install -r backend/requirements.txt
playwright install chromium
uvicorn backend.main:app --reload
```

## Arquitectura
- Scraping corre en background jobs (asyncio tasks)
- Frontend hace polling al job endpoint cada 2s
- Resultados se cachean en PostgreSQL (TTL 6h)
- Scrapers son modulares: cada plataforma tiene su propio archivo
- Scheduler de fondo para recoleccion historica continua
- Comparacion USD/EUR con API de tipo de cambio en tiempo real

## Paginas
- **/** - Landing page con 4 feature cards
- **/auctions** - Busqueda BaT + Cars & Bids (subastas)
- **/usa-used** - Autotrader + Cars.com (autos usados USA)
- **/germany-used** - Mobile.de + AutoScout24 + Kleinanzeigen (autos usados Alemania)
- **/comparison** - Comparacion USA vs Alemania con analisis de arbitraje

## Plataformas
| Plataforma | Tipo | Region | Scraper |
|-----------|------|--------|---------|
| Bring a Trailer | auction | USA | httpx + BS4 |
| Cars & Bids | auction | USA | Playwright |
| Autotrader | used_car | USA | Playwright |
| Cars.com | used_car | USA | httpx + BS4 |
| Mobile.de | used_car | Germany | Playwright |
| AutoScout24 | used_car | Germany | httpx + BS4 |
| Kleinanzeigen | used_car | Germany | Playwright |

## API Endpoints
- POST `/api/v1/auctions/search` - Buscar subastas
- GET `/api/v1/auctions/results/{job_id}` - Resultados subastas
- POST `/api/v1/used-cars/search` - Buscar autos usados
- GET `/api/v1/used-cars/results/{job_id}` - Resultados autos usados
- POST `/api/v1/comparison/analyze` - Comparacion USA vs Germany
- GET `/api/v1/jobs/{job_id}` - Status del job
- GET `/api/v1/export/{job_id}` - Export Excel
- GET `/api/v1/makes` - Lista de marcas
- GET `/api/v1/models/{make}` - Modelos por marca

## Lecciones
- BaT usa WordPress, HTML estatico, scraping facil con httpx+BS4
- Cars & Bids es React SPA, necesita Playwright + interceptar XHR
- Mobile.de y Kleinanzeigen necesitan Playwright + consent handling
- AutoScout24 funciona con httpx+BS4 (server-rendered)
- Usar `playwright-stealth` para evitar deteccion basica
- Rate limiting generoso (3-8s entre requests) para evitar bans
- Cars & Bids: bug is_sold invertido corregido (detectar "not sold"/"bid to" especificamente)
- BaT: cards solo muestran precio final, no starting bid para items vendidos
- PostgreSQL en produccion via Docker, SQLite solo para desarrollo rapido
