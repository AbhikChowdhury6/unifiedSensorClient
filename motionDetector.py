import sys
import time
import math
import zmq

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec

from config import (
    motion_detector_process_config,
    zmq_control_endpoint,
)

config = motion_detector_process_config
def motion_detector():
    #subscribe to control topic
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    print("motion detector connected to control topic")
    sys.stdout.flush()

    #subscribe to camera topic
    sub.connect(config["camera_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, config["camera_name"].encode())
    print("motion detector connected to camera topic")
    sys.stdout.flush()

    #connect to pub endpoint
    pub = ctx.socket(zmq.PUB)
    pub.bind(config["pub_endpoint"])
    print("motion detector connected to pub topic")
    sys.stdout.flush()

    last_frame = None
    interval_s = float(config.get("interval_seconds", 1))
    threshold = float(config.get("threshold", 50))
    
    next_capture = _compute_next_capture_ts(time.time(), interval_s)
    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)

        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == "motion"):
                print("motion detector got control exit")
                sys.stdout.flush()
                break
            continue
        if topic != config["camera_name"]:
            continue

        dt_utc, frame = msg[0], msg[1]
        if last_frame is None:
            last_frame = frame
            continue

        if dt_utc.timestamp() < next_capture:
            continue

        next_capture = _compute_next_capture_ts(dt_utc.timestamp(), interval_s)

        mean_brightness = (frame - last_frame).mean()
        print(f"motion detector mean difference: {mean_brightness}")
        sys.stdout.flush()
        last_frame = frame
        motion = int(mean_brightness < threshold)
        pub.send_multipart(ZmqCodec.encode(config["pub_topic"], [dt_utc, motion]))


    pub.close(0)
    sub.close(0)
    ctx.term()
    
def _compute_next_capture_ts(now_ts: float, interval_s: float) -> float:
    return int(math.ceil(now_ts / interval_s) * interval_s)