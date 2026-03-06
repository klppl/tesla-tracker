# Tesla Price Tracker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a CLI tool that scrapes used Tesla listings from carla.se, stores them in SQLite, and tracks price changes over time.

**Architecture:** Playwright-based scraper visits carla.se (which has Vercel bot protection), extracts listing data, stores in SQLite with price history tracking. Incremental approach: only visits detail pages for new cars; known cars just get price updates from the list page.

**Tech Stack:** Python 3.11+, Playwright, Click, SQLite3 (stdlib)

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `teslatracker/__init__.py`

**Step 1: Create requirements.txt**

```
playwright>=1.40
click>=8.0
```

**Step 2: Create pyproject.toml**

```toml
[project]
name = "teslatracker"
version = "0.1.0"
description = "Used Tesla price tracker for Swedish car sites"
requires-python = ">=3.11"
dependencies = [
    "playwright>=1.40",
    "click>=8.0",
]

[project.scripts]
teslatracker = "teslatracker.cli:cli"
```

**Step 3: Create teslatracker/__init__.py**

Empty file.

**Step 4: Install dependencies**

Run: `python -m venv .venv && source .venv/bin/activate && pip install -e . && playwright install chromium`

Expected: Dependencies install, Chromium downloads.

**Step 5: Commit**

```bash
git add pyproject.toml requirements.txt teslatracker/__init__.py
git commit -m "chore: project scaffolding with dependencies"
```

---

### Task 2: Data models

**Files:**
- Create: `teslatracker/models.py`
- Create: `tests/__init__.py`
- Create: `tests/test_models.py`

**Step 1: Write the failing test**

```python
# tests/test_models.py
from teslatracker.models import Car, PriceRecord
from datetime import datetime


def test_car_creation():
    car = Car(
        id="abc123",
        url="https://www.carla.se/bil/abc123",
        model="Model 3",
        trim="Long Range",
        year=2022,
        mileage_km=35000,
        price_sek=359000,
        color="White",
        battery_kwh=75.0,
        range_km=580,
        location="Stockholm",
        source="carla.se",
    )
    assert car.id == "abc123"
    assert car.model == "Model 3"
    assert car.price_sek == 359000


def test_car_optional_fields():
    car = Car(
        id="xyz",
        url="https://www.carla.se/bil/xyz",
        model="Model Y",
        year=2023,
        mileage_km=10000,
        price_sek=450000,
        source="carla.se",
    )
    assert car.trim is None
    assert car.color is None
    assert car.battery_kwh is None


def test_price_record_creation():
    rec = PriceRecord(
        car_id="abc123",
        price_sek=359000,
        recorded_at=datetime(2026, 3, 6, 12, 0, 0),
    )
    assert rec.car_id == "abc123"
    assert rec.price_sek == 359000
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL — cannot import Car, PriceRecord

**Step 3: Write minimal implementation**

```python
# teslatracker/models.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Car:
    id: str
    url: str
    model: str
    year: int
    mileage_km: int
    price_sek: int
    source: str
    trim: Optional[str] = None
    color: Optional[str] = None
    battery_kwh: Optional[float] = None
    range_km: Optional[int] = None
    location: Optional[str] = None
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    removed: bool = False


@dataclass
class PriceRecord:
    car_id: str
    price_sek: int
    recorded_at: datetime = field(default_factory=datetime.now)
    id: Optional[int] = None
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add teslatracker/models.py tests/
git commit -m "feat: add Car and PriceRecord data models"
```

---

### Task 3: Database layer

**Files:**
- Create: `teslatracker/db.py`
- Create: `tests/test_db.py`

**Step 1: Write the failing tests**

```python
# tests/test_db.py
import os
import tempfile
from datetime import datetime

from teslatracker.db import Database
from teslatracker.models import Car


def make_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return Database(path), path


def make_car(**overrides):
    defaults = dict(
        id="abc123",
        url="https://www.carla.se/bil/abc123",
        model="Model 3",
        trim="Long Range",
        year=2022,
        mileage_km=35000,
        price_sek=359000,
        source="carla.se",
    )
    defaults.update(overrides)
    return Car(**defaults)


