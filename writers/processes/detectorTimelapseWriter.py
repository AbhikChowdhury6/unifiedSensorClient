import sys
import os
import time
from datetime import datetime, timezone, timedelta
import numpy as np

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from platformUtils.zmq_codec import ZmqCodec
from config import zmq_control_endpoint
import zmq
import logging
from platformUtils.logUtils import worker_configurer, set_process_title
from config import dt_to_fnString, fnString_to_dt, file_writer_process_info
from writers.writer import Writer
from writers.videoOutput import video_output
import qoi

def detector_timelapse_writer(log_queue, config):
    #set up logging
    set_process_title(config["short_name"])
    worker_configurer(log_queue, config["debug_lvl"])
    l = logging.getLogger(config["short_name"])
    l.setLevel(config["debug_lvl"])
    l.info(config["short_name"] + " writer starting")

    #set up connections
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    l.info(" writer connected to control topic")

    for endpoint in config["detector_endpoints"]:
        sub.connect(endpoint)
    for name in config["detector_topics"]:
        sub.setsockopt(zmq.SUBSCRIBE, name.encode())
    l.info(" writer subscribed to " + str(config['detector_topics']) + " at " + str(config['detector_endpoints']))

    sub.connect(config["camera_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, config["camera_topic"].encode())
    l.info(" writer subscribed to " + config['camera_topic'] + " at " + config['camera_endpoint'])


    #set up outputs and writers
    full_speed_output_config = config["full_speed_output_config"]
    timelapse_output_config = config["timelapse_output_config"]

    full_speed_output = video_output(**full_speed_output_config, **file_writer_process_info)
    timelapse_output = video_output(**timelapse_output_config, **file_writer_process_info)
    
    full_speed_writer = Writer(**full_speed_output_config, **file_writer_process_info, output=full_speed_output)
    timelapse_writer = Writer(**timelapse_output_config, **file_writer_process_info, output=timelapse_output)

    #some fields for controlling the flow of the writer
    timelapse_hz = config["timelapse_output_config"]["hz"]
    seconds_till_irrelvance = timedelta(seconds=config["time_before_seconds"] + 1/timelapse_hz)


    persist_location = config["temp_file_location"] + config["short_name"] + "-persist/"
    os.makedirs(persist_location, exist_ok=True)
    def persist(dt, data):
        for i in range(data.shape[0]):
            frame_dt = dt + timedelta(seconds=i/full_speed_output_config["hz"])
            fn = persist_location + dt_to_fnString(frame_dt) + ".qoi"
            l.trace(" writer persisting frame: " + str(frame_dt))
            qoi.write(fn, data[i])
    
    def load():#for when we switch to full speed
        files = [file for file in sorted(os.listdir(persist_location)) 
                    if fnString_to_dt(file) <= datetime.now(timezone.utc) -\
                        timedelta(seconds=config["time_before_seconds"])]
        
        l.trace(" writer loading " + str(len(files)) + " files")
        for file in files:
            data = qoi.read(persist_location + file)
            data = np.expand_dims(data, axis=0)
            yield fnString_to_dt(file), data

    def delete_old_files():
        files = sorted(os.listdir(persist_location))
        dts = []
        for file in files:
            dt = fnString_to_dt(file)
            dts.append(dt)
            if dt < datetime.now(timezone.utc) -\
                seconds_till_irrelvance:
                l.trace(" writer deleting old file: " + str(file))
                os.remove(persist_location + file)
        l.debug(" writer deleted " + str(len(dts)) + " old files")
        if len(dts) == 0:
            return
        l.debug(" writer deleted files from: " + str(min(dts)) + " to " + str(max(dts)))
    
    def get_file(dt):
        fn = dt_to_fnString(dt) + ".qoi"
        if fn in os.listdir(persist_location):
            data = qoi.read(persist_location + fn)
            data = np.expand_dims(data, axis=0)
            return data
        return None
    


    
    #if there are left over files from the last run, write them to the full speed video
    for dt, fr in load():
        l.trace(" writer writing full speed frame: " + str(dt))
        full_speed_writer.write(dt, fr)
    delete_old_files()

    
    #if there are
    last_detection_ts = datetime.min.replace(tzinfo=timezone.utc)
    timelapse_after = last_detection_ts + timedelta(seconds=config["time_after_seconds"])
    is_full_speed = False
    switch_to_fs = False
    switch_to_tl = True
    start_writing_after = None
    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)
        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == config["short_name"]):
                l.info(" writer exiting")
                break
            continue
        
        if topic in config["detector_topics"]:
            detected = msg[1]
            l.debug(" writer detected: " + str(detected))
            if detected:
                timelapse_after = msg[0] + timedelta(seconds=config["time_after_seconds"])
                l.trace(" writer timelapse after: " + str(timelapse_after))
                if not is_full_speed:
                    switch_to_fs = True
                    l.trace(" writer switching to full speed")
                is_full_speed = True
                last_detection_ts = msg[0]
            
            elif timelapse_after < msg[0]: #switch to timelapse
                if is_full_speed:
                    switch_to_tl = True
                    l.trace(" writer switching to timelapse")
                is_full_speed = False
        
        if topic != config["camera_topic"]:
            continue
        
        dt_utc, frame = msg[0], msg[1]

        if switch_to_fs:
            l.info(" writer switching to full speed")
            #catch up on time before seconds amount of frames
            l.info(" writer catching up on " + str(config["time_before_seconds"]) + " seconds of frames")
            dts = []
            for dt, fr in load():
                dts.append(dt)
                l.trace(" writer writing full speed frame: " + str(dt))
                full_speed_writer.write(dt, fr)
            l.info(" writer caught up on " + str(len(dts)) + " frames")
            l.debug(" writer caught up on frames from: " + str(min(dts)) + " to " + str(max(dts)))
            delete_old_files()
            curr_timelapse_frame = None
            switch_to_fs = False
            is_full_speed = True
        

        if is_full_speed:
            l.trace(" writer writing full speed frame: " + str(dt_utc))
            full_speed_writer.write(dt_utc, frame)
            continue
        
        #it's a timelapse, presist in case we need to switch to full speed
        l.trace(" writer persisting timelapse frame: " + str(dt_utc))
        persist(dt_utc, frame)

        if switch_to_tl:
            l.info(" writer switching to timelapse")
            start_writing_after = dt_utc + seconds_till_irrelvance
            next_timelapse_frame_update = start_writing_after
            switch_to_tl = False
            continue

        if dt_utc < start_writing_after:
            l.trace(" writer waiting for frame after: " + str(start_writing_after))
            continue

        #upsample writes to every second
        if dt_utc.microsecond != 0:
            l.trace(" writer skipping frame with microsecond: " + str(dt_utc.microsecond))
            continue

        if dt_utc >= next_timelapse_frame_update:
            l.trace(" writer updating timelapse frame for " + str(dt_utc - seconds_till_irrelvance))
            curr_timelapse_frame = get_file(dt_utc - seconds_till_irrelvance)
            if curr_timelapse_frame is None:
                l.error(" writer no frame found for " + str(dt_utc - seconds_till_irrelvance))
                continue
            l.debug(" writer updating timelapse frame for " + str(dt_utc - seconds_till_irrelvance))
            delete_old_files()
            next_timelapse_frame_update += timedelta(seconds=1/timelapse_hz)

        frame_dt = dt_utc - seconds_till_irrelvance
        l.debug(" writer writing timelapse frame at " + str(frame_dt))
        timelapse_writer.write(frame_dt, curr_timelapse_frame)
    
    l.info(" writer closing")
    timelapse_writer.close()
    full_speed_writer.close()

