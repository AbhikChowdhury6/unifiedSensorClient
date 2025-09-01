import sqlite3
import sys
from datetime import datetime
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from config import sqlite_writer_write_location

db_path = f"{sqlite_writer_write_location}data.db"

query = """
SELECT * FROM readings GROUP BY topic ORDER BY ts DESC LIMIT 20;
"""

try:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query).fetchall()
        if not rows:
            print("No rows found.")
        else:
            print(f"{'topic':<40} {'ts':>10} {'value':>10}")
            print("-" * 52)
            for topic, ts, value in rows:
                dt = datetime.fromtimestamp(ts/1_000_000_000)  # Convert ns to seconds
                print(f"{topic:<40} {dt.strftime('%Y-%m-%d %H:%M:%S')} {value:>10}")
except sqlite3.OperationalError as e:
    if "no such table" in str(e).lower():
        print("Table 'readings' not found. Did you create it first?")
    else:
        raise