def test_init_creates_tables():
    db, path = make_db()
    try:
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {row[0] for row in tables}
        assert "cars" in names
        assert "price_history" in names
    finally:
        os.unlink(path)


def test_upsert_car_insert():
    db, path = make_db()
    try:
        car = make_car()
        db.upsert_car(car)
        row = db.get_car("abc123")
        assert row is not None
        assert row.model == "Model 3"
        assert row.price_sek == 359000
    finally:
        os.unlink(path)


def test_upsert_car_update_last_seen():
    db, path = make_db()
    try:
        car = make_car()
        db.upsert_car(car)
        first = db.get_car("abc123")

        car.last_seen = datetime(2026, 3, 7)
        db.upsert_car(car)
        updated = db.get_car("abc123")
        assert updated.last_seen > first.first_seen
    finally:
        os.unlink(path)


def test_record_price():
    db, path = make_db()
    try:
        car = make_car()
        db.upsert_car(car)
        db.record_price("abc123", 359000)
        db.record_price("abc123", 359000)  # same price, should not duplicate
        db.record_price("abc123", 349000)  # new price

        history = db.get_price_history("abc123")
        assert len(history) == 2  # only 2 distinct prices
        assert history[0].price_sek == 359000
        assert history[1].price_sek == 349000
    finally:
        os.unlink(path)


def test_list_cars():
    db, path = make_db()
    try:
        db.upsert_car(make_car(id="a", model="Model 3", price_sek=300000))
        db.upsert_car(make_car(id="b", model="Model Y", price_sek=400000))
        db.upsert_car(make_car(id="c", model="Model 3", price_sek=250000))

        all_cars = db.list_cars()
        assert len(all_cars) == 3

        m3_only = db.list_cars(model="Model 3")
        assert len(m3_only) == 2

        cheap = db.list_cars(max_price=310000)
        assert len(cheap) == 2
    finally:
        os.unlink(path)


def test_get_new_cars_since():
    db, path = make_db()
    try:
        old = make_car(id="old")
        old.first_seen = datetime(2026, 3, 1)
        db.upsert_car(old)

        new = make_car(id="new")
        new.first_seen = datetime(2026, 3, 6)
        db.upsert_car(new)

        since = datetime(2026, 3, 5)
        result = db.get_new_cars_since(since)
        assert len(result) == 1
        assert result[0].id == "new"
    finally:
        os.unlink(path)
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL — cannot import Database

**Step 3: Write implementation**

