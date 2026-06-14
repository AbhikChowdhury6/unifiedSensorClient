import time
from datetime import datetime

import importlib.util
import os
import sys
import zmq

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from platformUtils.zmq_codec import ZmqCodec
from platformUtils.utils import configure_process, should_exit

def load_class_and_instantiate(filepath, class_name, l, *args, **kwargs):
    module_name = os.path.splitext(os.path.basename(filepath))[0]
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    tcls = getattr(module, class_name)
    instance = tcls(*args, **kwargs)
    return instance

def video_controller(config_name):
    ctx = zmq.Context()
    l, sub, config = configure_process(ctx, config_name)
    l.info(config_name + " controller starting")

    fwc = config['file_writer_config']

    camera = load_class_and_instantiate(
        config['camera_class_loc'] + config['camera_module_name'] + '.py',
        config['camera_class_name'],
        l,
        **{
            "bus_location": config['bus_location'],
            "device_name": config['device_name'],
            "sensor_type": config['sensor_type'],
            "units": config['units'],
            "data_type": config['data_type'],
            "shape": config['shape'],
            "hz": config['hz'],
            "log_queue": None,
            "file_writer_config": fwc,
            "debug_lvl": config['debug_lvl'],
            "camera_index": config['camera_index'],
            "camera_width": config['camera_width'],
            "camera_height": config['camera_height'],
            "subsample_ratio": config['subsample_ratio'],
            "format": config['format'],
            "flip_vertical": config['flip_vertical'],
            "timestamp_images": config['timestamp_images'],
        })

    l.trace("camera initialized")
    hz = config.get('fps', config['hz'])
    delay_micros = 1_000_000/hz
    sensor = camera.sensor
    l.trace(delay_micros)

    while True:
        l.trace("retrieving data")
        sensor.read_data()

        try:
            parts = sub.recv_multipart(flags=zmq.NOBLOCK)
            topic, obj = ZmqCodec.decode(parts)
            l.debug("video controller message: " + str(topic) + " " + str(obj))
            if should_exit(topic, obj, config_name):
                break
        except zmq.Again:
            # No message available
            pass
        

        micros_to_delay = delay_micros - (datetime.now().microsecond % delay_micros)
        l.trace("sleeping for " + str(micros_to_delay) + " microseconds")
        time.sleep(micros_to_delay/1_000_000)

    l.info(config_name + " controller exiting")

if __name__ == "__main__":
    config_name = sys.argv[1]
    video_controller(config_name)