import sys
import time
import math
import zmq

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec

from config import (
    is_dark_detector_process_config,
    zmq_control_endpoint,
)

config = is_dark_detector_process_config
def is_dark_detector():
    #subscribe to control topic
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    print("is dark detector connected to control topic")
    sys.stdout.flush()

    #subscribe to camera topic
    camera_topic = config["camera_name"]
    camera_endpoint = config["camera_endpoint"]
    sub.connect(camera_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, camera_topic.encode())
    print("is dark detector connected to camera topic")
    sys.stdout.flush()

    #connect to pub endpoint
    pub = ctx.socket(zmq.PUB)
    pub.bind(config["pub_endpoint"])
    print("is dark detector connected to pub topic")
    sys.stdout.flush()
    pub_topic = config["pub_topic"]
    

    interval_s = float(config.get("interval_seconds", 1))
    threshold = float(config.get("threshold", 0.5))
    

    next_capture = _compute_next_capture_ts(time.time(), interval_s)
    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)

        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == "dark"):
                print("is dark detector got control exit")
                sys.stdout.flush()
                break
            continue
        if topic != camera_topic:
            continue

        dt_utc, frame = msg[0], msg[1]

        if dt_utc.timestamp() < next_capture:
            continue

        next_capture = _compute_next_capture_ts(dt_utc.timestamp(), interval_s)

        mean_brightness = frame.mean()
        print(f"is dark detector mean brightness: {mean_brightness}")
        sys.stdout.flush()
        is_dark = int(mean_brightness < threshold)
        pub.send_multipart(ZmqCodec.encode(pub_topic, [dt_utc, is_dark]))


    pub.close(0)
    sub.close(0)
    ctx.term()
    
def _compute_next_capture_ts(now_ts: float, interval_s: float) -> float:
    return int(math.ceil(now_ts / interval_s) * interval_s)