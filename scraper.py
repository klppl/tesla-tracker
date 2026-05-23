from datetime import datetime, timezone
from database import get_connection, init_db
from scrapers import ALL_SCRAPERS


def save_cars_to_db(cars):
    conn = get_connection()
    cursor = conn.cursor()

    new_cars_added = 0
    updated_cars = 0
    # When the tracker first sees a listing, in UTC to stay consistent with
    # date('now') (UTC) used elsewhere for removal/window comparisons.
    now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

    for car in cars:
        car_id = car["id"]
        source = car.get("source", "unknown")

        cursor.execute("SELECT price FROM cars WHERE id = ?", (car_id,))
        row = cursor.fetchone()

        if row is None:
            try:
                cursor.execute('''
                    INSERT INTO cars (id, model, version, year, price, mileage, created_at,
                        first_seen, features, image_url, url, color, towbar, winter_wheels,
                        battery_range, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (car_id, car["model"], car["version"], car["year"], car["price"],
                      car["mileage"], car["created_at"], now_utc, car["features"], car["image_url"],
                      car["url"], car["color"], car["towbar"], car["winter_wheels"],
                      car["battery_range"], source))
                new_cars_added += 1
            except Exception as e:
                print(f"  Error inserting {car_id}: {e}")
        else:
            old_price = row[0]
            if str(old_price) != str(car["price"]):
                cursor.execute('''
                    UPDATE cars SET price = ?, mileage = ?, scraped_at = CURRENT_TIMESTAMP, url = ?,
                        color = ?, towbar = ?, winter_wheels = ?, battery_range = ? WHERE id = ?
                ''', (car["price"], car["mileage"], car["url"], car["color"], car["towbar"],
                      car["winter_wheels"], car["battery_range"], car_id))
                updated_cars += 1
            else:
                cursor.execute('''
                    UPDATE cars SET mileage = ?, scraped_at = CURRENT_TIMESTAMP, url = ?,
                        color = ?, towbar = ?, winter_wheels = ?, battery_range = ? WHERE id = ?
                ''', (car["mileage"], car["url"], car["color"], car["towbar"],
                      car["winter_wheels"], car["battery_range"], car_id))

    conn.commit()
    conn.close()
    return new_cars_added, updated_cars


def mark_removed_cars(source, seen_ids):
    """Reconcile active/removed status for a single source.

    Scoped to `source` so a failed or incomplete scrape of one source never
    flags another source's cars as removed. Cars from this source that are
    active but no longer seen are marked removed; previously-removed cars
    that reappear are reactivated.
    """
    conn = get_connection()
    cursor = conn.cursor()
    # Load seen IDs into a temp table instead of inlining one bind variable per
    # ID — that hits SQLite's SQLITE_MAX_VARIABLE_NUMBER limit (999 on older
    # builds) once a source has enough listings.
    cursor.execute("CREATE TEMP TABLE seen_ids (id TEXT PRIMARY KEY)")
    cursor.executemany(
        "INSERT OR IGNORE INTO seen_ids (id) VALUES (?)",
        [(i,) for i in seen_ids],
    )
    cursor.execute('''
        UPDATE cars SET status = 'removed', removed_at = date('now')
        WHERE status = 'active' AND source = ?
          AND id NOT IN (SELECT id FROM seen_ids)
    ''', (source,))
    removed = cursor.rowcount
    cursor.execute('''
        UPDATE cars SET status = 'active', removed_at = NULL
        WHERE status = 'removed' AND source = ?
          AND id IN (SELECT id FROM seen_ids)
    ''', (source,))
    cursor.execute("DROP TABLE seen_ids")
    conn.commit()
    conn.close()
    return removed


def dedupe_cross_source():
    """Flag cross-source duplicate listings so analytics don't double-count the
    same physical car listed on more than one site.

    Match key is (model, year, mileage, price); within a matched group the
    canonical source (carla.se, which carries the richest metadata) is kept and
    every row from another source is flagged is_duplicate=1. Only rows from a
    *different* source are flagged, so two genuinely distinct cars on the same
    site are never merged. Recomputed from scratch each run.
    """
    conn = get_connection()
    cursor = conn.cursor()
    # Reset first so cars that are no longer duplicated become visible again.
    cursor.execute("UPDATE cars SET is_duplicate = 0 WHERE is_duplicate = 1")

    cursor.execute('''
        SELECT model, year, mileage, price
        FROM cars
        WHERE status = 'active' AND price IS NOT NULL
          AND mileage IS NOT NULL AND year IS NOT NULL
        GROUP BY model, year, mileage, price
        HAVING COUNT(DISTINCT source) > 1
    ''')
    groups = cursor.fetchall()

    flagged = 0
    for model, year, mileage, price in groups:
        cursor.execute('''
            SELECT id, source FROM cars
            WHERE status = 'active' AND model = ? AND year = ?
              AND mileage = ? AND price = ?
        ''', (model, year, mileage, price))
        rows = cursor.fetchall()
        sources = {src for _, src in rows}
        canonical = 'carla.se' if 'carla.se' in sources else sorted(sources)[0]
        for car_id, src in rows:
            if src != canonical:
                cursor.execute("UPDATE cars SET is_duplicate = 1 WHERE id = ?", (car_id,))
                flagged += 1

    conn.commit()
    conn.close()
    return flagged


def save_price_snapshot():
    conn = get_connection()
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute('''
        SELECT model, price FROM cars
        WHERE status = 'active' AND price IS NOT NULL
          AND COALESCE(is_duplicate, 0) = 0
        ORDER BY model, price
    ''')
    rows = cursor.fetchall()
    by_model = {}
    for model, price in rows:
        by_model.setdefault(model, []).append(price)

    for model, prices in by_model.items():
        avg_price = round(sum(prices) / len(prices))
        prices.sort()
        mid = len(prices) // 2
        median_price = prices[mid] if len(prices) % 2 else round((prices[mid - 1] + prices[mid]) / 2)
        cursor.execute('''
            INSERT OR REPLACE INTO price_snapshots (date, model, avg_price, median_price, car_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (today, model, avg_price, median_price, len(prices)))

    conn.commit()
    conn.close()


def main():
    print("Initializing database...")
    init_db()

    for scraper in ALL_SCRAPERS:
        print(f"\n[{scraper.name}] Fetching Tesla listings...")
        try:
            cars = scraper.fetch()
        except Exception as e:
            # Source failed entirely — skip reconciliation so we never flag
            # its (or any other source's) cars as removed/sold by mistake.
            print(f"[{scraper.name}] Error: {e} — skipping removal reconciliation.")
            continue

        print(f"[{scraper.name}] Fetched {len(cars)} cars.")
        new_added, updated = save_cars_to_db(cars)
        print(f"[{scraper.name}] Added {new_added} new, updated {updated} prices.")

        seen_ids = {car["id"] for car in cars}
        if not seen_ids:
            print(f"[{scraper.name}] No cars returned — skipping removal reconciliation.")
        elif not scraper.last_fetch_complete:
            print(f"[{scraper.name}] Incomplete fetch — refreshed prices but skipping removal reconciliation.")
        else:
            removed = mark_removed_cars(scraper.name, seen_ids)
            print(f"[{scraper.name}] Marked {removed} cars as removed/sold.")

    flagged = dedupe_cross_source()
    print(f"\nFlagged {flagged} cross-source duplicate listings.")

    save_price_snapshot()
    print("Price snapshot saved.")


if __name__ == "__main__":
    main()
