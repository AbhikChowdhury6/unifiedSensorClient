import os
import sys
import time
import math
from datetime import datetime, timezone

import zmq
import numpy as np
import cv2
import logging

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec
from logUtils import worker_configurer, set_process_title
from config import (
    jpeg_writer_process_config,
    zmq_control_endpoint,
)
config = jpeg_writer_process_config


def _format_ts_for_filename(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts_utc = ts.astimezone(timezone.utc)
    # Match h264 writer naming with millisecond precision
    return ts_utc.strftime("%Y%m%dT%H%M%S") + "p" + str(ts_utc.microsecond // 1000).zfill(3) + "Z"


def _compute_next_capture_ts(now_ts: float, interval_s: float) -> float:
    # Assumes interval_s evenly divides 86400
    return int(math.ceil(now_ts / interval_s) * interval_s)


def jpeg_writer(log_queue):
    set_process_title(config["short_name"])
    worker_configurer(log_queue, config["debug_lvl"])
    l = logging.getLogger(config["short_name"])
    l.setLevel(config["debug_lvl"])
    l.info(config["short_name"] + " writer starting")
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)

    # Drop old frames: keep only the latest couple per pipe
    sub.setsockopt(zmq.RCVHWM, 2)

    # Control
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")

    # Camera frames
    camera_topic = config["camera_name"]
    camera_endpoint = config["camera_endpoint"]
    sub.connect(camera_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, camera_topic.encode())
    l.info(config["short_name"] + " subscribed to " + camera_topic + " at " + camera_endpoint)

    write_location = config["write_location"]
    image_interval_s = float(config.get("image_interval_seconds", 60))
    if 86400 % image_interval_s != 0:
        raise ValueError(f"image_interval_seconds ({image_interval_s}) must evenly divide 86400 for day alignment")
    quality = int(config.get("quality", 80))
    fmt = config.get("format", "RGB888")

    os.makedirs(write_location, exist_ok=True)

    latest_frame = None
    latest_ts = None
    now = time.time()
    next_capture = _compute_next_capture_ts(now, image_interval_s)
    l.debug(config["short_name"] + " next capture: " + str(next_capture))
    capture_tolerance_s = float(config.get("capture_tolerance_seconds", 0.25))


    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)

        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == "jpeg"):
                l.info(config["short_name"] + " got control exit")
                break
            continue
        
        if topic != camera_topic:
            continue

        ts, frame = msg[0], msg[1]
        l.debug(config["short_name"] + " got frame: " + str(ts))

        # Keep raw latest; process only if we will write
        latest_frame = frame
        # Normalize timestamp to aware datetime for naming when writing
        if isinstance(ts, datetime):
            latest_ts = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
        else:
            latest_ts = datetime.fromtimestamp(ts / 1_000_000_000, tz=timezone.utc)

        # Work in seconds for comparisons
        frame_ts_seconds = latest_ts.timestamp()
        l.debug(config["short_name"] + " frame ts seconds: " + str(frame_ts_seconds) + ", next capture: " + str(next_capture) + ", latest ts: " + str(latest_ts))
        
        if frame_ts_seconds >= next_capture:
            # Reschedule to the aligned time closest to the frame timestamp
            next_capture = _compute_next_capture_ts(frame_ts_seconds, image_interval_s)
            l.debug(config["short_name"] + " next capture: " + str(next_capture))
            should_write = False
            ts_diff = abs(frame_ts_seconds - (next_capture - image_interval_s))
            if ts_diff <= capture_tolerance_s:
                should_write = True
            l.debug(config["short_name"] + " should write: " + str(should_write))
            if should_write:
                # Validate and convert only now
                frame_to_write = latest_frame
                if not isinstance(frame_to_write, np.ndarray) or frame_to_write.ndim != 3 or frame_to_write.shape[2] != 3:
                    pass
                else:
                    if not frame_to_write.flags["C_CONTIGUOUS"]:
                        frame_to_write = np.ascontiguousarray(frame_to_write)
                    if frame_to_write.dtype != np.uint8:
                        frame_to_write = frame_to_write.astype(np.uint8, copy=False)
                    if fmt.upper() in ("RGB888", "RGB24", "RGB"):
                        frame_to_write = cv2.cvtColor(frame_to_write, cv2.COLOR_RGB2BGR)

                    ts_str = _format_ts_for_filename(latest_ts)
                    # Write into UTC hourly folders: YYYY/MM/DD/HH/MM/
                    hourly_subdir = latest_ts.astimezone(timezone.utc).strftime("%Y/%m/%d/%H/%M/")
                    out_dir = os.path.join(write_location, hourly_subdir)
                    os.makedirs(out_dir, exist_ok=True)
                    filename = f"{config["file_base"]}_{ts_str}.jpeg"
                    filepath = os.path.join(out_dir, filename)
                    try:
                        cv2.imwrite(filepath, frame_to_write, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
                        l.debug(config["short_name"] + " saved " + filepath)
                    except Exception as e:
                        l.error(config["short_name"] + " failed to save " + filepath + ": " + str(e))

    l.info(config["short_name"] + " exiting")


if __name__ == "__main__":
    jpeg_writer(None)