```python
# teslatracker/db.py
import sqlite3
from datetime import datetime
from typing import Optional

from teslatracker.models import Car, PriceRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS cars (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    model TEXT NOT NULL,
    trim TEXT,
    year INTEGER NOT NULL,
    mileage_km INTEGER NOT NULL,
    color TEXT,
    battery_kwh REAL,
    range_km INTEGER,
    location TEXT,
    first_seen TIMESTAMP NOT NULL,
    last_seen TIMESTAMP NOT NULL,
    removed BOOLEAN NOT NULL DEFAULT 0,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id TEXT NOT NULL REFERENCES cars(id),
    price_sek INTEGER NOT NULL,
    recorded_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_price_history_car_id ON price_history(car_id);
CREATE INDEX IF NOT EXISTS idx_cars_model ON cars(model);
CREATE INDEX IF NOT EXISTS idx_cars_source ON cars(source);
"""


class Database:
    def __init__(self, db_path: str = "teslatracker.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA)

    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def upsert_car(self, car: Car):
        self.conn.execute(
            """INSERT INTO cars (id, url, model, trim, year, mileage_km, color,
               battery_kwh, range_km, location, first_seen, last_seen, removed, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
               last_seen = excluded.last_seen,
               removed = 0,
               mileage_km = excluded.mileage_km
            """,
            (car.id, car.url, car.model, car.trim, car.year, car.mileage_km,
             car.color, car.battery_kwh, car.range_km, car.location,
             car.first_seen.isoformat(), car.last_seen.isoformat(),
             car.removed, car.source),
        )
        self.conn.commit()

    def get_car(self, car_id: str) -> Optional[Car]:
        row = self.conn.execute("SELECT * FROM cars WHERE id = ?", (car_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_car(row)

    def record_price(self, car_id: str, price_sek: int):
        last = self.conn.execute(
            "SELECT price_sek FROM price_history WHERE car_id = ? ORDER BY recorded_at DESC LIMIT 1",
            (car_id,),
        ).fetchone()
        if last and last["price_sek"] == price_sek:
            return  # no change
        self.conn.execute(
            "INSERT INTO price_history (car_id, price_sek, recorded_at) VALUES (?, ?, ?)",
            (car_id, price_sek, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_price_history(self, car_id: str) -> list[PriceRecord]:
        rows = self.conn.execute(
            "SELECT * FROM price_history WHERE car_id = ? ORDER BY recorded_at",
            (car_id,),
        ).fetchall()
        return [
            PriceRecord(
                id=r["id"],
                car_id=r["car_id"],
                price_sek=r["price_sek"],
                recorded_at=datetime.fromisoformat(r["recorded_at"]),
            )
            for r in rows
        ]

    def list_cars(
        self,
        model: Optional[str] = None,
        max_price: Optional[int] = None,
        sort_by: str = "first_seen",
    ) -> list[Car]:
        query = "SELECT c.*, ph.price_sek FROM cars c LEFT JOIN price_history ph ON c.id = ph.car_id AND ph.id = (SELECT MAX(id) FROM price_history WHERE car_id = c.id) WHERE 1=1"
        params: list = []
        if model:
            query += " AND c.model LIKE ?"
            params.append(f"%{model}%")
        if max_price is not None:
            query += " AND ph.price_sek <= ?"
            params.append(max_price)
        valid_sorts = {"first_seen": "c.first_seen", "price": "ph.price_sek", "mileage": "c.mileage_km", "year": "c.year"}
        order = valid_sorts.get(sort_by, "c.first_seen")
        query += f" ORDER BY {order} DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_car(r) for r in rows]

    def get_new_cars_since(self, since: datetime) -> list[Car]:
        rows = self.conn.execute(
            "SELECT * FROM cars WHERE first_seen > ? ORDER BY first_seen DESC",
            (since.isoformat(),),
        ).fetchall()
        return [self._row_to_car(r) for r in rows]

    def mark_unseen_as_removed(self, seen_ids: set[str], source: str):
        if not seen_ids:
            return
        placeholders = ",".join("?" for _ in seen_ids)
        self.conn.execute(
            f"UPDATE cars SET removed = 1 WHERE source = ? AND id NOT IN ({placeholders})",
            [source] + list(seen_ids),
        )
        self.conn.commit()

    def _row_to_car(self, row: sqlite3.Row) -> Car:
        return Car(
            id=row["id"],
            url=row["url"],
            model=row["model"],
            trim=row["trim"],
            year=row["year"],
            mileage_km=row["mileage_km"],
            price_sek=row["price_sek"] if "price_sek" in row.keys() else 0,
            color=row["color"],
            battery_kwh=row["battery_kwh"],
            range_km=row["range_km"],
            location=row["location"],
            first_seen=datetime.fromisoformat(row["first_seen"]),
            last_seen=datetime.fromisoformat(row["last_seen"]),
            removed=bool(row["removed"]),
            source=row["source"],
        )
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db.py -v`
Expected: 6 passed

**Step 5: Commit**

```bash
git add teslatracker/db.py tests/test_db.py
git commit -m "feat: add SQLite database layer with price tracking"
```

---

### Task 4: DOM discovery — inspect carla.se with Playwright

**Files:**
- Create: `scripts/inspect_dom.py`

This is NOT a TDD task. This is a discovery step to determine the actual HTML structure and CSS selectors on carla.se. The script saves the page HTML and prints the DOM structure of listing cards.

**Step 1: Write the inspection script**

