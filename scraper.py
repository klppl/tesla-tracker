import requests
import json
from datetime import datetime
from database import get_connection, init_db

# Algolia API details for Carla.se
URL = "https://izs3uhkhl4-dsn.algolia.net/1/indexes/*/queries"
HEADERS = {
    "x-algolia-agent": "Algolia for JavaScript (4.25.2)",
    "x-algolia-application-id": "IZS3UHKHL4",
    "x-algolia-api-key": "05ebd9cb812d1c6ebe07ab6de7dc28bb"
}

def fetch_tesla_listings(offset=0, length=50):
    payload = {
        "requests": [
            {
                "indexName": "new_created_at_desc",
                "params": f"filters=manufacturer%3A%22Tesla%22&offset={offset}&length={length}"
            }
        ]
    }
    
    response = requests.post(URL, params=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()['results'][0]['hits']

def clean_features(badges):
    if not badges:
        return ""
    # Usually badges might be a list of dicts or strings. Let's inspect typical Carla data.
    # The subagent mentioned: badges: List of features like `["Dragkrok"]` 
    if isinstance(badges, list):
         return ", ".join([str(b) for b in badges])
    return str(badges)

def mark_removed_cars(seen_ids):
    """Mark cars not seen in this scrape as removed/sold."""
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ','.join('?' for _ in seen_ids)
    cursor.execute(f'''
        UPDATE cars SET status = 'removed', removed_at = date('now')
        WHERE status = 'active' AND id NOT IN ({placeholders})
    ''', list(seen_ids))
    removed = cursor.rowcount
    # Reactivate cars that reappear
    cursor.execute(f'''
        UPDATE cars SET status = 'active', removed_at = NULL
        WHERE status = 'removed' AND id IN ({placeholders})
    ''', list(seen_ids))
    conn.commit()
    conn.close()
    return removed

def save_price_snapshot():
    """Save daily average/median price per model."""
    conn = get_connection()
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute('''
        SELECT model, price FROM cars
        WHERE status = 'active' AND price IS NOT NULL
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

def save_cars_to_db(cars):
    conn = get_connection()
    cursor = conn.cursor()

    new_cars_added = 0
    updated_cars = 0

    for car in cars:
        # Extract fields
        car_id = car.get("registrationNumber") or car.get("objectID")
        if not car_id:
            continue
            
        model = car.get("model", "Unknown")
        version = car.get("version", "")
        year = car.get("modelYear")
        price = car.get("retailPrice")
        mileage = car.get("mileage")
        created_at = car.get("createdAt")
        features = clean_features(car.get("badges", []))
        image_url = car.get("mainPhoto", {}).get("url") if isinstance(car.get("mainPhoto"), dict) else car.get("mainPhoto")
        
        # Carla URL format typically: /bil/{objectID} 
        object_id = car.get("objectID", "")
        url = f"https://www.carla.se/bil/{object_id}"
        
        # Check if exists
        cursor.execute("SELECT price FROM cars WHERE id = ?", (car_id,))
        row = cursor.fetchone()
        
        if row is None:
            # Insert new
            try:
                cursor.execute('''
                    INSERT INTO cars (id, model, version, year, price, mileage, created_at, features, image_url, url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (car_id, model, version, year, price, mileage, created_at, features, image_url, url))
                new_cars_added += 1
            except Exception as e:
                print(f"Error inserting car {car_id}: {e}")
        else:
            old_price = row[0]
            if str(old_price) != str(price):
                # Update price and url
                cursor.execute('''
                    UPDATE cars SET price = ?, scraped_at = CURRENT_TIMESTAMP, url = ? WHERE id = ?
                ''', (price, url, car_id))
                updated_cars += 1
            else:
                # Update timestamp and url (to fix old broken urls)
                cursor.execute('''
                    UPDATE cars SET scraped_at = CURRENT_TIMESTAMP, url = ? WHERE id = ?
                ''', (url, car_id))
            
    conn.commit()
    conn.close()
    
    return new_cars_added, updated_cars

def main():
    print("Initializing database...")
    init_db()
    
    print("Fetching Tesla listings from carla.se...")
    try:
        cars = fetch_tesla_listings()
        print(f"Fetched {len(cars)} cars.")

        new_added, updated = save_cars_to_db(cars)
        print(f"Successfully processed listings. Added {new_added} new cars, updated {updated} prices.")

        seen_ids = set()
        for car in cars:
            car_id = car.get("registrationNumber") or car.get("objectID")
            if car_id:
                seen_ids.add(car_id)

        removed = mark_removed_cars(seen_ids)
        print(f"Marked {removed} cars as removed/sold.")

        save_price_snapshot()
        print("Price snapshot saved.")
    except Exception as e:
        print(f"Error scraping data: {e}")

if __name__ == "__main__":
    main()
