import sqlite3
import sys
from datetime import datetime
import argparse

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from config import sqlite_writer_write_location

# Set up command line argument parsing
parser = argparse.ArgumentParser(description='Show the last N rows per topic from the database.')
parser.add_argument('-n', '--num_rows', type=int, default=10,
                   help='Number of rows to display per topic (default: 10)')
args = parser.parse_args()

db_path = f"{sqlite_writer_write_location}data.db"

query = f"""
WITH RankedRows AS (
    SELECT 
        *,
        ROW_NUMBER() OVER (PARTITION BY topic ORDER BY ts DESC) as rn
    FROM readings
)
SELECT topic, ts, value
FROM RankedRows 
WHERE rn <= {args.num_rows}
ORDER BY topic, ts DESC;
"""

try:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query).fetchall()
        if not rows:
            print("No rows found.")
        else:
            current_topic = None
            for topic, ts, value in rows:
                if topic != current_topic:
                    if current_topic is not None:
                        print("\n" + "=" * 80 + "\n")  # Separator between topics
                    current_topic = topic
                    print(f"Topic: {topic}")
                    print(f"{'Timestamp':<25} {'Value':>15}")
                    print("-" * 40)
                
                dt = datetime.fromtimestamp(ts/1_000_000_000)  # Convert ns to seconds
                print(f"{dt.strftime('%Y-%m-%d %H:%M:%S.%f'):<25} {value:>15.6f}")
except sqlite3.OperationalError as e:
    if "no such table" in str(e).lower():
        print("Table 'readings' not found. Did you create it first?")
    else:
        raise
