import sqlite3
import sys

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from config import sqlite_writer_write_location

db_path = f"{sqlite_writer_write_location}data.db"

print(f"dropping all topic tables from {db_path}")
with sqlite3.connect(db_path) as conn:
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
    for t in tables:
        print(f" - dropping {t}")
        conn.execute(f"DROP TABLE IF EXISTS \"{t.replace('\"', '\"\"')}\"")
    conn.commit()
print(f"dropped {len(tables)} tables from {db_path}")