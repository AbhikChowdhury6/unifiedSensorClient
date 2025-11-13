import time
from datetime import datetime

import importlib.util
import os
import sys
import zmq

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
class_loc = repoPath + "unifiedSensorClient/cameraClasses/"
from platformUtils.zmq_codec import ZmqCodec
import logging
from platformUtils.logUtils import worker_configurer, check_apply_level, set_process_title
from config import video_controller_process_1_config, zmq_control_endpoint

config = video_controller_process_1_config
def load_class_and_instantiate(filepath, class_name, *args, **kwargs):
    module_name = os.path.splitext(os.path.basename(filepath))[0]
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    tcls = getattr(module, class_name)
    instance = tcls(*args, **kwargs)
    return instance

def video_controller(log_queue):
    set_process_title(config["short_name"])
    worker_configurer(log_queue, config["debug_lvl"])
    l = logging.getLogger(config["short_name"])
    l.info(config["short_name"] + " controller starting")

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    l.info(config["short_name"] + " controller connected to control topic")

    camera = load_class_and_instantiate(
        class_loc + config['camera_type_module'] + '.py',
        config['camera_type_class'],
        {"platform_uuid": config['platform_uuid'],
        "bus_location": config['bus_location'],
        "device_name": config['device_name'],
        "sensor_type": config['sensor_type'],
        "units": config['units'],
        "data_type": config['data_type'],
        "data_shape": config['data_shape'],
        "hz": config['hz'],
        "file_writer_config": config['file_writer_config'],
        "debug_lvl": config['debug_lvl'],

        "camera_index": config['camera_index'],
        "camera_width": config['camera_width'],
        "camera_height": config['camera_height'],
        "subsample_ratio": config['subsample_ratio'],
        "format": config['format'],
        "flip_vertical": config['flip_vertical'],
        "timestamp_images": config['timestamp_images'],
        })

    hz = config['fps']
    delay_micros = 1_000_000/hz
    sensor = camera.sensor

    while True:
        sensor.retrieve_data()

        try:
            parts = sub.recv_multipart(flags=zmq.NOBLOCK)
            topic, obj = ZmqCodec.decode(parts)
            if check_apply_level(obj, config["short_name"]):
                continue

            l.debug("video controller message: " + str(topic) + " " + str(obj))
            if topic == "control" and (obj[0] == "exit_all" or (obj[0] == "exit" and obj[-1] == "video")):
                l.info('video controller exiting')
                break
        except zmq.Again:
            # No message available
            pass
        

        micros_to_delay = delay_micros - (datetime.now().microsecond % delay_micros)
        time.sleep(micros_to_delay/1_000_000)

    l.info(config["short_name"] + " controller exiting")