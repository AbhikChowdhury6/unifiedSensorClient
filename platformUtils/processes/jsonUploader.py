import os
import sys
import zmq
import json
import logging
from datetime import datetime, timezone
import sqlite3

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from platformUtils.zmq_codec import ZmqCodec
from platformUtils.logUtils import worker_configurer, set_process_title
from config import (
    sqlite_writer_write_location,
    zmq_control_endpoint
)
def json_uploader(log_queue, config):
    l = logging.getLogger(config["short_name"])
    set_process_title(config["short_name"])
    worker_configurer(log_queue, config["debug_lvl"])
    l.info(config["short_name"] + " process starting")

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")

    #so in this one we'll
    #check the sqlite database for up to 10MB of entries
    #read them (keeping track of their keys)
    #package them into a json object
    #send them to the server
    #delete the entries from the database
    #repeat this every 1 second
    conn = sqlite3.connect(f"{sqlite_writer_write_location}data.db")
    ins = conn.cursor()
    while True:
        try:
            parts = sub.recv_multipart()
        except zmq.error.Again:
            continue
        topic, msg = ZmqCodec.decode(parts)
        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == "json-up"):
                l.info(config["short_name"] + " process got control exit")
                break
        