```python
# scripts/inspect_dom.py
"""
Run this script to inspect the carla.se DOM structure.
It saves screenshots and prints the HTML of listing elements
so we can determine the right CSS selectors for the parser.
"""
import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # visible for debugging
        page = await browser.new_page()

        print("Navigating to carla.se...")
        await page.goto(
            "https://www.carla.se/kopa-bil?manufacturer=Tesla&sort=created_at%3Adesc",
            wait_until="networkidle",
            timeout=30000,
        )

        await page.screenshot(path="debug_listing_page.png", full_page=True)
        print("Screenshot saved: debug_listing_page.png")

        # Save full HTML
        html = await page.content()
        with open("debug_listing_page.html", "w") as f:
            f.write(html)
        print("HTML saved: debug_listing_page.html")

        # Try common listing card selectors
        candidates = [
            "a[href*='/bil/']",
            "[data-testid*='car']",
            "[data-testid*='listing']",
            "[class*='listing']",
            "[class*='card']",
            "[class*='vehicle']",
            "article",
        ]
        for sel in candidates:
            count = await page.locator(sel).count()
            if count > 0:
                print(f"\n--- Selector: {sel} — {count} matches ---")
                first = page.locator(sel).first
                inner = await first.inner_html()
                text = await first.inner_text()
                print(f"Text: {text[:300]}")
                print(f"HTML: {inner[:500]}")

        # Also check for Next.js data
        next_data = await page.query_selector("script#__NEXT_DATA__")
        if next_data:
            content = await next_data.inner_text()
            print(f"\n--- __NEXT_DATA__ found ({len(content)} chars) ---")
            print(content[:1000])

        # Check network requests for API calls
        print("\n--- Checking for XHR/fetch API calls ---")
        # Navigate again with request interception
        api_urls = []

        async def log_request(request):
            if "api" in request.url.lower() or "graphql" in request.url.lower():
                api_urls.append(request.url)

        page.on("request", log_request)
        await page.reload(wait_until="networkidle")

        for url in api_urls:
            print(f"API call: {url}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 2: Run it**

Run: `source .venv/bin/activate && python scripts/inspect_dom.py`

Expected: Screenshots, HTML dump, and selector matches printed. Use output to fill in the real selectors in Task 5.

**Step 3: Examine the output**

Look at `debug_listing_page.png` and the printed selectors. Note:
- Which selector matches listing cards
- What data is visible on each card (model, price, mileage, year)
- The URL pattern for detail pages
- Any API endpoints discovered

**Step 4: Commit the inspection script**

```bash
git add scripts/inspect_dom.py
echo "debug_*" >> .gitignore
git add .gitignore
git commit -m "chore: add DOM inspection script for carla.se"
```

---

### Task 5: Parser — extract car data from HTML

**Files:**
- Create: `teslatracker/parser.py`
- Create: `tests/test_parser.py`
- Create: `tests/fixtures/` (sample HTML snippets)

**Important:** This task depends on Task 4's output. The CSS selectors and HTML structure below are placeholders. Replace them with the actual selectors discovered in Task 4.

**Step 1: Save sample HTML from Task 4 as test fixtures**

Save a listing card HTML snippet to `tests/fixtures/listing_card.html` and a detail page snippet to `tests/fixtures/detail_page.html`. These come from the debug output of Task 4.

**Step 2: Write the failing tests**

```python
# tests/test_parser.py
from pathlib import Path
from teslatracker.parser import parse_listing_cards, parse_detail_page

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_listing_cards():
    html = (FIXTURES / "listing_card.html").read_text()
    cards = parse_listing_cards(html)
    assert len(cards) >= 1
    card = cards[0]
    assert card["id"]  # has a listing ID
    assert card["model"]  # has a model name
    assert card["price_sek"] > 0
    assert card["url"].startswith("http")


def test_parse_detail_page():
    html = (FIXTURES / "detail_page.html").read_text()
    details = parse_detail_page(html)
    # Should extract extended fields
    assert "year" in details
    assert "mileage_km" in details
```

**Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_parser.py -v`
Expected: FAIL

**Step 4: Implement parser based on discovered selectors**

