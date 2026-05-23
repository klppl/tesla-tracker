import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "tesla_cars.db")

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create the cars table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cars (
            id TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            version TEXT NOT NULL,
            year INTEGER,
            price INTEGER,
            mileage INTEGER,
            created_at TEXT,
            first_seen TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            features TEXT,
            image_url TEXT,
            url TEXT,
            source TEXT DEFAULT 'carla.se',
            status TEXT DEFAULT 'active',
            removed_at TEXT,
            color TEXT,
            towbar TEXT,
            winter_wheels TEXT,
            battery_range INTEGER
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS price_snapshots (
            date TEXT NOT NULL,
            model TEXT NOT NULL,
            avg_price INTEGER,
            median_price INTEGER,
            car_count INTEGER,
            PRIMARY KEY (date, model)
        )
    ''')

    # Add columns if they don't exist (for existing databases)
    new_cols = [
        ('status', 'TEXT', "'active'"), ('removed_at', 'TEXT', 'NULL'),
        ('color', 'TEXT', 'NULL'), ('towbar', 'TEXT', 'NULL'),
        ('winter_wheels', 'TEXT', 'NULL'), ('battery_range', 'INTEGER', 'NULL'),
        ('first_seen', 'TEXT', 'NULL'),
    ]
    for col, coltype, default in new_cols:
        try:
            cursor.execute(f"ALTER TABLE cars ADD COLUMN {col} {coltype} DEFAULT {default}")
        except sqlite3.OperationalError:
            pass

    # Backfill first_seen for rows predating the column. We never observed the
    # true first-seen time for these, so approximate with the listing's publish
    # date (created_at), falling back to the last scrape time. Idempotent: new
    # rows get first_seen at insert, so this only ever touches legacy rows once.
    cursor.execute('''
        UPDATE cars SET first_seen = COALESCE(created_at, scraped_at)
        WHERE first_seen IS NULL
    ''')

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
