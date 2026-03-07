from flask import Flask, render_template
import sqlite3
import os
import argparse
from datetime import datetime

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "tesla_cars.db")

def get_connection():
    return sqlite3.connect(DB_PATH)

def get_analytics_data():
    if not os.path.exists(DB_PATH):
        return {}
        
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
        "equipment_value": [],
        "color_stats": {},
        "depreciation": {},
        "listing_timing": {"by_weekday": [], "by_month": []},
        "price_prediction": {},
    }

    # Summary stats
    cursor.execute("SELECT COUNT(*) FROM cars WHERE status = 'active'")
    analytics["summary"]["total"] = cursor.fetchone()[0]
    cursor.execute("SELECT model, COUNT(*) as cnt FROM cars WHERE status = 'active' GROUP BY model ORDER BY cnt DESC")
    for row in cursor.fetchall():
        analytics["summary"]["by_model"][row["model"]] = row["cnt"]
    cursor.execute("SELECT source, COUNT(*) as cnt FROM cars WHERE status = 'active' GROUP BY source ORDER BY cnt DESC")
    for row in cursor.fetchall():
        analytics["summary"]["by_source"][row["source"]] = row["cnt"]

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
        WHERE status = 'active' AND price IS NOT NULL
    ''')
    row = cursor.fetchone()
    if row and row["avg_price"]:
        analytics["summary"]["quick_stats"] = {
            "avg_price": int(row["avg_price"]),
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
        WHERE year IS NOT NULL
        GROUP BY model, year
        ORDER BY model, year
    ''')
    for row in cursor.fetchall():
        model = f"Tesla {row['model']}"
        if model not in analytics["averages"]:
            analytics["averages"][model] = {"years": [], "prices": [], "mileages": [], "counts": []}
        analytics["averages"][model]["years"].append(row['year'])
        analytics["averages"][model]["prices"].append(round(row['avg_price']))
        analytics["averages"][model]["mileages"].append(round(row['avg_mileage_mil'], 1))
        analytics["averages"][model]["counts"].append(row['count'])

    # 2. Scatter Data (All cars) - Price vs Mileage in 'mil'
    cursor.execute('''
        SELECT model, version, year, price, mileage / 10.0 as mileage_mil, url
        FROM cars
        WHERE price IS NOT NULL AND mileage IS NOT NULL
    ''')
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
        }
        analytics["scatter"][model].append(point)
        analytics["scatter_all"].append(point)
        
    # 3. Daily Additions
    cursor.execute('''
        SELECT substr(created_at, 1, 10) as fetch_date, COUNT(*) as count
        FROM cars
        WHERE created_at IS NOT NULL
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
        pass

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
        pass

    # 6. Equipment value – price impact of towbar, winter wheels, battery range
    try:
        cursor.execute('''
            SELECT
                towbar,
                winter_wheels,
                ROUND(AVG(price)) as avg_price,
                COUNT(*) as cnt
            FROM cars
            WHERE price IS NOT NULL AND year IS NOT NULL AND mileage IS NOT NULL
            GROUP BY towbar, winter_wheels
            HAVING cnt >= 2
        ''')
        for row in cursor.fetchall():
            analytics["equipment_value"].append({
                "towbar": row["towbar"],
                "winter_wheels": row["winter_wheels"],
                "avg_price": row["avg_price"],
                "count": row["cnt"],
            })
    except Exception:
        pass

    # 7. Color stats – average price per color
    try:
        cursor.execute('''
            SELECT color, ROUND(AVG(price)) as avg_price, COUNT(*) as cnt
            FROM cars
            WHERE color IS NOT NULL AND price IS NOT NULL
            GROUP BY color
            HAVING cnt >= 2
            ORDER BY avg_price DESC
        ''')
        colors_list = []
        for row in cursor.fetchall():
            colors_list.append({
                "color": row["color"],
                "avg_price": int(row["avg_price"]),
                "count": row["cnt"],
            })
        analytics["color_stats"] = colors_list
    except Exception:
        pass

    # 8. Depreciation curve – avg price by car age (current year - model year)
    current_year = datetime.now().year
    try:
        cursor.execute('''
            SELECT model, year, ROUND(AVG(price)) as avg_price, COUNT(*) as cnt
            FROM cars
            WHERE year IS NOT NULL AND price IS NOT NULL
            GROUP BY model, year
            ORDER BY model, year
        ''')
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
        pass

    # 9. Listing timing – weekday and month distribution
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
        pass

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
            # Simple linear regression: price = slope * day_index + intercept
            n = len(points)
            xs = list(range(n))
            ys = [p[1] for p in points]
            x_mean = sum(xs) / n
            y_mean = sum(ys) / n
            num = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
            den = sum((xs[i] - x_mean) ** 2 for i in range(n))
            slope = num / den if den != 0 else 0
            intercept = y_mean - slope * x_mean

            # Predict 90 days ahead
            pred_90 = round(slope * (n - 1 + 90) + intercept)
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
        pass

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

    print(f"Statisk sida genererad: {output_path}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Tesla Tracker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--server", action="store_true", help="Starta Flask-servern")
    group.add_argument("--static", action="store_true", help="Generera statiska filer i /public")
    args = parser.parse_args()

    if args.static:
        generate_static()
    else:
        app.run(debug=True, port=5000)