```python
# teslatracker/parser.py
"""
Parses carla.se listing HTML into structured data.

CSS selectors here are determined by running scripts/inspect_dom.py.
If carla.se changes their HTML, update the selectors here.
"""
import re
from html.parser import HTMLParser


def parse_listing_cards(html: str) -> list[dict]:
    """Parse the search results page HTML and extract listing card data.

    Returns list of dicts with keys: id, url, model, price_sek, mileage_km, year.
    Selectors must be updated based on inspect_dom.py output.
    """
    # PLACEHOLDER: Replace with actual extraction logic from Task 4
    # This will use string/regex parsing on the raw HTML or
    # a lightweight HTML parser to avoid extra dependencies
    cards = []
    # TODO: implement after DOM inspection
    return cards


def parse_detail_page(html: str) -> dict:
    """Parse a single car detail page for extended fields.

    Returns dict with keys: trim, color, battery_kwh, range_km, location.
    """
    details = {}
    # TODO: implement after DOM inspection
    return details


def _extract_price(text: str) -> int:
    """Extract price in SEK from text like '359 000 kr' or '359000'."""
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0


def _extract_mileage(text: str) -> int:
    """Extract mileage in km from text like '35 000 km' or 'mil: 3.5'."""
    # Handle 'mil' (Scandinavian miles, 1 mil = 10 km)
    mil_match = re.search(r"([\d\s,\.]+)\s*mil", text, re.IGNORECASE)
    if mil_match:
        mil_str = mil_match.group(1).replace(" ", "").replace(",", ".")
        return int(float(mil_str) * 10)

    # Handle km
    km_match = re.search(r"([\d\s]+)\s*km", text, re.IGNORECASE)
    if km_match:
        return int(km_match.group(1).replace(" ", ""))
    return 0
```

**Step 5: Run tests**

Run: `python -m pytest tests/test_parser.py -v`
Expected: Tests pass once real selectors are added

**Step 6: Commit**

```bash
git add teslatracker/parser.py tests/test_parser.py tests/fixtures/
git commit -m "feat: add HTML parser for carla.se listings"
```

---

### Task 6: Scraper — Playwright automation

**Files:**
- Create: `teslatracker/scraper.py`

This is the Playwright automation layer. It does NOT have unit tests — it's integration-level code that talks to the real site. We test it by running it.

**Step 1: Write the scraper**

