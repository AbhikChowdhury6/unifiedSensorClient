import sqlite3
import sys
from datetime import datetime
import argparse

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from config import sqlite_writer_write_location

# Set up command line argument parsing
parser = argparse.ArgumentParser(description='Show the last N rows per per-topic table from the database.')
parser.add_argument('-n', '--num_rows', type=int, default=10,
                   help='Number of rows to display per table (default: 10)')
args = parser.parse_args()

db_path = f"{sqlite_writer_write_location}data.db"

def maybe_format_value(value):
    # Heuristic formatting for epoch-ns timestamps; otherwise return as-is
    if isinstance(value, int) and value > 1_500_000_000_000_000_000:
        try:
            return datetime.fromtimestamp(value / 1_000_000_000).strftime('%Y-%m-%d %H:%M:%S.%f')
        except Exception:
            return value
    return value

with sqlite3.connect(db_path) as conn:
    conn.row_factory = sqlite3.Row
    # List all user tables created for topics
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]

    if not tables:
        print("No topic tables found.")
        sys.exit(0)

    def qident(name: str) -> str:
        return name.replace('"', '""')

    for idx, table in enumerate(tables):
        # Fetch column names for the table
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info(\"{qident(table)}\")").fetchall()]
        # Pull last N rows by insertion order (rowid desc)
        rows = conn.execute(f"SELECT rowid, * FROM \"{qident(table)}\" ORDER BY rowid DESC LIMIT ?", (args.num_rows,)).fetchall()

        if idx > 0:
            print("\n" + "=" * 80 + "\n")
        print(f"Table: {table}")
        header = ["rowid"] + cols
        print(" | ".join(header))
        print("-" * 80)
        for r in rows:
            values = [maybe_format_value(r[k]) for k in header]
            print(" | ".join(str(v) for v in values))
