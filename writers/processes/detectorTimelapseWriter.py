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
    time_after_seconds = config["time_after_seconds"]
    time_before_seconds = config["time_before_seconds"]
    detection_grace_period = timedelta(seconds=8)
    seconds_till_irrelvance = timedelta(seconds=time_before_seconds + 1/timelapse_hz) + detection_grace_period
    last_frame_dt = datetime.min.replace(tzinfo=timezone.utc)
    timelapse_frame_offset = timedelta(seconds=time_before_seconds + 1/timelapse_hz)


    persist_location = config["temp_file_location"] + config["short_name"] + "-persist/"
    os.makedirs(persist_location, exist_ok=True)
    def persist(dt, data):
        for i in range(data.shape[0]):
            frame_dt = dt + timedelta(seconds=i/full_speed_output_config["hz"])
            fn = persist_location + dt_to_fnString(frame_dt) + ".qoi"
            l.trace(" writer persisting frame: " + str(frame_dt))
            qoi.write(fn, data[i])
    
    #full speed writes all the files in prsist 
    #that are after or on the time before seconds from the given dt_utc
    #but also before the time after seconds from the given dt_utc
    def load(dt_utc):#for when we switch to full speed
        
        l.debug("dt_utc: " + str(dt_utc))
        l.debug("time before seconds: " + str(time_before_seconds))
        time_before_dt = dt_utc - timedelta(seconds=time_before_seconds)
        l.debug("time before datetime: " + str(time_before_dt))
        time_after_dt = dt_utc + timedelta(seconds=time_after_seconds)
        l.debug("time after datetime: " + str(time_after_dt))
        
        files = [file for file in sorted(os.listdir(persist_location)) 
                    if fnString_to_dt(file) >= time_before_dt and 
                    fnString_to_dt(file) < time_after_dt]
        
        l.trace(" writer loading " + str(len(files)) + " files")
        if len(files) > 0:
            f_dts = [fnString_to_dt(file) for file in files]
            l.debug(" writer loading files from: " + str(min(f_dts)) + " to " + str(max(f_dts)))
        
        for file in files:
            data = qoi.read(persist_location + file)
            data = np.expand_dims(data, axis=0)
            full_speed_writer.write(fnString_to_dt(file), data)

    #will delete all of the files in the persist
    #that are before seconds_till_irrelvance from the given dt_utc
    def delete_old_files(dt_utc):
        files = sorted(os.listdir(persist_location))
        
        l.debug("dt_utc: " + str(dt_utc))
        l.debug("seconds till irrelvance: " + str(seconds_till_irrelvance))
        l.debug("irrelvance datetime: " + str(dt_utc - seconds_till_irrelvance))
        
        dts = []
        for file in files:
            dt = fnString_to_dt(file)
            dts.append(dt)
            if dt < dt_utc -\
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
    


    
    min_dt = datetime.min.replace(tzinfo=timezone.utc) + seconds_till_irrelvance
    #if there are left over files from the last run, write them to the full speed video
    for dt, fr in load(min_dt):
        l.trace(" writer writing full speed frame: " + str(dt))
        full_speed_writer.write(dt, fr)
    delete_old_files(min_dt)

    
    #if there are
    last_detection_dt = datetime.min.replace(tzinfo=timezone.utc)
    is_full_speed = False
    switch_to_fs = False

    last_positive_detection_dt = datetime.min.replace(tzinfo=timezone.utc)
    fs_expires_dt = datetime.min.replace(tzinfo=timezone.utc)
    timelapse_write_dt = datetime.min.replace(tzinfo=timezone.utc)
    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)
        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == config["short_name"]):
                l.info(" writer exiting")
                break
            continue
        
        #check if we got a positive detection
        if topic in config["detector_topics"]:
            if msg[0] < last_frame_dt - detection_grace_period:
                l.warning("detected frame too old: " + str(msg[0]) + " < " + str(last_frame_dt))

                continue

            if last_detection_dt < msg[0]:
                l.warning("got an out of order detection: " + str(last_detection_dt) + " < " + str(msg[0]))
                continue

            detected = msg[1]
            l.debug(" writer detected: " + str(detected) + " at " + str(msg[0]) + " UTC")
            last_detection_dt = msg[0]
            if not detected:
                continue
            
            last_positive_detection_dt = msg[0]
            #what is this even being used for?
            #when to stop automatically writing all of the fullspeed frames (brfore this time)
            fs_expires_dt = msg[0] + timedelta(seconds=time_after_seconds)
            
            #another detected signal could come in up until this point
            #and if it comes in before or at this point, we'll keep full speed
            stitch_delay = time_after_seconds + time_before_seconds
            
            #the dt to write the first timelapse frame
            timelapse_write_dt = msg[0] + timedelta(seconds=stitch_delay)
            #once this dt passes, we'll write timelapse frames at curr_time - Time before seconds
            #there'll be separate logic for deciding what frame to write (if it's a duplicate or an updated frame)


            l.trace(" fs expires at: " + str(fs_expires_dt))
            if not is_full_speed:
                switch_to_fs = True
                l.trace(" writer switching to full speed")
            is_full_speed = True
        
            
            continue
        
        #ignore unknown topics
        if topic != config["camera_topic"]:
            continue
        
        

        if switch_to_fs:
            l.info(" writer switching to full speed")
            #close the timelapse writer if it's open
            timelapse_writer.close()

            #catch up on time before seconds amount of frames
            load(last_positive_detection_dt)
            delete_old_files(last_positive_detection_dt)
            
            curr_timelapse_frame = None
            switch_to_fs = False
            is_full_speed = True
        

        dt_utc, frame = msg[0], msg[1]
        
        if dt_utc < fs_expires_dt:
            l.trace(" writer writing full speed frame: " + str(dt_utc))
            full_speed_writer.write(dt_utc, frame)
            continue
        
        #we'll persist the frame so we can switch back to full speed if needed
        persist(dt_utc, frame)
        
        if dt_utc < timelapse_write_dt:
            continue
        elif full_speed_writer.file_name is not None:
            # we are now officially writing timelapse frames
            full_speed_writer.close()
        is_full_speed = False
        
        if dt_utc.microsecond != 0:
            continue

        if dt_utc >= next_timelapse_frame_update:
            curr_timelapse_frame = get_file(dt_utc - timelapse_frame_offset)
            if curr_timelapse_frame is None:
                l.error(" writer no frame found for " + str(dt_utc - timelapse_frame_offset))
                continue
            l.debug(" writer updating timelapse frame for " + str(dt_utc - timelapse_frame_offset))
            delete_old_files(dt_utc)
            next_timelapse_frame_update += timedelta(seconds=1/timelapse_hz)
        
        frame_dt = dt_utc - timelapse_frame_offset
        l.debug(" writer writing timelapse frame at " + str(frame_dt))
        timelapse_writer.write(frame_dt, curr_timelapse_frame)
        
        

    
    l.info(" writer closing")
    timelapse_writer.close()
    full_speed_writer.close()

