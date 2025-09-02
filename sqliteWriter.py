import os
import sys
import zmq
import sqlite3
import time

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec

from config import sqlite_writer_subscription_endpoints, sqlite_writer_write_location
from config import sqlite_writer_subscription_topics, zmq_control_endpoint

def sqlite_writer():
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    for endpoint in sqlite_writer_subscription_endpoints:
        sub.connect(endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    print("sqlite writer connected to control and subscription topics")
    sys.stdout.flush()

    for topic in sqlite_writer_subscription_topics:
        sub.setsockopt(zmq.SUBSCRIBE, topic.encode())
        print(f"sqlite writer subscribed to {topic}")
        sys.stdout.flush()
    print("sqlite writer subscribed to all topics")
    sys.stdout.flush()
    
    os.makedirs(sqlite_writer_write_location, exist_ok=True)
    conn = sqlite3.connect(f"{sqlite_writer_write_location}data.db")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS readings (
    topic TEXT NOT NULL,
    ts INTEGER NOT NULL,   -- epoch ns
    value REAL,            -- assumes scalar sensors
    PRIMARY KEY(topic, ts)
    )
    """)
    ins = conn.cursor()
    
    last_commit = time.time()
    while True:
        topic, msg = ZmqCodec.decode(sub.recv_multipart())
        ts = msg[0]
        value = msg[1]
        if topic == "control":
            if msg == "exit":
                print("sqlite writer got control exit")
                sys.stdout.flush()
                break
        if topic in sqlite_writer_subscription_topics:
            ins.execute("INSERT OR IGNORE INTO readings(topic, ts, value) " + 
                "VALUES (?, ?, ?)", (topic, ts, value))
            print(f"sqlite writer wrote {msg} to {topic}")
            sys.stdout.flush()
            
            # Commit every second
            current_time = time.time()
            if current_time - last_commit >= 1.0:
                conn.commit()
                last_commit = current_time
        else:
            print(f"sqlite writer got unknown topic {topic}")
            sys.stdout.flush()
    print("sqlite writer exiting")
    sys.stdout.flush()