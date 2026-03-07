# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tesla Tracker is a Swedish-language dashboard for tracking used Tesla prices across Swedish car listing sites. It scrapes data from multiple sources, stores it in SQLite, and serves an interactive Chart.js dashboard via Flask (or as a static HTML file).

All UI text is in Swedish.

## Commands

```bash
# Setup
uv venv && source .venv/bin/activate
uv pip install flask requests

# Run scraper (fetches all Tesla listings, saves to tesla_cars.db)
uv run scraper.py

# Start local dev server on :5000
uv run app.py --server

# Generate static site to public/index.html
uv run app.py --static
```

There are no tests or linting configured.

## Architecture

### Data Flow

`scrapers/*.py` → `scraper.py` (orchestrator) → `database.py` (SQLite) → `app.py` (analytics queries) → `templates/index.html` (Chart.js)

### Scraper System

Modular scraper architecture in `scrapers/`:

- **`scrapers/base.py`** – `BaseScraper` base class defining the common car dict format (id, model, version, year, price, mileage in km, color, towbar, winter_wheels, battery_range, source, etc.)
- **`scrapers/carla.py`** – Scrapes Carla.se via Algolia API. Paginates with offset/length.
- **`scrapers/wayke.py`** – Scrapes Wayke.se via internal search API (`/api/search/vehicles`). Mileage conversion: if `odometerReading.unit == "ScandinavianMile"`, multiply by 10 to get km.
- **`scrapers/__init__.py`** – Registry: `ALL_SCRAPERS` list of instantiated scrapers.

To add a new scraper: create a class extending `BaseScraper`, implement `fetch() -> list[dict]` returning the common car format, and register it in `ALL_SCRAPERS`.

All scrapers use 1.5s delay between paginated requests and retry with exponential backoff on HTTP 429.

### Orchestrator (`scraper.py`)

Runs all registered scrapers, calls `save_cars_to_db()` for upserts, `mark_removed_cars()` to flag listings no longer seen, and `save_price_snapshot()` for daily aggregate stats.

### Database (`database.py`)

SQLite with two tables:
- **`cars`** – Individual listings. `status` is `'active'` or `'removed'`. Uses `id` (listing ID or reg number) as primary key.
- **`price_snapshots`** – Daily aggregates per model (avg/median price, count). Composite PK: `(date, model)`.

Schema migrations use `ALTER TABLE ADD COLUMN` wrapped in try/except for backwards compatibility.

### Dashboard (`app.py`)

`get_analytics_data()` builds a single `analytics` dict with keys: summary, averages, scatter, scatter_all, daily_additions, price_trends, market_stats, equipment_value, color_stats, depreciation, listing_timing, price_prediction. This dict is passed to the Jinja2 template.

The template (`templates/index.html`) is a single-page dashboard using Chart.js. It includes a "golden car" detector using linear regression (price ~ year + mileage, largest negative residual = best deal). Mileage is displayed in Swedish "mil" (1 mil = 10 km) throughout the UI.

### CI/CD

`.github/workflows/scrape-and-build.yml` runs daily at 06:00 UTC: scrapes, generates static site, commits `tesla_cars.db` + `public/` back to the repo. Hosted via Cloudflare Pages pointing at `public/`.

## Key Conventions

- Mileage is stored in **km** in the database but displayed in **mil** (÷10) in the UI
- Prices are in **SEK**
- Car URLs: Carla uses `/bil/{objectID}`, Wayke uses `/objekt/{_id}`
- The `source` field on each car identifies which scraper it came from (e.g. `"carla.se"`, `"wayke.se"`)
