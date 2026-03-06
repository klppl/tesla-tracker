# Tesla Price Tracker — Design

## Purpose

Track used Tesla car listings from Swedish car sites, starting with carla.se. Detect new listings daily, store model details and mileage, and track price changes over time.

## Architecture

- **Python** with **Playwright** for browser-based scraping (carla.se is behind Vercel bot protection)
- **SQLite** for local storage
- **Click**-based CLI for running scrapes and querying data

### Components

- `scraper.py` — Playwright automation. Loads search page, paginates, extracts listing cards. Visits detail pages for new cars only.
- `parser.py` — Extracts structured data from HTML elements. Separated from scraper for maintainability when site changes.
- `db.py` — SQLite schema, insert/update/query functions.
- `models.py` — Dataclasses for Car, PriceRecord.
- `cli.py` — CLI commands: `scrape`, `list`, `new`, `history`, `stats`.

## Data Model

### `cars` table

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | Carla listing ID (from URL) |
| url | TEXT | Full listing URL |
| model | TEXT | e.g. "Model 3", "Model Y" |
| trim | TEXT | e.g. "Long Range", "Performance" |
| year | INTEGER | Model year |
| mileage_km | INTEGER | Kilometers driven |
| color | TEXT | Exterior color |
| battery_kwh | REAL | Battery capacity if available |
| range_km | INTEGER | Stated range if available |
| location | TEXT | Seller location |
| first_seen | DATETIME | When we first scraped it |
| last_seen | DATETIME | Last time it appeared in search |
| removed | BOOLEAN | Disappeared from listings (sold?) |
| source | TEXT | "carla.se" — extensible for future sources |

### `price_history` table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| car_id | TEXT FK | References cars.id |
| price_sek | INTEGER | Price in SEK |
| recorded_at | DATETIME | When this price was seen |

Price is recorded each run. New row only added when price differs from the most recent record.

## Scraper Flow (Incremental Hybrid — Approach 3)

1. Launch Playwright headless Chromium
2. Navigate to `carla.se/kopa-bil?manufacturer=Tesla&sort=created_at:desc`
3. Wait for listings to render
4. For each page of results (default limit: 5 pages):
   - Extract listing cards: id, model, price, mileage, year
   - Known car → record price in price_history, update last_seen
   - New car → visit detail page, extract extended fields, insert car + price
   - Paginate until no more results or page limit reached
5. Mark cars not seen in this run as potentially removed
6. Print summary: X new, Y price changes, Z removed

### Scraping behavior
- Random delays (2-5s) between requests
- Retry logic for transient failures
- `--full` flag to scrape all pages
- CSS selectors determined by inspecting live DOM via Playwright

## CLI Commands

- `python cli.py scrape` — Run the scraper
- `python cli.py list [--model X] [--max-price N] [--sort price|mileage|year]` — Browse cars
- `python cli.py history <car_id>` — Price history for a car
- `python cli.py new` — Cars added since last run
- `python cli.py stats` — Count by model, avg price, etc.

## Project Structure

```
teslatracker/
├── teslatracker/
│   ├── __init__.py
│   ├── scraper.py
│   ├── parser.py
│   ├── db.py
│   ├── models.py
│   └── cli.py
├── docs/plans/
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Dependencies

- `playwright` — headless browser
- `click` — CLI framework
- `sqlite3` — standard library

## Future Extensibility

- Add more sources (blocket.se, bytbil.se, etc.) via source-specific parser modules
- Web dashboard (Streamlit/Flask) for browsing and charts
- Notifications (email/Slack) for new listings matching criteria
- Price trend charts
