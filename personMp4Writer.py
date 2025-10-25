import os
import sys
import zmq
import numpy as np
import cv2
import logging
from datetime import datetime, timezone, timedelta

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
        
        return output
    
    def close_mp4(output, is_full_speed):
        if output is not None:
            output.release()
        #rename the file with the end timestamp
    
    
    is_full_speed = False
    last_detection_ts = datetime.min.replace(tzinfo=timezone.utc)
    time_before_seconds = config["time_before_seconds"]
    time_after_seconds = config["time_after_seconds"]
    timelapse_after = last_detection_ts + timedelta(seconds=time_after_seconds)
    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)
        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == "person_mp4"):
                l.info(config["short_name"] + " got control exit")
                break
            continue
        if topic in config["detector_names"]:
            detected = msg[1]
            if detected:
                # set the timing logic here
                timelapse_after = msg[0] + timedelta(seconds=time_after_seconds)
                if not is_full_speed:
                    #close the current mp4 file if open
                    pass
                    #open a new mp4 file that's a full speed
                    pass
                is_full_speed = True
                last_detection_ts = msg[0]
            
            elif timelapse_after < msg[0]:
                if is_full_speed:
                    pass
                    #close the current mp4 file if open
                is_full_speed = False
                #open a new mp4 file that's a timelapse


        # use the last detection timestamp to determine if we should be in full speed
        
        if topic != config["camera_name"]:
            continue
        dt_utc, frame = msg[0], msg[1]
        l.trace(config["short_name"] + " got frame: " + str(dt_utc))



