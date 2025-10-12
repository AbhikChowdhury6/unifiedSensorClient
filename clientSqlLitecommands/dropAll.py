import sqlite3
import os
import sys

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from config import sqlite_writer_write_location

#os.system(f"rm -rf {sqlite_writer_write_location}*")

print(f"dropping readings table from {sqlite_writer_write_location}data.db")
conn = sqlite3.connect(f"{sqlite_writer_write_location}data.db")
conn.execute("DROP TABLE IF EXISTS readings")
conn.commit()
conn.close()
print(f"dropped readings table from {sqlite_writer_write_location}data.db")