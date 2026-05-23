# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tesla Tracker is a Swedish-language dashboard for tracking used Tesla prices across Swedish car listing sites. It scrapes data from multiple sources, stores it in SQLite, and serves an interactive Chart.js dashboard via Flask (or as a static HTML file).

All UI text is in Swedish.

## Commands

```bash
# Setup
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Fetch the live database (it lives on the 'data' branch, not main)
git show origin/data:tesla_cars.db > tesla_cars.db

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
- **`scrapers/wayke.py`** – Scrapes Wayke.se via internal search API (`/api/search/vehicles`). Mileage: the `mileage` field is always in Scandinavian mil. Uses `odometerReading.value` when `unit == "Kilometer"`, otherwise `mileage * 10`, to store km.
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

`.github/workflows/scrape-and-build.yml` runs daily at 06:00 UTC:

1. **Restore** `tesla_cars.db` from the `data` branch (see below).
2. **Scrape** all sources.
3. **Verify** DB integrity (`PRAGMA integrity_check` + non-zero car count); the job aborts if the scrape produced a corrupt/empty DB, so the last good copy survives.
4. **Generate** the static site and append a build log.
5. **Commit** `public/` (the deployed artifact + `log.txt`) to `main`.
6. **Persist** the DB to the `data` branch.

Cloudflare Pages serves the static `public/` directory from `main` and never reads the database.

### The `data` branch (database storage)

`tesla_cars.db` is **not** tracked on `main`. It lives on a dedicated `data` branch as a *single, force-pushed commit* that is overwritten every run, so daily DB churn never accumulates in git history. The database's own tables (`price_snapshots`, `first_seen`, `removed_at`) are the durable time-series — git only needs the latest file.

- Get the live DB locally: `git show origin/data:tesla_cars.db > tesla_cars.db`
- The `data` branch has no meaningful git history by design; do not expect to roll the DB back through it. Recovery from a bad write is prevented up front by the integrity-check step.

## Key Conventions

- Mileage is stored in **km** in the database but displayed in **mil** (÷10) in the UI
- Prices are in **SEK**
- Car URLs: Carla uses `/bil/{objectID}`, Wayke uses `/objekt/{_id}`
- The `source` field on each car identifies which scraper it came from (e.g. `"carla.se"`, `"wayke.se"`)

## Chart.js Frontend – Known Pitfalls

The dashboard template (`templates/index.html`) is a single large file with ~10 Chart.js charts. These rules exist because of bugs that were hard to track down:

- **No `defer` on Chart.js script tags.** Use synchronous `<script src="...">` in `<head>`. `defer` caused race conditions where `Chart` was undefined at init time.
- **No chartjs-plugin-zoom.** The zoom plugin registers globally and intercepts scroll/wheel events on ALL canvases, breaking page scrolling and filter buttons. It was removed entirely.
- **Clone data points with `{...pt}`.** Chart.js mutates data objects internally (adds `$context` etc). If scatter-all and per-model charts share the same point objects, updating one chart corrupts the other. Always spread-clone in `buildDatasets` and `buildModelScatterDatasets`.
- **No lazy loading (IntersectionObserver) for charts.** Lazy init caused charts to not render and broke filter buttons after scrolling. All charts initialize eagerly on `DOMContentLoaded`.
- **No `Chart.defaults.events` override.** Changing the global events array broke tooltips and interactions across all charts.
- **No `onHover` callbacks on charts.** Custom `onHover` handlers interfered with Chart.js internal event processing, breaking filter buttons.
- **Keep chart configs simple.** Avoid `onZoomComplete`, `onPanComplete`, or any callback that calls `chart.resetZoom()` — it causes infinite recursion.

### Rollback

A known stable version is tagged `VERY-WORKING-VERSION`. To restore the dashboard:

```bash
git checkout VERY-WORKING-VERSION -- templates/index.html public/index.html
```
