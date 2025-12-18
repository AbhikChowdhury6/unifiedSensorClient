import sys
import time
from datetime import datetime, timezone, timedelta

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from platformUtils.zmq_codec import ZmqCodec
from config import zmq_control_endpoint, file_writer_process_info, file_output_infos
import zmq
import logging
from platformUtils.logUtils import worker_configurer, set_process_title
from writers.writer import Writer
import importlib

def writer_process(log_queue = None, 
                    topic = None,
                    msg_hz = None,
                    output_hz = None,
                    output_base = None,
                    output_module = None,
                    file_size_check_interval_s_range = (30, 60),
                    additional_output_config = {},
                    debug_lvl = 30,
                    **kwargs
                    ):
    if log_queue is None:
        raise ValueError("log_queue is required")
    process_name = topic + "_writer-process"
    l = logging.getLogger(process_name)
    set_process_title(process_name)
    worker_configurer(log_queue, debug_lvl)
    l.info(process_name + " starting")

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    
    sensor_endpoint = f"ipc:///tmp/{topic}.sock"
    sub.connect(sensor_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, topic.encode())
    l.info(process_name + " subscribed to " + topic)

    interp_seconds = 0
    interped_messages = 0
    last_dt = datetime.min.replace(tzinfo=timezone.utc)
    last_data = None
    if msg_hz is None and output_hz is not None:
        msg_hz = output_hz
    if msg_hz < 1:
        interp_seconds = 1/msg_hz
        #if it's 800ms into the second, assume the data isn't coming
        sub.setsockopt(zmq.RCVTIMEO, 800) 


    wc = file_writer_process_info
    
    # Dynamically import the output module using its fully qualified module path
    output_info = file_output_infos[output_module]
    output_module = importlib.import_module(output_info["module_path"])
    output_ctor = getattr(output_module, output_info["func_name"])
    if debug_lvl <= 5: start_time = datetime.now().timestamp()
    output = output_ctor(**additional_output_config,
                         output_base=output_base,
                         output_hz=output_hz,
                         temp_write_location=wc["temp_write_location"],
                         debug_lvl=debug_lvl)
    if debug_lvl <= 5:
        l.trace(process_name + " output constructor time: " + str(datetime.now().timestamp() - start_time))
    
    if debug_lvl <= 5: start_time = datetime.now().timestamp()
    writer = Writer(output=output,
                    temp_write_location=wc["temp_write_location"],
                    output_write_location=wc["output_write_location"],
                    target_file_size=wc["target_file_size"],
                    file_size_check_interval_s_range=file_size_check_interval_s_range,
                    platform_uuid=wc["platform_uuid"],
                    debug_lvl=debug_lvl)
    if debug_lvl <= 5:
        l.trace(process_name + " writer constructor time: " + str(datetime.now().timestamp() - start_time))
    
    def sleep_to_next_second():
        next_second_ts = datetime.now(timezone.utc).replace(microsecond=0).timestamp() + 1
        time.sleep(next_second_ts - datetime.now().timestamp())

    while True:
        #handle no interploation
        if not interp_seconds:
            msg_topic, msg = ZmqCodec.decode(sub.recv_multipart())
            if msg_topic == "control" and (msg[0] == "exit_all" or 
                (msg[0] == "exit" and msg[-1] == process_name)):
                l.info(process_name + " exiting")
                break
            
            if msg_topic != topic:
                continue

            dt, chunk = msg
            writer.write(dt, chunk)
            continue


        #handle interpolating
        msg_topic = None
        msg = None
        try:
            msg_topic, msg = ZmqCodec.decode(sub.recv_multipart())
        except zmq.Again:
            l.trace(process_name + " no message available")
            #if we're interpolating, and we have never gotten data, sleep to the next second
            if last_data is None:
                sleep_to_next_second()
                continue
        
        #at this stage, we either got a message, or recev timed out and we should interpolate
        
        #if we got a message, handle it
        if msg_topic is not None: #we either got a control message or new data
            if msg_topic == "control" and (msg[0] == "exit_all" or 
                (msg[0] == "exit" and msg[-1] == process_name)):
                l.info(process_name + " exiting")
                break
            
            if msg_topic != topic: #don't sleep if we didn't get new data
                continue

            dt, chunk = msg
            writer.write(dt, chunk)
            interped_messages = 0
            last_dt = dt
            last_data = chunk
            sleep_to_next_second()
            continue


        #at this point, we are interpolating, and recev timed out
        interped_messages += 1

        if interped_messages > interp_seconds:
            #it's been too long, sleep to the next second and don't write anything
            sleep_to_next_second()
            continue
        
        #write the interpolated data
        interp_time = last_dt +timedelta(seconds=interped_messages)
        writer.write(interp_time, last_data)
        
        #if it for some reason took longer than 200ms to write, don't wait
        next_second_ts = datetime.now(timezone.utc).replace(microsecond=0).timestamp() + 1
        time.sleep(max(0, next_second_ts - datetime.now().timestamp()))
        

    l.info(process_name + " exiting")
    writer.close()
