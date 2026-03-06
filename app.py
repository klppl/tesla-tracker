from flask import Flask, render_template
import sqlite3
import os
import argparse

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
        "averages": {},
        "scatter": {},
        "scatter_all": [],
        "daily_additions": {"dates": [], "counts": []},
        "price_trends": {},
        "market_stats": {},
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
