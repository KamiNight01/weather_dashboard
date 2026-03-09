from db.database import get_connection, init_db

LOCATIONS = [
    ("Seattle", "WA", "US", 47.6062, -122.3321),
    ("Providence", "RI", "US", 41.8240, -71.4128),
    ("Columbus", "OH", "US", 39.9612, -82.9988),
    ("Los Angeles", "CA", "US", 34.0522, -118.2437),
]

def seed():
    init_db()
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO locations
            (name, region, country, latitude, longitude)
            VALUES (?, ?, ?, ?, ?)
            """,
            LOCATIONS,
        )
        conn.commit()

if __name__ == "__main__":
    seed()

