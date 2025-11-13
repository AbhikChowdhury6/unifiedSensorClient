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

def writer_process(log_queue, 
                    topic,
                    msg_hz,
                    output_hz,
                    output_base,
                    output_module,
                    additional_output_config = {},
                    debug_lvl = "warning",
                    ):
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
    last_dt = datetime.min.replace(tzinfo=timezone.utc)
    last_data = None
    if msg_hz < 1:
        interp_seconds = 1/msg_hz
        #if it's 800ms into the second, assume the data isn't coming
        sub.setsockopt(zmq.RCVTIMEO, 800) 


    wc = file_writer_process_info

    output_module_name = file_output_infos[output_module]["module_name"]
    importlib.import_module(output_module_name)
    output_class = getattr(output_module_name, output_module_name)
    output = output_class(**additional_output_config,
                          output_base=output_base,
                          output_hz=output_hz,
                          temp_write_location=wc["temp_write_location"],
                          debug_lvl=debug_lvl)
    
    writer = Writer(output=output,
                    temp_write_location=wc["temp_write_location"],
                    output_write_location=wc["output_write_location"],
                    target_file_size=wc["target_file_size"],
                    file_size_check_interval_s_range=wc["file_size_check_interval_s_range"],
                    debug_lvl=debug_lvl)
    while True:
        msg_topic, msg = ZmqCodec.decode(sub.recv_multipart())

        if msg_topic == "control" and (msg[0] == "exit_all" or 
                (msg[0] == "exit" and msg[-1] == process_name)):
            l.info(process_name + " exiting")
            break

        if msg_topic != topic:
            continue


        dt, chunk = msg

        if interp_seconds == 0: #if we got new data
            writer.write(dt, chunk)
            continue

        if dt != last_dt:
            writer.write(dt, chunk)
            last_dt = dt
            last_data = chunk
            #if we're interpolating, and got new data, wait till the end of the second
            # so we don't try to intpolate the same second
            time.sleep(max(0, (dt.replace(microsecond=0).timestamp() + 1 - datetime.now().timestamp())))
            continue
        
        #until the end of the interp_seconds, we'll write the last data
        curr_dt = datetime.now(timezone.utc).replace(microsecond=0)
        if curr_dt < last_dt + timedelta(seconds=interp_seconds):
            writer.write(curr_dt, last_data)
        
        #if it for some reason took longer than 200ms to write, don't wait
        time.sleep(max(0, curr_dt.timestamp() + 1 - datetime.now().timestamp()))
        


    l.info(process_name + " exiting")
    writer.close()
