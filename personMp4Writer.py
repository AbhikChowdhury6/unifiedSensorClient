import os
import sys
import zmq
import numpy as np
import cv2
import logging
from datetime import datetime, timezone, timedelta
import pyqoi

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec
from logUtils import worker_configurer, check_apply_level, set_process_title
from config import (
    person_mp4_writer_process_config,
    zmq_control_endpoint,
)

config = person_mp4_writer_process_config
l = logging.getLogger(config["short_name"])
def person_mp4_writer(log_queue):
    set_process_title(config["short_name"])
    worker_configurer(log_queue, config["debug_lvl"])
    l.info(config["short_name"] + " process starting")

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    # Control channel for graceful exit
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")

    # subscribe to all detector topics
    for endpoint in config["detector_endpoints"]:
        sub.connect(endpoint)
    for name in config["detector_names"]:
        sub.setsockopt(zmq.SUBSCRIBE, name.encode())
    l.info(config["short_name"] + " process subscribed to " + str(config['detector_names']) + " at " + str(config['detector_endpoints']))

    # subscribe to the camera topic
    sub.connect(config["camera_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, config["camera_name"].encode())
    l.info(config["short_name"] + " process subscribed to " + config['camera_name'] + " at " + config['camera_endpoint'])

    # connect to the pub endpoint
    pub = ctx.socket(zmq.PUB)
    pub.bind(config["pub_endpoint"])
    l.info(config["short_name"] + " process connected to pub topic")


    fourcc = cv2.VideoWriter_fourcc(*'avc1')
    def dt_to_fnString(dt):
        return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H%M%S,%f%z')
    

    def start_mp4(dt, is_full_speed):
        if is_full_speed:
            path = config["full_speed_location"]
        else:
            path = config["timelapse_location"]
        path = os.path.join(path, dt_to_fnString(dt) + ".mp4")
        output = cv2.VideoWriter(path, 
                        fourcc, 
                        30.0, 
                        (config["camera_width"], config["camera_height"]))
        if not output.isOpened():
            l.error("Failed to open video writer")
            return None
        
        return output, path
    
    def close_mp4(output, is_full_speed, path, last_dt):
        if output is None:
            return
        output.release()
        #rename the file with the end timestamp

    def tl_time_to_write(dt):
        return dt.timestamp() % config["timelapse_interval_seconds"] == 0
    
    
    is_full_speed = False
    last_detection_ts = datetime.min.replace(tzinfo=timezone.utc)
    time_before_seconds = config["time_before_seconds"]
    time_after_seconds = config["time_after_seconds"]
    timelapse_after = last_detection_ts + timedelta(seconds=time_after_seconds)
    output, path = None, None
    last_dt = datetime.min.replace(tzinfo=timezone.utc)
    switch_to_fs = False
    switch_to_tl = False
    start_time = datetime.now(timezone.utc)
    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)
        #check if exiting
        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == "person_mp4"):
                l.info(config["short_name"] + " got control exit")
                break
            continue
        #check if a detection has occurred
        if topic in config["detector_names"]:
            detected = msg[1]
            if detected:
                # set the timing logic here
                timelapse_after = msg[0] + timedelta(seconds=time_after_seconds)
                if not is_full_speed:
                    switch_to_fs = True
                is_full_speed = True
                last_detection_ts = msg[0]
            
            elif timelapse_after < msg[0]:
                if is_full_speed:
                    switch_to_tl = True
                is_full_speed = False
            

        if topic != config["camera_name"]:
            continue
        
        dt_utc, frame = msg[0], msg[1]

        # wait till after the buffer period before writing
        if dt_utc < start_time + timedelta(seconds=time_before_seconds):
            continue
        if output is None:
            output, path = start_mp4(start_time, is_full_speed)

        l.trace(config["short_name"] + " got frame: " + str(dt_utc))


        #handle new day transitions
        if last_dt.date() != dt_utc.date() and not (switch_to_fs or switch_to_tl):
            close_mp4(output, is_full_speed, path, last_detection_ts)
            output, path = start_mp4(dt_utc, True)
        
        # handle video type transitions
        if switch_to_fs:
            close_mp4(output, False, path, last_detection_ts)
            #get the time before seconds timestamp
            tb_dt_utc = dt_utc - timedelta(seconds=time_before_seconds)

            output, path = start_mp4(tb_dt_utc, True)
            #here we need to read the time_before_seconds amount of frames
            # and write them to the output video
            switch_to_fs = False
        elif switch_to_tl:
            close_mp4(output, True, path, last_detection_ts)
            output, path = start_mp4(dt_utc, False)
            switch_to_tl = False


        if not is_full_speed and not tl_time_to_write(dt_utc):
            continue
 

        output.write(frame)
        last_dt = dt_utc

        # how would I like to go about deleting old qoi files?
        # if not is full speed, then I'll delete all but the first one in the last block
        # if is full speed, then I wont delete any
        # whenever an mp4 is closed, I'll delete the qoi files that are older than the mp4 file