```python
# teslatracker/scraper.py
import asyncio
import random
from datetime import datetime

from playwright.async_api import async_playwright, Page

from teslatracker.db import Database
from teslatracker.models import Car
from teslatracker.parser import parse_listing_cards, parse_detail_page

BASE_URL = "https://www.carla.se"
SEARCH_URL = f"{BASE_URL}/kopa-bil?manufacturer=Tesla&sort=created_at%3Adesc"
SOURCE = "carla.se"


async def scrape(db: Database, max_pages: int = 5, headless: bool = True):
    """Run the full scrape cycle."""
    stats = {"new": 0, "price_changes": 0, "seen": 0}
    seen_ids: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()

        print(f"Navigating to {SEARCH_URL}")
        await page.goto(SEARCH_URL, wait_until="networkidle", timeout=30000)

        for page_num in range(1, max_pages + 1):
            print(f"Scraping page {page_num}...")
            html = await page.content()
            cards = parse_listing_cards(html)

            if not cards:
                print("No more listings found.")
                break

            for card in cards:
                car_id = card["id"]
                seen_ids.add(car_id)
                stats["seen"] += 1

                existing = db.get_car(car_id)
                if existing:
                    # Known car — just update price
                    db.upsert_car(Car(
                        id=car_id,
                        url=card["url"],
                        model=existing.model,
                        year=existing.year,
                        mileage_km=card.get("mileage_km", existing.mileage_km),
                        price_sek=card["price_sek"],
                        source=SOURCE,
                        trim=existing.trim,
                        color=existing.color,
                        battery_kwh=existing.battery_kwh,
                        range_km=existing.range_km,
                        location=existing.location,
                        first_seen=existing.first_seen,
                        last_seen=datetime.now(),
                    ))
                    old_price = db.get_price_history(car_id)
                    db.record_price(car_id, card["price_sek"])
                    new_history = db.get_price_history(car_id)
                    if len(new_history) > len(old_price):
                        stats["price_changes"] += 1
                        print(f"  Price change: {existing.model} {old_price[-1].price_sek} -> {card['price_sek']} SEK")
                else:
                    # New car — visit detail page
                    print(f"  New: {card.get('model', 'Unknown')} — visiting detail page...")
                    await _random_delay()
                    detail = await _fetch_detail(page, card["url"])

                    car = Car(
                        id=car_id,
                        url=card["url"],
                        model=card.get("model", "Unknown"),
                        year=detail.get("year", card.get("year", 0)),
                        mileage_km=detail.get("mileage_km", card.get("mileage_km", 0)),
                        price_sek=card["price_sek"],
                        source=SOURCE,
                        trim=detail.get("trim"),
                        color=detail.get("color"),
                        battery_kwh=detail.get("battery_kwh"),
                        range_km=detail.get("range_km"),
                        location=detail.get("location"),
                    )
                    db.upsert_car(car)
                    db.record_price(car_id, card["price_sek"])
                    stats["new"] += 1

            # Try to paginate
            has_next = await _go_next_page(page)
            if not has_next:
                break
            await _random_delay()

        db.mark_unseen_as_removed(seen_ids, SOURCE)
        await browser.close()

    print(f"\nDone! Seen: {stats['seen']}, New: {stats['new']}, Price changes: {stats['price_changes']}")
    return stats


async def _fetch_detail(page: Page, url: str) -> dict:
    """Navigate to detail page, extract extended fields, navigate back."""
    try:
        await page.goto(url, wait_until="networkidle", timeout=20000)
        html = await page.content()
        detail = parse_detail_page(html)
        await page.go_back(wait_until="networkidle", timeout=20000)
        return detail
    except Exception as e:
        print(f"    Warning: could not fetch detail page: {e}")
        return {}


async def _go_next_page(page: Page) -> bool:
    """Click the next page button. Returns False if no next page."""
    # PLACEHOLDER: selector depends on Task 4 discovery
    try:
        next_btn = page.locator("button:has-text('Nästa'), a:has-text('Nästa'), [aria-label='Next']")
        if await next_btn.count() > 0 and await next_btn.first.is_enabled():
            await next_btn.first.click()
            await page.wait_for_load_state("networkidle", timeout=15000)
            return True
    except Exception:
        pass
    return False


async def _random_delay():
    """Wait 2-5 seconds between requests."""
    delay = random.uniform(2, 5)
    await asyncio.sleep(delay)
```

**Step 2: Commit**

```bash
git add teslatracker/scraper.py
git commit -m "feat: add Playwright scraper with incremental logic"
```

---

### Task 7: CLI

**Files:**
- Create: `teslatracker/cli.py`
- Create: `tests/test_cli.py`

**Step 1: Write failing test**

```python
# tests/test_cli.py
from click.testing import CliRunner
from teslatracker.cli import cli


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "scrape" in result.output
    assert "list" in result.output


def test_cli_stats_empty_db(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["stats", "--db", str(tmp_path / "test.db")])
    assert result.exit_code == 0
    assert "0" in result.output  # zero cars
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL

**Step 3: Implement CLI**

```python
# teslatracker/cli.py
import asyncio
from datetime import datetime, timedelta

import click

from teslatracker.db import Database


@click.group()
def cli():
    """Tesla price tracker — track used Tesla listings from Swedish car sites."""
    pass


@cli.command()
@click.option("--db", default="teslatracker.db", help="Database path")
@click.option("--max-pages", default=5, help="Max search pages to scrape")
@click.option("--full", is_flag=True, help="Scrape all pages (no limit)")
@click.option("--visible", is_flag=True, help="Show browser window")
def scrape(db, max_pages, full, visible):
    """Scrape carla.se for Tesla listings."""
    from teslatracker.scraper import scrape as run_scrape

    database = Database(db)
    pages = 999 if full else max_pages
    asyncio.run(run_scrape(database, max_pages=pages, headless=not visible))


