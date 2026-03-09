import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "weather.db"

def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)

def init_db():
    with get_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            region TEXT,
            country TEXT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL
        );
        """)
        conn.commit()

def search_locations(query: str, limit: int = 20):
    q = (query or "").strip()
    with get_connection() as conn:
        if not q:
            rows = conn.execute(
                """
                SELECT id, name, region, country, latitude, longitude
                FROM locations
                ORDER BY name
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            like = f"%{q}%"
            rows = conn.execute(
                """
                SELECT id, name, region, country, latitude, longitude
                FROM locations
                WHERE name LIKE ? OR region LIKE ? OR country LIKE ?
                ORDER BY name
                LIMIT ?
                """,
                (like, like, like, limit),
            ).fetchall()

    return [
        {
            "id": r[0],
            "name": r[1],
            "region": r[2],
            "country": r[3],
            "lat": r[4],
            "lon": r[5],
        }
        for r in rows
    ]

