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
    process_name = config["topic"] + "_writer-process"
    l = logging.getLogger(process_name)
    set_process_title(process_name)
    worker_configurer(log_queue, config["debug_lvl"])
    l.info(process_name + " starting")

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    
    sensor_endpoint = f"ipc:///tmp/{config['topic']}.sock"
    sub.connect(sensor_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, config["topic"].encode())
    l.info(process_name + " subscribed to " + config["topic"])

    hz = config["hz"]
    interp_seconds = 0
    last_dt = datetime.min.replace(tzinfo=timezone.utc)
    last_data = None
    if hz < 1:
        interp_seconds = 1/hz
        sub.setsockopt(zmq.RCVTIMEO, 900) 

    #TODO
    #subsample and write every second if desired (barometric pressure and IMU)
        #no longer as needed for now with the new persist method
    #automatically interpolate to the second as needed (1hz timeout on messages
    # that will resend the last data with the next second timestamp)
    #look out for commands to stop the output
    #look out for commands to start the output

    #we'll need another process to listen to the detectors

    writer = Writer(config, output)
    while True:
        topic, msg = ZmqCodec.decode(sub.recv_multipart())

        if topic == "control" and (msg[0] == "exit_all" or 
                (msg[0] == "exit" and msg[-1] == process_name)):
            l.info(process_name + " exiting")
            break

        if topic != config["topic"]:
            continue


        dt, chunk = msg

        if interp_seconds == 0 or dt != last_dt: #if we got new data
            writer.write(dt, chunk)
            last_dt = dt
            last_data = chunk
            continue
        
        #until the end of the interp_seconds, we'll write the last data
        curr_dt = datetime.now(timezone.utc).replace(microsecond=0)
        if curr_dt < last_dt + timedelta(seconds=interp_seconds):
            writer.write(curr_dt, last_data)
        
        #sleep for microseconds until the start of the next second
        time.sleep((1 - datetime.now().microsecond/1_000_000))
        


    l.info(process_name + " exiting")
    writer.close()
