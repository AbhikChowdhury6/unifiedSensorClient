import os
import sys
import zmq
from datetime import datetime, timezone
import numpy as np
import requests

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec
import logging
from logUtils import worker_configurer, check_apply_level

from config import file_uploader_process_config, zmq_control_endpoint
config = file_uploader_process_config
l = logging.getLogger(config["short_name"])

def _parse_ts_from_filename(path: str):
    """Extract UTC timestamp seconds from a data file name.

    Expects names like ..._YYYYMMDDTHHMMSSpMSZ.ext; returns None if unparsable.
    Works whether passed a full path or a base name.
    """
    try:
        base = os.path.basename(path)
        string_time = base.split("_")[-1].split(".")[0]
        if string_time.endswith("Z"):
            string_time = string_time[:-1]
        string_time = string_time.replace("p", ".")
        return datetime.strptime(string_time, "%Y%m%dT%H%M%S.%f").timestamp()
    except Exception:
        return None


def _iter_files_recursive(root_dir: str):
    """Yield absolute file paths under root_dir (recursive)."""
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for fname in filenames:
            yield os.path.join(dirpath, fname)


def _remove_empty_dirs(root_dir: str):
    """Remove empty directories under root_dir (bottom-up), but not root_dir itself."""
    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
        if dirpath == root_dir:
            continue
        try:
            if not dirnames and not filenames:
                os.rmdir(dirpath)
                l.debug(config["short_name"] + " process removed empty directory: " + dirpath)
        except Exception as e:
            l.warning(config["short_name"] + " process failed to remove directory " + dirpath + ": " + str(e))

def _upload_files_in_backlog(time_till_ready: int):
    now_cutoff = datetime.now(timezone.utc).timestamp() - time_till_ready
    candidates = []
    data_root = config["data_dir"]
    num_uploaded = 0
    for full_path in _iter_files_recursive(data_root):
        if not os.path.isfile(full_path):
            continue
        ts = _parse_ts_from_filename(full_path)
        if ts is None:
            continue
        if ts < now_cutoff:
            candidates.append((ts, full_path))

    candidates.sort(key=lambda x: x[0])
    l.debug(config["short_name"] + " process found " + str(len(candidates)) + " files in backlog")
    l.trace(config["short_name"] + " process candidates: " + str(candidates))
    for _, full_path in candidates:
        l.debug(config["short_name"] + " process uploading file: " + full_path)
        _upload_file(full_path)
    num_uploaded += len(candidates)
    _remove_empty_dirs(data_root)
    l.debug(config["short_name"] + " process uploaded files in backlog: " + str(num_uploaded))
    return


def _upload_file(path: str):
    # post to the upload url
    response = requests.post(config["upload_url"], files={"file": open(path, "rb")})
    if response.status_code != 200:
        l.error(config["short_name"] + " process failed to upload file: " + path)
    else:
        l.debug(config["short_name"] + " process uploaded file: " + path)
    # delete the file
    os.remove(path)
    return
def file_uploader(log_queue):
    worker_configurer(log_queue, config["debug_lvl"])
    l.info(config["short_name"] + " process starting")

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    # Wake up at least once per second if no messages arrive
    sub.setsockopt(zmq.RCVTIMEO, 1000)
    for endpoint in config["subscription_endpoints"]:
        sub.connect(endpoint)
    for topic in config["subscription_topics"]:
        sub.setsockopt(zmq.SUBSCRIBE, topic.encode())
    l.info(config["short_name"] + " process subscribed to " + str(config["subscription_topics"]) + " at " + str(config["subscription_endpoints"]))

    while True:
        try:
            parts = sub.recv_multipart()
        except zmq.error.Again:
            # idle tick: check backlog then continue listening
            _upload_files_in_backlog(config["time_till_ready"])
            continue

        topic, msg = ZmqCodec.decode(parts)

        # No payload: treat as idle tick; check backlog then continue
        if msg is None:
            _upload_files_in_backlog(config["time_till_ready"])
            continue
        if check_apply_level(msg, config["short_name"]):
            continue
        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == "file-up"):
                l.info(config["short_name"] + " process got control exit")
                break
            continue
        if topic in config["subscription_topics"]:
            # Writers publish [segment_start_dt, path]; accept either structure
            completed_path = None
            try:
                # msg expected like [dt, path]
                if isinstance(msg, (list, tuple)) and len(msg) >= 2:
                    completed_path = msg[1]
                elif isinstance(msg, str):
                    completed_path = msg
            except Exception:
                completed_path = None
            if isinstance(completed_path, str) and os.path.isfile(completed_path):
                _upload_file(completed_path)
                _remove_empty_dirs(config["data_dir"])
                l.debug(config["short_name"] + " process uploaded file: " + completed_path)
            else:
                l.debug(config["short_name"] + " process got message without valid path: " + str(msg))
    
    l.info(config["short_name"] + " process exiting")

