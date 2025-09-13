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
    detector_based_deleter_process_config,
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
    config = detector_based_deleter_process_config
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
    latest_detection_signal_dt = datetime.min.replace(tzinfo=timezone.utc) + timedelta(seconds=config["seconds_before_keep"])

    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)
        #print(f"detector_based_deleter got message: {topic}")
        #print(f"detector_based_deleter got message: {msg}")
        #sys.stdout.flush()
        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == "del"):
                print("detector_based_deleter got control exit")
                sys.stdout.flush()
                break
            continue
        
        last_msg_time = msg[0]
        if topic == config["detector_name"]:
            dt_utc, detected = msg
            print(f"detector_based_deleter got detection: {dt_utc}, {detected}")
            sys.stdout.flush()
            if detected:
                evict_after_dt = dt_utc + timedelta(seconds=config["seconds_after_keep"])
            
            print(f"detector_based_deleter evict after dt: {evict_after_dt}")
            sys.stdout.flush()
            continue
        
        if topic == config["h264_writer_topic"]:
            print(f"detector_based_deleter got h264 writer message: {msg}")
            sys.stdout.flush()
            potential_evictions.append(msg)
            print(f"detector_based_deleter got potential evictions: {len(potential_evictions)}")
            sys.stdout.flush()
            potential_evictions.sort(key=lambda x: x[0])
            new_potential_evictions = []
            for eviction in potential_evictions:
                # if its in the clear
                if eviction[0] < evict_after_dt:
                    print(f"detector_based_deleter removing eviction: {eviction}")
                    sys.stdout.flush()
                    continue
                # if its not in the grace period
                grace_period_start = last_msg_time - timedelta(seconds=config["seconds_before_keep"])
                print(f"detector_based_deleter grace period start: {grace_period_start}")
                print(f"detector_based_deleter eviction timestamp: {eviction[0]}")
                print(f"the truth is: {eviction[0] <= grace_period_start}")
                sys.stdout.flush()
                if eviction[0] <= grace_period_start:
                    os.remove(eviction[1])
                    print(f"detector_based_deleter deleted {eviction[1]}")
                    sys.stdout.flush()
                    continue
                print(f"detector_based_deleter skipping eviction: {eviction}")
                new_potential_evictions.append(eviction)
                sys.stdout.flush()
                continue
            potential_evictions = new_potential_evictions
                
            print(f"detector_based_deleter has potential evictions: {len(potential_evictions)}")
            sys.stdout.flush()

        print(f"detector_based_deleter got message: {topic}")
        sys.stdout.flush()

    print("detector_based_deleter exiting")
    sys.stdout.flush()


