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
    # ZMQ setup
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    sub.connect(detector_based_deleter_config["detector_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, detector_based_deleter_config["detector_name"].encode())
    print(f"detector_based_deleter subscribed to {detector_based_deleter_config['detector_name']} at {detector_based_deleter_config['detector_endpoint']}")
    sys.stdout.flush()
    
    files = _get_files_in_location(detector_based_deleter_config["files_location"])
    print(f"detector_based_deleter found {len(files)} files in {detector_based_deleter_config['files_location']}")
    sys.stdout.flush()
    
    files_by_second = [_parse_ts_from_filename(file) for file in files if file is not None]
    files_by_second.sort()
    print(f"detector_based_deleter sorted {len(files_by_second)} files by timestamp")
    sys.stdout.flush()
    
