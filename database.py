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
    ]
    for col, coltype, default in new_cols:
        try:
            cursor.execute(f"ALTER TABLE cars ADD COLUMN {col} {coltype} DEFAULT {default}")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
