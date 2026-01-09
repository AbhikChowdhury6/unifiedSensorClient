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
    l.debug(process_name + " subscribed to control on endpoint: " + zmq_control_endpoint)
    
    sensor_endpoint = f"ipc:///tmp/{topic}.sock"
    sub.connect(sensor_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, topic.encode())
    l.info(process_name + " subscribed to " + topic)


    if "file_writer_process_info" in kwargs:
        wc = kwargs["file_writer_process_info"]
    else:
        wc = file_writer_process_info

    l.debug(process_name + " additional_output_config: " + str(additional_output_config))
    
    if "output_info" in kwargs:
        output_info = kwargs["output_info"][output_module]
    else:
        output_info = file_output_infos[output_module]
    
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
        msg_topic, msg = ZmqCodec.decode(sub.recv_multipart())
        if msg_topic == "control" and (msg[0] == "exit_all" or 
            (msg[0] == "exit" and msg[-1] == process_name)):
            l.info(process_name + " exiting")
            break
        
        if msg_topic != topic:
            continue

        dt, chunk = msg
        writer.write(dt, chunk)



    l.info(process_name + " exiting")
    writer.close()
