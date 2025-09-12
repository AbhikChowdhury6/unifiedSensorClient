import os
import sys
import time
import bisect
from datetime import datetime, timezone, timedelta

import zmq

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec

from config import (
    detector_based_deleter_config,
    zmq_control_endpoint,
)


def _safe_cfg_get(cfg, key, default):
    """Get a config value, or default if not present."""
    if key in cfg:
        return cfg[key]
    print(f"detector_based_deleter: config missing '{key}', using default {default}")
    sys.stdout.flush()
    return default



def _parse_ts_from_filename(path: str):
    string_time = path.split("_")[-1].split(".")[0]
    string_time = string_time.replace("p", ".")
    return datetime.strptime(string_time, "%Y%m%dT%H%M%S.%f").timestamp()


def _get_files_in_location(location: str):
    return [f for f in os.listdir(location) if os.path.isfile(os.path.join(location, f))]


def detector_based_deleter():
    config = detector_based_deleter_config
    # ZMQ setup
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    sub.connect(config["detector_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, config["detector_name"].encode())
    print(f"detector_based_deleter subscribed to {config['detector_name']} at {config['detector_endpoint']}")
    sys.stdout.flush()

    sub.connect(config["h264_writer_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, config["h264_writer_topic"].encode())
    print(f"detector_based_deleter subscribed to {config['h264_writer_topic']} at {config['h264_writer_endpoint']}")
    sys.stdout.flush()
    
    #initialize to min datetime
    evict_after_dt = datetime.min.replace(tzinfo=timezone.utc)
    potential_evictions = []
    latest_detection_dt = datetime.min.replace(tzinfo=timezone.utc) + timedelta(seconds=config["seconds_before_keep"])

    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)
        print(f"detector_based_deleter got message: {topic}")
        print(f"detector_based_deleter got message: {msg}")
        sys.stdout.flush()
        if topic == "control":
            if msg == "exit":
                print("detector_based_deleter got control exit")
                sys.stdout.flush()
                break
            continue
        if topic == config["detector_name"]:
            dt_utc, detected = msg
            if detected:
                evict_after_dt = dt_utc + timedelta(seconds=config["seconds_after_keep"])
                latest_detection_dt = dt_utc
            continue
        if topic == config["h264_writer_topic"]:
            potential_evictions.append(msg)

            potential_evictions.sort(key=lambda x: x[0])
            for eviction in potential_evictions:
                if eviction[0] < evict_after_dt:
                    potential_evictions.remove(eviction)
                    continue
                if eviction[0] > latest_detection_dt - timedelta(seconds=config["seconds_before_keep"]):
                    continue
                os.remove(eviction[1])
                print(f"detector_based_deleter deleted {eviction[1]}")
                sys.stdout.flush()
                potential_evictions.remove(eviction)
            continue
        print(f"detector_based_deleter got message: {topic}")
        sys.stdout.flush()

    print("detector_based_deleter exiting")
    sys.stdout.flush()


