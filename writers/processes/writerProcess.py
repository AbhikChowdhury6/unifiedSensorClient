import os
import sys
import time
import subprocess
import threading
from datetime import datetime, timezone, timedelta

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from platformUtils.zmq_codec import ZmqCodec
from config import zmq_control_endpoint,\
     dt_to_fnString, fnString_to_dt
import zmq
import logging
import numpy as np
from platformUtils.logUtils import worker_configurer, set_process_title
from writers.writer import Writer
import pickle


def writer_process(log_queue, config, output):
    l = logging.getLogger(config["topic"])
    set_process_title(config["topic"])
    worker_configurer(log_queue, config["debug_lvl"])
    l.info(config["topic"] + " writer starting")

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    
    sensor_endpoint = f"ipc:///tmp/{config['topic']}.sock"
    sub.connect(sensor_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, config["topic"].encode())
    l.info(config["topic"] + " writer subscribed to " + config["topic"])


    writer = Writer(config, output)
    while True:
        topic, msg = ZmqCodec.decode(sub.recv_multipart())

        if topic == "control" and (msg[0] == "exit_all" or 
                (msg[0] == "exit" and msg[-1] == config["file_base"]+"_writer-process")):
            l.info(config["file_base"] + "_writer-process exiting")
            break

        if topic != config["topic"]:
            continue

        dt, chunk = msg
        writer.write(dt, chunk)

    l.info(config["topic"] + " writer exiting")
    writer.close()
