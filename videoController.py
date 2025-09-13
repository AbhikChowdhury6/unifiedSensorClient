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

def video_controller():
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    print("video controller connected to control topic")
    sys.stdout.flush()

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
            print("video controller message:", topic, obj)
            if topic == "control" and (obj[0] == "exit_all" or (obj[0] == "exit" and obj[-1] == "video")):
                print('video controller exiting')
                break
        except zmq.Again:
            # No message available
            pass
        

        micros_to_delay = delay_micros - (datetime.now().microsecond % delay_micros)
        time.sleep(micros_to_delay/1_000_000)

    print("video controller exiting")
    sys.stdout.flush()