@cli.command("list")
@click.option("--db", default="teslatracker.db", help="Database path")
@click.option("--model", default=None, help="Filter by model (e.g. 'Model 3')")
@click.option("--max-price", default=None, type=int, help="Max price in SEK")
@click.option("--sort", "sort_by", default="first_seen", type=click.Choice(["price", "mileage", "year", "first_seen"]))
def list_cars(db, model, max_price, sort_by):
    """List tracked cars."""
    database = Database(db)
    cars = database.list_cars(model=model, max_price=max_price, sort_by=sort_by)
    if not cars:
        click.echo("No cars found.")
        return
    click.echo(f"{'Model':<20} {'Year':<6} {'Mileage':<10} {'Price':<12} {'Location':<15} {'First seen':<12}")
    click.echo("-" * 85)
    for car in cars:
        history = database.get_price_history(car.id)
        price = f"{history[-1].price_sek:,} kr" if history else "N/A"
        click.echo(
            f"{car.model + (' ' + car.trim if car.trim else ''):<20} "
            f"{car.year:<6} "
            f"{car.mileage_km:>7,} km "
            f"{price:>12} "
            f"{(car.location or 'N/A'):<15} "
            f"{car.first_seen.strftime('%Y-%m-%d'):<12}"
        )


@cli.command()
@click.option("--db", default="teslatracker.db", help="Database path")
@click.argument("car_id")
def history(db, car_id):
    """Show price history for a car."""
    database = Database(db)
    car = database.get_car(car_id)
    if not car:
        click.echo(f"Car '{car_id}' not found.")
        return
    click.echo(f"Price history for {car.model} ({car.year}) — {car.url}")
    records = database.get_price_history(car_id)
    for rec in records:
        click.echo(f"  {rec.recorded_at.strftime('%Y-%m-%d %H:%M')}  {rec.price_sek:>10,} kr")


@cli.command()
@click.option("--db", default="teslatracker.db", help="Database path")
@click.option("--days", default=1, help="Show cars added in last N days")
def new(db, days):
    """Show recently added cars."""
    database = Database(db)
    since = datetime.now() - timedelta(days=days)
    cars = database.get_new_cars_since(since)
    if not cars:
        click.echo(f"No new cars in the last {days} day(s).")
        return
    click.echo(f"New cars since {since.strftime('%Y-%m-%d')}:")
    for car in cars:
        history = database.get_price_history(car.id)
        price = f"{history[-1].price_sek:,} kr" if history else "N/A"
        click.echo(f"  {car.model} ({car.year}) — {price} — {car.mileage_km:,} km — {car.url}")


@cli.command()
@click.option("--db", default="teslatracker.db", help="Database path")
def stats(db):
    """Show summary statistics."""
    database = Database(db)
    cars = database.list_cars()
    click.echo(f"Total cars tracked: {len(cars)}")
    if not cars:
        return
    models: dict[str, list] = {}
    for car in cars:
        models.setdefault(car.model, []).append(car)
    click.echo(f"\nBy model:")
    for model, group in sorted(models.items()):
        histories = [database.get_price_history(c.id) for c in group]
        prices = [h[-1].price_sek for h in histories if h]
        avg_price = sum(prices) // len(prices) if prices else 0
        click.echo(f"  {model}: {len(group)} cars, avg {avg_price:,} kr")


if __name__ == "__main__":
    cli()
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_cli.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add teslatracker/cli.py tests/test_cli.py
git commit -m "feat: add Click CLI with scrape, list, history, new, stats commands"
```

---

### Task 8: First real scrape — integration test

**Step 1: Run the DOM inspector to discover selectors**

Run: `source .venv/bin/activate && python scripts/inspect_dom.py`

Examine output, update `teslatracker/parser.py` with real CSS selectors.

**Step 2: Run scrape with visible browser**

Run: `python -m teslatracker.cli scrape --visible --max-pages 1`

Watch the browser, verify it loads the page and extracts listings.

**Step 3: Check the database**

Run: `python -m teslatracker.cli stats`
Run: `python -m teslatracker.cli list`

Verify data looks correct.

**Step 4: Commit parser updates**

```bash
git add teslatracker/parser.py
git commit -m "feat: update parser with real carla.se selectors"
```

---

### Task 9: Add .gitignore and final cleanup

**Files:**
- Create/update: `.gitignore`

**Step 1: Write .gitignore**

```
.venv/
__pycache__/
*.pyc
*.db
debug_*
.eggs/
*.egg-info/
dist/
build/
```

**Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: add .gitignore"
```
