import os
import sys
import zmq
import sqlite3
import time
from datetime import datetime, timezone
import numpy as np

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec
import logging
from logUtils import worker_configurer, check_apply_level, set_process_title

from config import sqlite_writer_process_config, zmq_control_endpoint
config = sqlite_writer_process_config

def sqlite_writer(log_queue):
    set_process_title(config["short_name"])
    worker_configurer(log_queue, config["debug_lvl"])
    l = logging.getLogger(config["short_name"])
    l.info(config["short_name"] + " writer starting")

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    for endpoint in config['subscription_endpoints']:
        sub.connect(endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    l.info(config["short_name"] + " writer connected to control and subscription topics")

    for topic in config['subscription_topics']:
        sub.setsockopt(zmq.SUBSCRIBE, topic.encode())
        l.info(config["short_name"] + " writer subscribed to " + topic)
    print("sqlite writer subscribed to all topics")
    l.info(config["short_name"] + " writer subscribed to all topics")
    
    os.makedirs(config['write_location'], exist_ok=True)
    conn = sqlite3.connect(f"{config['write_location']}data.db")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    ins = conn.cursor()

    # Helpers for dynamic per-topic tables
    def _qident(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    def _to_sql_type(value) -> str:
        # Map Python/numpy types to SQLite column types
        if isinstance(value, datetime):
            return "INTEGER"  # store epoch ns
        if isinstance(value, (bool, np.bool_)):
            return "INTEGER"
        if isinstance(value, (int, np.integer)):
            return "INTEGER"
        if isinstance(value, (float, np.floating)):
            return "REAL"
        if isinstance(value, (bytes, bytearray, memoryview)):
            return "BLOB"
        if isinstance(value, np.ndarray):
            if value.ndim == 0:
                # Will normalize to scalar; choose based on dtype kind
                kind = value.dtype.kind
                if kind in ("i", "u", "b"):
                    return "INTEGER"
                if kind in ("f",):
                    return "REAL"
                return "BLOB"
            # non-scalar arrays unsupported for sqlite columns here
            return "BLOB"
        # Fallback to TEXT
        return "TEXT"

    def _normalize_value(value):
        # Convert values into SQLite-storable Python types
        if isinstance(value, datetime):
            # ensure tz-aware, then epoch ns
            dt = value
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1_000_000_000)
        if isinstance(value, np.ndarray):
            if value.ndim == 0:
                value = value.item()
            else:
                # unsupported; signal by returning a sentinel
                return None
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, bool):
            return int(value)
        return value

    prepared_statements = {}  # topic -> (insert_sql, num_cols)

    def _table_exists(topic: str) -> bool:
        cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (topic,))
        return cur.fetchone() is not None

    def _get_table_ncols(topic: str) -> int:
        cur = conn.execute("PRAGMA table_info(" + _qident(topic) + ")")
        cols = cur.fetchall()
        return len(cols)

    def _ensure_table_for_message(topic: str, msg_list):
        # Create a table named after the topic with columns c0..c{n-1}
        if _table_exists(topic):
            return _get_table_ncols(topic)
        col_types = []
        for v in msg_list:
            col_types.append(_to_sql_type(v))
        col_defs = []
        for i, t in enumerate(col_types):
            col_defs.append(f"c{i} {t}")
        sql = f"CREATE TABLE IF NOT EXISTS {_qident(topic)} (" + ", ".join(col_defs) + ")"
        conn.execute(sql)
        conn.commit()  # commit DDL immediately
        return len(col_types)
    
    last_commit = time.time()
    while True:
        topic, msg = ZmqCodec.decode(sub.recv_multipart())
        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == "sqlite"):
                l.info(config["short_name"] + " writer got control exit")
                break
            
            check_apply_level(msg, config["short_name"])
            continue


        # Expect messages to be a list/tuple; wrap scalars as single-element list
        payload = msg if isinstance(msg, (list, tuple)) else [msg]

        # Skip messages containing non-scalar ndarrays
        non_scalar_array = any(isinstance(v, np.ndarray) and getattr(v, 'ndim', 1) > 0 for v in payload)
        if non_scalar_array:
            l.error(config["short_name"] + " writer skipping non-scalar array payload for " + topic)
            continue

        if topic in config['subscription_topics']:
            # Ensure table exists and matches payload length
            try:
                ncols = _ensure_table_for_message(topic, payload)
            except Exception as e:
                l.error(config["short_name"] + " writer failed ensuring table for " + topic + ": " + str(e))
                continue

            if len(payload) != ncols:
                l.error(config["short_name"] + " writer payload length mismatch for " + topic + ": got " + str(len(payload)) + ", expected " + str(ncols))
                continue

            # Prepare insert statement if needed
            if topic not in prepared_statements:
                placeholders = ",".join(["?"] * ncols)
                colnames = ",".join([f"c{i}" for i in range(ncols)])
                insert_sql = f"INSERT INTO {_qident(topic)}(" + colnames + ") VALUES (" + placeholders + ")"
                prepared_statements[topic] = (insert_sql, ncols)

            insert_sql, _ = prepared_statements[topic]
            values = []
            for v in payload:
                nv = _normalize_value(v)
                if nv is None:
                    l.error(config["short_name"] + " writer skipping due to unsupported value in payload for " + topic)
                    values = None
                    break
                values.append(nv)
            if values is None:
                continue

            try:
                ins.execute(insert_sql, tuple(values))
            except Exception as e:
                l.error(config["short_name"] + " writer insert failed for " + topic + ": " + str(e))
                continue

            # Commit every second
            current_time = time.time()
            if current_time - last_commit >= 1.0:
                conn.commit()
                last_commit = current_time
        else:
            l.error(config["short_name"] + " writer got unknown topic " + topic)
    l.info(config["short_name"] + " writer exiting")