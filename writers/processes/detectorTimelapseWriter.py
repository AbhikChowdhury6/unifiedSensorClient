import sys
import os
import time
from datetime import datetime, timezone, timedelta

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from platformUtils.zmq_codec import ZmqCodec
from config import zmq_control_endpoint, detector_timelapse_writer_process_config
import zmq
import logging
from platformUtils.logUtils import worker_configurer, set_process_title
from config import dt_to_fnString, fnString_to_dt
from writers.writer import Writer
from writers.videoOutput import video_output
import qoi

config = detector_timelapse_writer_process_config
def detector_timelapse_writer(log_queue):
    set_process_title(config["short_name"])
    worker_configurer(log_queue, config["debug_lvl"])
    l = logging.getLogger(config["short_name"])
    l.info(config["short_name"] + " writer starting")

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    l.info(config["short_name"] + " writer connected to control topic")

    for endpoint in config["detector_endpoints"]:
        sub.connect(endpoint)
    for name in config["detector_topics"]:
        sub.setsockopt(zmq.SUBSCRIBE, name.encode())
    l.info(config["short_name"] + " writer subscribed to " + str(config['detector_topics']) + " at " + str(config['detector_endpoints']))

    sub.connect(config["camera_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, config["camera_topic"].encode())
    l.info(config["short_name"] + " writer subscribed to " + config['camera_topic'] + " at " + config['camera_endpoint'])

    full_speed_output = video_output(config["full_speed_output_config"])
    timelapse_output = video_output(config["timelapse_output_config"])
    
    full_speed_writer = Writer(config["full_speed_output_config"], full_speed_output)
    timelapse_writer = Writer(config["timelapse_output_config"], timelapse_output)

    timelapse_hz = config["timelapse_output_config"]["hz"]


    persist_location = config["cache_location"] + config["short_name"] + "/"
    def persist(dt, frame):
        fn = persist_location + dt_to_fnString(dt) + ".qoi"
        qoi.write(fn, frame)
    
    def load():
        files = [file for file in os.listdir(persist_location).sorted() 
                    if fnString_to_dt(file) < datetime.now(timezone.utc) -\
                        timedelta(seconds=config["time_before_seconds"])]
        
        for file in files:
            data = qoi.read(persist_location + file)
            yield fnString_to_dt(file), data

    def delete_old_files():
        files = os.listdir(persist_location).sorted()
        for file in files:
            if fnString_to_dt(file) < datetime.now(timezone.utc) -\
                timedelta(seconds=config["time_before_seconds"] + 1/timelapse_hz):
                os.remove(persist_location + file)
    
    def get_file(dt):
        fn = dt_to_fnString(dt) + ".qoi"
        if fn in os.listdir(persist_location):
            return qoi.read(persist_location + fn)
        return None

    last_detection_ts = datetime.min.replace(tzinfo=timezone.utc)
    timelapse_after = last_detection_ts + timedelta(seconds=config["time_after_seconds"])
    is_full_speed = False
    switch_to_fs = False
    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)
        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == config["short_name"]):
                l.info(config["short_name"] + " writer exiting")
                break
            continue
        
        if topic in config["detector_topics"]:
            detected = msg[1]
            if detected:
                timelapse_after = msg[0] + timedelta(seconds=config["time_after_seconds"])
                if not switch_to_fs:
                    switch_to_fs = True
                is_full_speed = True
                last_detection_ts = msg[0]
            
            elif timelapse_after < msg[0]: #switch to timelapse
                if is_full_speed:
                    switch_to_tl = True
                    next_timelapse_frame_to_write = msg[0] + timedelta(seconds=1)
                    next_timelapse_frame_update = msg[0] + timedelta(seconds=1/timelapse_hz)
                is_full_speed = False
        
        if topic != config["camera_topic"]:
            continue
        
        dt_utc, frame = msg[0], msg[1]

        if switch_to_fs:
            #catch up on time before seconds amount of frames
            for dt, fr in load():
                full_speed_writer.write(dt, fr)
            delete_old_files()
            curr_timelapse_frame = None
            switch_to_fs = False
            is_full_speed = True
        

        if is_full_speed:
            full_speed_writer.write(dt_utc, frame)
            continue
        
        #it's a timelapse, presist in case we need to switch to full speed
        persist(dt_utc, frame)

        if switch_to_tl:
            
            timelapse_writer.write(dt_utc, frame) #write to a timelapse video
            latest_timelapse_frame = frame
            next_timelapse_frame_to_write = dt_utc + timedelta(seconds=1)
            next_timelapse_frame_update = dt_utc + timedelta(seconds=1/timelapse_hz)
            switch_to_tl = False
            continue
        

        #upsample writes to every second
        if dt_utc < next_timelapse_frame_to_write:
            continue


        time_before_name = dt_to_fnString(dt_utc - timedelta(seconds=config["ti"]))
        #check if the time before seconds frame exists
        if time_before_name in os.listdir(persist_location):
            curr_timelapse_frame = qoi.read(persist_location + time_before_name + ".qoi")
            timelapse_writer.write(dt_utc, curr_timelapse_frame)
            delete_old_files()
            continue

        if curr_timelapse_frame is not None:
            timelapse_writer.write(dt_utc, curr_timelapse_frame)

