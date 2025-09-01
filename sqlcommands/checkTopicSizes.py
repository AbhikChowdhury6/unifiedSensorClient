import sqlite3
import sys
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from config import sqlite_writer_write_location

db_path = f"{sqlite_writer_write_location}data.db"

query = """
SELECT topic, COUNT(*) AS entry_count
FROM readings
GROUP BY topic
ORDER BY entry_count DESC;
"""

try:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query).fetchall()
        if not rows:
            print("No rows found.")
        else:
            print(f"{'topic':<40} {'count':>10}")
            print("-" * 52)
            for topic, count in rows:
                print(f"{topic:<40} {count:>10}")
except sqlite3.OperationalError as e:
    if "no such table" in str(e).lower():
        print("Table 'readings' not found. Did you create it first?")
    else:
        raise
