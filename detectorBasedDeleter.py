import os
import sys
import time
import bisect
from datetime import datetime, timezone, timedelta
import logging
import zmq

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec
from logUtils import worker_configurer
from config import (
    detector_based_deleter_process_config,
    zmq_control_endpoint,
)
config = detector_based_deleter_process_config
l = logging.getLogger(config["short_name"])


def _safe_cfg_get(cfg, key, default):
    """Get a config value, or default if not present."""
    if key in cfg:
        return cfg[key]
    l.warning(config["short_name"] + " deleter: config missing '" + key + "', using default " + str(default))
    return default



def _parse_ts_from_filename(path: str):
    string_time = path.split("_")[-1].split(".")[0]
    string_time = string_time.replace("p", ".")
    return datetime.strptime(string_time, "%Y%m%dT%H%M%S.%f").timestamp()


def _get_files_in_location(location: str):
    return [f for f in os.listdir(location) if os.path.isfile(os.path.join(location, f))]


def detector_based_deleter(log_queue):
    worker_configurer(log_queue, config["debug_lvl"])
    l.info(config["short_name"] + " deleter starting")

    # ZMQ setup
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    for endpoint in config["detector_endpoints"]:
        sub.connect(endpoint)
    for name in config["detector_names"]:
        sub.setsockopt(zmq.SUBSCRIBE, name.encode())
    l.info(config["short_name"] + " deleter subscribed to " + str(config['detector_names']) + " at " + str(config['detector_endpoints']))

    sub.connect(config["mp4_writer_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, config["mp4_writer_topic"].encode())
    l.info(config["short_name"] + " deleter subscribed to " + config['mp4_writer_topic'] + " at " + config['mp4_writer_endpoint'])
    
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
                l.info(config["short_name"] + " deleter got control exit")
                break
            continue
        
        last_msg_time = msg[0]
        if topic in config["detector_names"]:
            dt_utc, detected = msg
            l.debug(config["short_name"] + " deleter got detection: " + str(dt_utc) + ", " + str(detected))
            if detected:
                evict_after_dt = dt_utc + timedelta(seconds=config["seconds_after_keep"])
            
            l.debug(config["short_name"] + " deleter evict after dt: " + str(evict_after_dt))
            continue
        
        if topic == config["mp4_writer_topic"]:
            l.debug(config["short_name"] + " deleter got mp4 writer message: " + str(msg))
            potential_evictions.append(msg)
            l.debug(config["short_name"] + " deleter got potential evictions: " + str(len(potential_evictions)))
            potential_evictions.sort(key=lambda x: x[0])
            new_potential_evictions = []
            for eviction in potential_evictions:
                # if its in the clear
                if eviction[0] < evict_after_dt:
                    l.debug(config["short_name"] + " deleter removing eviction: " + str(eviction))
                    continue
                # if its not in the grace period
                grace_period_start = last_msg_time - timedelta(seconds=config["seconds_before_keep"])
                l.debug(config["short_name"] + " deleter grace period start: " + str(grace_period_start))
                l.debug(config["short_name"] + " deleter eviction timestamp: " + str(eviction[0]))
                l.debug(config["short_name"] + " deleter the truth is: " + str(eviction[0] <= grace_period_start))
                if eviction[0] <= grace_period_start:
                    os.remove(eviction[1])
                    l.debug(config["short_name"] + " deleter deleted " + str(eviction[1]))
                    continue
                l.debug(config["short_name"] + " deleter skipping eviction: " + str(eviction))
                new_potential_evictions.append(eviction)
                continue
            potential_evictions = new_potential_evictions
                
            l.debug(config["short_name"] + " deleter has potential evictions: " + str(len(potential_evictions)))

        l.debug(config["short_name"] + " deleter got message: " + str(topic))

    l.info(config["short_name"] + " deleter exiting")


