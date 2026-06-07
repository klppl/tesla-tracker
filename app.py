from flask import Flask, render_template
import sqlite3
import os
import argparse
import logging
from datetime import datetime
from database import init_db

# Each analytics section is wrapped in try/except so one failing query (schema
# drift, bad data) degrades that single chart instead of the whole dashboard.
# Log the traceback rather than swallowing it silently — in the static/CI build
# this surfaces in log.txt, which is the only way a quietly-missing chart gets
# noticed. The traceback pinpoints the failing section by line.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("tesla_tracker")

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "tesla_cars.db")

# Shared predicate for "a car that should appear in active-market stats":
# currently listed and not a flagged cross-source duplicate.
ACTIVE = "status = 'active' AND COALESCE(is_duplicate, 0) = 0"

def get_connection():
    return sqlite3.connect(DB_PATH)

def get_analytics_data():
    if not os.path.exists(DB_PATH):
        return {}

    # Ensure the schema is current (idempotent) so a static build never trips
    # over a column added since the DB was last written by the scraper.
    init_db()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    analytics = {
        "summary": {"total": 0, "by_model": {}, "by_source": {}},
        "averages": {},
        "scatter": {},
        "scatter_all": [],
        "daily_additions": {"dates": [], "counts": []},
        "price_trends": {},
        "market_stats": {},
        "equipment_value": {},
        "color_stats": [],
        "depreciation": {},
        "listing_timing": {"by_weekday": [], "by_month": []},
        "price_prediction": {},
        "car_flow": {"added": [], "removed": []},
        "supply_trend": {},
        "battery_range": {},
    }

    # Summary stats. ACTIVE = listed and not a cross-source duplicate, so the
    # same physical car listed on two sites is counted once.
    cursor.execute(f"SELECT COUNT(*) FROM cars WHERE {ACTIVE}")
    analytics["summary"]["total"] = cursor.fetchone()[0]
    cursor.execute(f"SELECT model, COUNT(*) as cnt FROM cars WHERE {ACTIVE} GROUP BY model ORDER BY cnt DESC")
    for row in cursor.fetchall():
        analytics["summary"]["by_model"][row["model"]] = row["cnt"]
    cursor.execute(f"SELECT source, COUNT(*) as cnt FROM cars WHERE {ACTIVE} GROUP BY source ORDER BY cnt DESC")
    for row in cursor.fetchall():
        analytics["summary"]["by_source"][row["source"]] = row["cnt"]

    # Last updated timestamp — use most recent of: snapshot date, car added, car removed
    cursor.execute('''
        SELECT MAX(ts) FROM (
            SELECT MAX(date) as ts FROM price_snapshots
            UNION ALL
            SELECT MAX(created_at) as ts FROM cars
            UNION ALL
            SELECT MAX(removed_at) as ts FROM cars WHERE removed_at IS NOT NULL
        )
    ''')
    last_row = cursor.fetchone()
    if last_row and last_row[0]:
        analytics["summary"]["last_updated"] = last_row[0]

    # Quick stats for hero section
    cursor.execute('''
        SELECT
            ROUND(AVG(price)) as avg_price,
            MIN(price) as min_price,
            MAX(price) as max_price,
            ROUND(AVG(mileage) / 10.0) as avg_mileage_mil,
            ROUND(AVG(year), 1) as avg_year,
            MIN(year) as min_year,
            MAX(year) as max_year
        FROM cars
        WHERE {ACTIVE} AND price IS NOT NULL
    '''.format(ACTIVE=ACTIVE))
    row = cursor.fetchone()
    if row and row["avg_price"]:
        # Compute median price separately
        cursor.execute('''
            SELECT price FROM cars
            WHERE {ACTIVE} AND price IS NOT NULL
            ORDER BY price
        '''.format(ACTIVE=ACTIVE))
        prices = [r["price"] for r in cursor.fetchall()]
        n = len(prices)
        if n > 0:
            median_price = (prices[n // 2] + prices[(n - 1) // 2]) // 2
        else:
            median_price = int(row["avg_price"])

        analytics["summary"]["quick_stats"] = {
            "avg_price": int(row["avg_price"]),
            "median_price": median_price,
            "min_price": int(row["min_price"]),
            "max_price": int(row["max_price"]),
            "avg_mileage": int(row["avg_mileage_mil"]),
            "avg_year": row["avg_year"],
            "min_year": int(row["min_year"]),
            "max_year": int(row["max_year"]),
        }

    # 1. Averages by Model and Year. Convert mileage (in km) to 'mil' (divide by 10)
    cursor.execute('''
        SELECT 
            model, 
            year, 
            AVG(price) as avg_price, 
            AVG(mileage) / 10.0 as avg_mileage_mil,
            COUNT(*) as count
        FROM cars
        WHERE year IS NOT NULL AND {ACTIVE}
        GROUP BY model, year
        ORDER BY model, year
    '''.format(ACTIVE=ACTIVE))
    for row in cursor.fetchall():
        model = f"Tesla {row['model']}"
        if model not in analytics["averages"]:
            analytics["averages"][model] = {"years": [], "prices": [], "mileages": [], "counts": []}
        analytics["averages"][model]["years"].append(row['year'])
        analytics["averages"][model]["prices"].append(round(row['avg_price']))
        analytics["averages"][model]["mileages"].append(round(row['avg_mileage_mil'], 1))
        analytics["averages"][model]["counts"].append(row['count'])

    # 2. Scatter Data (active cars only) - Price vs Mileage in 'mil'
    cursor.execute('''
        SELECT model, version, year, price, mileage / 10.0 as mileage_mil, url, source, color
        FROM cars
        WHERE price IS NOT NULL AND mileage IS NOT NULL AND {ACTIVE}
    '''.format(ACTIVE=ACTIVE))
    for row in cursor.fetchall():
        model = f"Tesla {row['model']}"
        if model not in analytics["scatter"]:
            analytics["scatter"][model] = []
            
        kr_per_mil = round(row['price'] / row['mileage_mil']) if row['mileage_mil'] and row['mileage_mil'] > 0 else None
        point = {
            "x": round(row['mileage_mil'], 1),
            "y": row['price'],
            "year": row['year'],
            "version": row['version'],
            "model": model,
            "url": row['url'],
            "kr_mil": kr_per_mil,
            "source": row['source'],
            "color": row['color'] or "Okänd",
        }
        analytics["scatter"][model].append(point)
        analytics["scatter_all"].append(point)
        
    # 3. Daily Additions — when the tracker first saw each listing (first_seen),
    # not when the seller published it (created_at).
    cursor.execute('''
        SELECT substr(first_seen, 1, 10) as fetch_date, COUNT(*) as count
        FROM cars
        WHERE first_seen IS NOT NULL
        GROUP BY fetch_date
        ORDER BY fetch_date
    ''')
    for row in cursor.fetchall():
        if row['fetch_date']:
            analytics["daily_additions"]["dates"].append(row['fetch_date'])
            analytics["daily_additions"]["counts"].append(row['count'])

    # 4. Price trends over time (from snapshots)
    try:
        cursor.execute('''
            SELECT date, model, avg_price, median_price, car_count
            FROM price_snapshots
            ORDER BY model, date
        ''')
        for row in cursor.fetchall():
            model = f"Tesla {row['model']}"
            if model not in analytics["price_trends"]:
                analytics["price_trends"][model] = {"dates": [], "avg": [], "median": [], "count": []}
            analytics["price_trends"][model]["dates"].append(row['date'])
            analytics["price_trends"][model]["avg"].append(row['avg_price'])
            analytics["price_trends"][model]["median"].append(row['median_price'])
            analytics["price_trends"][model]["count"].append(row['car_count'])
    except Exception:
        logger.exception("Analytics section failed — skipping (see traceback for which)")

    # 5. Market stats – removed cars (sold)
    try:
        cursor.execute('''
            SELECT model,
                   COUNT(*) as total_removed,
                   ROUND(AVG(julianday(removed_at) - julianday(substr(created_at, 1, 10)))) as avg_days
            FROM cars
            WHERE status = 'removed' AND removed_at IS NOT NULL AND created_at IS NOT NULL
            GROUP BY model
        ''')
        for row in cursor.fetchall():
            model = f"Tesla {row['model']}"
            analytics["market_stats"][model] = {
                "sold_count": row['total_removed'],
                "avg_days_on_market": int(row['avg_days']) if row['avg_days'] else None,
            }
    except Exception:
        logger.exception("Analytics section failed — skipping (see traceback for which)")

    # 6. Equipment value – separate towbar and winter wheel price impact
    try:
        # Towbar impact
        cursor.execute('''
            SELECT
                CASE
                    WHEN towbar IN ('INCLUDED', 'ADDON', 'AVAILABLE') THEN 'Med dragkrok'
                    ELSE 'Utan dragkrok'
                END as towbar_label,
                ROUND(AVG(price)) as avg_price,
                COUNT(*) as cnt
            FROM cars
            WHERE price IS NOT NULL AND {ACTIVE}
            GROUP BY towbar_label
            HAVING cnt >= 2
        '''.format(ACTIVE=ACTIVE))
        towbar_stats = []
        for row in cursor.fetchall():
            towbar_stats.append({
                "label": row["towbar_label"],
                "avg_price": row["avg_price"],
                "count": row["cnt"],
            })

        # Winter wheels impact
        cursor.execute('''
            SELECT
                CASE
                    WHEN winter_wheels IN ('FRICTION', 'STUDDED') THEN 'Med vinterhjul'
                    ELSE 'Utan vinterhjul'
                END as wheels_label,
                ROUND(AVG(price)) as avg_price,
                COUNT(*) as cnt
            FROM cars
            WHERE price IS NOT NULL AND {ACTIVE}
            GROUP BY wheels_label
            HAVING cnt >= 2
        '''.format(ACTIVE=ACTIVE))
        winter_stats = []
        for row in cursor.fetchall():
            winter_stats.append({
                "label": row["wheels_label"],
                "avg_price": row["avg_price"],
                "count": row["cnt"],
            })

        analytics["equipment_value"] = {
            "towbar": towbar_stats,
            "winter_wheels": winter_stats,
        }
    except Exception:
        logger.exception("Analytics section failed — skipping (see traceback for which)")

    # 7. Color stats – average price per color
    try:
        cursor.execute('''
            SELECT color, ROUND(AVG(price)) as avg_price, COUNT(*) as cnt
            FROM cars
            WHERE color IS NOT NULL AND price IS NOT NULL AND {ACTIVE}
            GROUP BY color
            HAVING cnt >= 2
            ORDER BY avg_price DESC
        '''.format(ACTIVE=ACTIVE))
        colors_list = []
        for row in cursor.fetchall():
            colors_list.append({
                "color": row["color"],
                "avg_price": int(row["avg_price"]),
                "count": row["cnt"],
            })
        analytics["color_stats"] = colors_list
    except Exception:
        logger.exception("Analytics section failed — skipping (see traceback for which)")

    # 8. Depreciation curve – avg price by car age (current year - model year)
    current_year = datetime.now().year
    try:
        cursor.execute('''
            SELECT model, year, ROUND(AVG(price)) as avg_price, COUNT(*) as cnt
            FROM cars
            WHERE year IS NOT NULL AND price IS NOT NULL AND {ACTIVE}
            GROUP BY model, year
            ORDER BY model, year
        '''.format(ACTIVE=ACTIVE))
        for row in cursor.fetchall():
            model = f"Tesla {row['model']}"
            age = current_year - row['year']
            if model not in analytics["depreciation"]:
                analytics["depreciation"][model] = {"ages": [], "prices": [], "years": [], "counts": []}
            analytics["depreciation"][model]["ages"].append(age)
            analytics["depreciation"][model]["prices"].append(int(row['avg_price']))
            analytics["depreciation"][model]["years"].append(row['year'])
            analytics["depreciation"][model]["counts"].append(row['cnt'])
    except Exception:
        logger.exception("Analytics section failed — skipping (see traceback for which)")

    # 9. Listing timing – weekday and month distribution. Intentionally uses
    # created_at (the seller's publish date), since this measures when sellers
    # list cars, not when the tracker discovered them.
    weekday_names = ['Mån', 'Tis', 'Ons', 'Tor', 'Fre', 'Lör', 'Sön']
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'Maj', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dec']
    try:
        cursor.execute('''
            SELECT
                CAST(strftime('%w', substr(created_at, 1, 10)) AS INTEGER) as dow,
                CAST(strftime('%m', substr(created_at, 1, 10)) AS INTEGER) as month,
                price
            FROM cars
            WHERE created_at IS NOT NULL AND price IS NOT NULL
        ''')
        weekday_prices = {i: [] for i in range(7)}
        month_prices = {i: [] for i in range(1, 13)}
        for row in cursor.fetchall():
            dow = row['dow']  # 0=Sunday in SQLite
            weekday_prices[dow].append(row['price'])
            month_prices[row['month']].append(row['price'])

        # SQLite: 0=Sun, 1=Mon..6=Sat → remap to Mon-Sun
        remap = [1, 2, 3, 4, 5, 6, 0]  # Mon=1, Tue=2 ... Sun=0
        analytics["listing_timing"]["by_weekday"] = [{
            "label": weekday_names[i],
            "count": len(weekday_prices[remap[i]]),
            "avg_price": round(sum(weekday_prices[remap[i]]) / len(weekday_prices[remap[i]])) if weekday_prices[remap[i]] else 0,
        } for i in range(7)]

        analytics["listing_timing"]["by_month"] = [{
            "label": month_names[m - 1],
            "count": len(month_prices[m]),
            "avg_price": round(sum(month_prices[m]) / len(month_prices[m])) if month_prices[m] else 0,
        } for m in range(1, 13)]
    except Exception:
        logger.exception("Analytics section failed — skipping (see traceback for which)")

    # 10. Price prediction – linear extrapolation from snapshots
    try:
        cursor.execute('''
            SELECT model, date, avg_price
            FROM price_snapshots
            ORDER BY model, date
        ''')
        snapshot_data = {}
        for row in cursor.fetchall():
            model = f"Tesla {row['model']}"
            snapshot_data.setdefault(model, []).append((row['date'], row['avg_price']))

        for model, points in snapshot_data.items():
            if len(points) < 2:
                continue
            # Linear regression price = slope * day + intercept, where day is
            # the number of days since the first snapshot — not the row index —
            # so gaps in the snapshot history don't distort the slope.
            n = len(points)
            base_date = datetime.strptime(points[0][0], '%Y-%m-%d')
            xs = [(datetime.strptime(d, '%Y-%m-%d') - base_date).days for d, _ in points]
            ys = [p[1] for p in points]
            x_mean = sum(xs) / n
            y_mean = sum(ys) / n
            num = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
            den = sum((xs[i] - x_mean) ** 2 for i in range(n))
            slope = num / den if den != 0 else 0
            intercept = y_mean - slope * x_mean

            # Predict 90 days past the most recent snapshot
            pred_90 = round(slope * (xs[-1] + 90) + intercept)
            current = ys[-1]
            change_pct = round((pred_90 - current) / current * 100, 1) if current else 0

            analytics["price_prediction"][model] = {
                "current_avg": current,
                "predicted_90d": pred_90,
                "change_pct": change_pct,
                "direction": "up" if slope > 0 else "down",
                "data_points": n,
            }
    except Exception:
        logger.exception("Analytics section failed — skipping (see traceback for which)")

    # 11. Car flow – recently added and removed cars (last 7 days)
    try:
        cursor.execute('''
            SELECT model, version, year, price, mileage / 10.0 as mileage_mil,
                   url, source, color, substr(first_seen, 1, 10) as added_date
            FROM cars
            WHERE first_seen IS NOT NULL
              AND substr(first_seen, 1, 10) >= date('now', '-7 days')
            ORDER BY first_seen DESC
            LIMIT 50
        ''')
        for row in cursor.fetchall():
            analytics["car_flow"]["added"].append({
                "model": row["model"],
                "version": row["version"],
                "year": row["year"],
                "price": row["price"],
                "mileage_mil": round(row["mileage_mil"], 1) if row["mileage_mil"] else None,
                "url": row["url"],
                "source": row["source"],
                "color": row["color"],
                "date": row["added_date"],
            })

        cursor.execute('''
            SELECT model, version, year, price, mileage / 10.0 as mileage_mil,
                   url, source, color, substr(removed_at, 1, 10) as removed_date
            FROM cars
            WHERE status = 'removed' AND removed_at IS NOT NULL
              AND substr(removed_at, 1, 10) >= date('now', '-7 days')
            ORDER BY removed_at DESC
            LIMIT 50
        ''')
        for row in cursor.fetchall():
            analytics["car_flow"]["removed"].append({
                "model": row["model"],
                "version": row["version"],
                "year": row["year"],
                "price": row["price"],
                "mileage_mil": round(row["mileage_mil"], 1) if row["mileage_mil"] else None,
                "url": row["url"],
                "source": row["source"],
                "color": row["color"],
                "date": row["removed_date"],
            })
    except Exception:
        logger.exception("Analytics section failed — skipping (see traceback for which)")

    # 12. Supply trend – car_count per model over time from snapshots
    try:
        cursor.execute('''
            SELECT date, model, car_count
            FROM price_snapshots
            WHERE car_count IS NOT NULL
            ORDER BY model, date
        ''')
        for row in cursor.fetchall():
            model = f"Tesla {row['model']}"
            if model not in analytics["supply_trend"]:
                analytics["supply_trend"][model] = {"dates": [], "counts": []}
            analytics["supply_trend"][model]["dates"].append(row['date'])
            analytics["supply_trend"][model]["counts"].append(row['car_count'])
    except Exception:
        logger.exception("Analytics section failed — skipping (see traceback for which)")

    # 14. Battery range analysis
    try:
        # Average range per model and year
        cursor.execute('''
            SELECT model, year, ROUND(AVG(battery_range)) as avg_range, COUNT(*) as cnt
            FROM cars
            WHERE battery_range IS NOT NULL AND battery_range > 0
              AND year IS NOT NULL AND {ACTIVE}
            GROUP BY model, year
            HAVING cnt >= 1
            ORDER BY model, year
        '''.format(ACTIVE=ACTIVE))
        for row in cursor.fetchall():
            model = f"Tesla {row['model']}"
            if model not in analytics["battery_range"]:
                analytics["battery_range"][model] = {"years": [], "ranges": [], "counts": []}
            analytics["battery_range"][model]["years"].append(row['year'])
            analytics["battery_range"][model]["ranges"].append(int(row['avg_range']))
            analytics["battery_range"][model]["counts"].append(row['cnt'])
    except Exception:
        logger.exception("Analytics section failed — skipping (see traceback for which)")

    conn.close()
    return analytics

@app.route('/')
def index():
    data = get_analytics_data()
    return render_template('index.html', analytics_data=data)

def generate_static():
    output_dir = os.path.join(os.path.dirname(__file__), "public")
    os.makedirs(output_dir, exist_ok=True)

    with app.app_context():
        data = get_analytics_data()
        html = render_template('index.html', analytics_data=data)

    output_path = os.path.join(output_dir, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    size = len(html.encode('utf-8'))
    print(f"Statisk sida genererad: {output_path}")
    print(f"  Storlek: {size:,} bytes")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Tesla Tracker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--server", action="store_true", help="Starta Flask-servern")
    group.add_argument("--static", action="store_true", help="Generera statiska filer i /public")
    parser.add_argument("--debug", action="store_true",
                        help="Aktivera Flask debug-läge (endast lokal utveckling)")
    args = parser.parse_args()

    if args.static:
        generate_static()
    else:
        app.run(debug=args.debug, port=5000)
