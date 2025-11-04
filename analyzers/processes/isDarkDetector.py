import sys
import time
import math
import zmq
import logging

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from platformUtils.zmq_codec import ZmqCodec
from platformUtils.logUtils import worker_configurer, set_process_title
from config import (
    is_dark_detector_process_config,
    zmq_control_endpoint,
)
config = is_dark_detector_process_config
l = logging.getLogger(config["short_name"])

def is_dark_detector(log_queue):
    set_process_title(config["short_name"])
    worker_configurer(log_queue, config["debug_lvl"])
    l.info(config["short_name"] + " process starting")

    #subscribe to control topic
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    l.info(config["short_name"] + " process connected to control topic")

    #subscribe to camera topic
    sub.connect(config["camera_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, config["camera_name"].encode())
    l.info(config["short_name"] + " process connected to camera topic")

    #connect to pub endpoint
    pub = ctx.socket(zmq.PUB)
    pub.bind(config["pub_endpoint"])
    l.info(config["short_name"] + " process connected to pub topic")


    interval_s = float(config.get("interval_seconds", 1))
    threshold = float(config.get("threshold", 0.5))
    
    next_capture = _compute_next_capture_ts(time.time(), interval_s)
    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)

        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == "dark"):
                l.info(config["short_name"] + " process got control exit")
                break
            continue
        if topic != config["camera_name"]:
            continue

        dt_utc, frame = msg[0], msg[1]

        if dt_utc.timestamp() < next_capture:
            continue

        next_capture = _compute_next_capture_ts(dt_utc.timestamp(), interval_s)

        mean_brightness = frame.mean()
        l.debug(config["short_name"] + " process mean brightness: " + str(mean_brightness))
        is_dark = int(mean_brightness < threshold)
        pub.send_multipart(ZmqCodec.encode(config["pub_topic"], [dt_utc, is_dark]))


    pub.close(0)
    sub.close(0)
    ctx.term()
    l.info(config["short_name"] + " process exiting")
def _compute_next_capture_ts(now_ts: float, interval_s: float) -> float:
    return int(math.ceil(now_ts / interval_s) * interval_s)