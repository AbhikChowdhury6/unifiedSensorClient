import sqlite3
import sys

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from config import sqlite_writer_write_location

db_path = f"{sqlite_writer_write_location}data.db"

with sqlite3.connect(db_path) as conn:
    # Get user-created tables (each is a topic)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]

    if not tables:
        print("No topic tables found.")
        sys.exit(0)

    counts = []
    for t in tables:
        cnt = conn.execute(f"SELECT COUNT(*) FROM \"{t.replace('\"', '\"\"')}\"").fetchone()[0]
        counts.append((t, cnt))

    counts.sort(key=lambda x: x[1], reverse=True)

    print(f"{'table':<70} {'count':>12}")
    print("-" * 84)
    for name, cnt in counts:
        print(f"{name:<70} {cnt:>12}")
