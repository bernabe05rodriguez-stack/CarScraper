# CarScraper - CLAUDE.md

## Descripcion
Aplicacion web para investigacion de mercado automotriz. Busca en plataformas de subastas y sitios de autos usados para analisis de precios y arbitraje.

## Tech Stack
- **Backend**: Python 3.12+, FastAPI, SQLAlchemy (async), SQLite
- **Scraping**: httpx + BeautifulSoup4 (BaT), Playwright (Cars & Bids)
- **Frontend**: HTML/CSS/JS vanilla (sin frameworks)
- **Export**: openpyxl para Excel

## Rutas
- **Repo**: /mnt/c/Users/berna/OneDrive/Documentos/GitHub/CarScraper/
- **Backend**: backend/
- **Frontend**: frontend/ (servido como static files por FastAPI)

## Comandos
```bash
# Instalar dependencias
pip install -r backend/requirements.txt
playwright install chromium

# Ejecutar dev server
cd /mnt/c/Users/berna/OneDrive/Documentos/GitHub/CarScraper
uvicorn backend.main:app --reload

# Acceder
http://localhost:8000
```

## Arquitectura
- Scraping corre en background jobs (asyncio tasks)
- Frontend hace polling al job endpoint cada 2s
- Resultados se cachean en SQLite (TTL 6h)
- Scrapers son modulares: cada plataforma tiene su propio archivo

## Fases
- **Fase 1 (MVP)**: Subastas - BaT + Cars & Bids
- **Fase 2**: USA Used Cars - Autotrader + Cars.com
- **Fase 3**: German Sites - Mobile.de + AutoScout24 + Kleinanzeigen
- **Fase 4**: Comparacion/Arbitraje cross-region

## Lecciones
- BaT usa WordPress, HTML estatico, scraping facil con httpx+BS4
- Cars & Bids es React SPA, necesita Playwright + interceptar XHR
- Usar `playwright-stealth` para evitar deteccion basica
- Rate limiting generoso (5-10s entre requests) para evitar bans
