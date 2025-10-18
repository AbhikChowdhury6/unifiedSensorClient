import time
from datetime import datetime

import importlib.util
import os
import sys
import zmq

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
class_loc = repoPath + "unifiedSensorClient/cameraClasses/"
from zmq_codec import ZmqCodec
import logging
from logUtils import worker_configurer, check_apply_level
from config import video_controller_process_config, zmq_control_endpoint

config = video_controller_process_config
def load_class_and_instantiate(filepath, class_name, *args, **kwargs):
    module_name = os.path.splitext(os.path.basename(filepath))[0]
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    tcls = getattr(module, class_name)
    instance = tcls(*args, **kwargs)
    return instance

def video_controller(log_queue):
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
        config)

    hz = config['fps']
    delay_micros = 1_000_000/hz
    camera.enable()

    while True:
        if camera.is_enabled():
            camera.capture()
        
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