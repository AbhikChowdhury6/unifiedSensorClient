import os
import sys
import time
import math
from datetime import datetime, timezone

import zmq
import numpy as np
import cv2

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec

from config import (
    jpeg_writer_config,
    platform_uuid,
    zmq_control_endpoint,
)


def _format_ts_for_filename(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts_utc = ts.astimezone(timezone.utc)
    # Match h264 writer naming with millisecond precision
    return ts_utc.strftime("%Y%m%dT%H%M%S") + "p" + str(ts_utc.microsecond // 1000).zfill(3) + "Z"


def _seconds_in_year(year: int) -> int:
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    next_start = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    return int((next_start - start).total_seconds())


def _compute_next_capture(now_ts: float, interval_s: float) -> float:
    # Choose the largest alignment period divisible by interval: year > day > hour > minute
    now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
    seconds_year = _seconds_in_year(now_dt.year)
    anchor_ts = None
    if seconds_year % interval_s == 0:
        anchor_ts = datetime(now_dt.year, 1, 1, tzinfo=timezone.utc).timestamp()
    elif 86400 % interval_s == 0:
        anchor_ts = datetime(now_dt.year, now_dt.month, now_dt.day, tzinfo=timezone.utc).timestamp()
    elif 3600 % interval_s == 0:
        anchor_ts = datetime(now_dt.year, now_dt.month, now_dt.day, now_dt.hour, tzinfo=timezone.utc).timestamp()
    elif 60 % interval_s == 0:
        anchor_ts = datetime(now_dt.year, now_dt.month, now_dt.day, now_dt.hour, now_dt.minute, tzinfo=timezone.utc).timestamp()
    else:
        # Fallback align to epoch
        anchor_ts = 0.0

    # Next multiple of interval after now relative to anchor
    k = math.ceil((now_ts - anchor_ts) / interval_s)
    return anchor_ts + k * interval_s


def _compute_anchor_ts(interval_s: float, ts_seconds: float) -> float:
    dt = datetime.fromtimestamp(ts_seconds, tz=timezone.utc)
    seconds_year = _seconds_in_year(dt.year)
    if seconds_year % interval_s == 0:
        return datetime(dt.year, 1, 1, tzinfo=timezone.utc).timestamp()
    if 86400 % interval_s == 0:
        return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc).timestamp()
    if 3600 % interval_s == 0:
        return datetime(dt.year, dt.month, dt.day, dt.hour, tzinfo=timezone.utc).timestamp()
    if 60 % interval_s == 0:
        return datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, tzinfo=timezone.utc).timestamp()
    return 0.0


def _nearest_aligned_capture(ts_seconds: float, interval_s: float) -> float:
    anchor = _compute_anchor_ts(interval_s, ts_seconds)
    k = round((ts_seconds - anchor) / interval_s)
    return anchor + k * interval_s


def jpeg_writer():
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)

    # Drop old frames: keep only the latest
    sub.setsockopt(zmq.RCVHWM, 1)
    try:
        sub.setsockopt(zmq.CONFLATE, 1)
    except Exception:
        # CONFLATE may not be available in some builds; HWM still helps
        pass

    # Control
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")

    # Camera frames
    camera_topic = jpeg_writer_config["camera_name"]
    camera_endpoint = jpeg_writer_config["camera_endpoint"]
    sub.connect(camera_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, camera_topic.encode())

    write_location = jpeg_writer_config["write_location"]
    image_interval_s = float(jpeg_writer_config.get("image_interval_seconds", 60))
    quality = int(jpeg_writer_config.get("quality", 80))
    fmt = jpeg_writer_config.get("format", "RGB888")

    os.makedirs(write_location, exist_ok=True)

    latest_frame = None
    latest_ts = None
    now = time.time()
    next_capture = _compute_next_capture(now, image_interval_s)
    capture_tolerance_s = float(jpeg_writer_config.get("capture_tolerance_seconds", 0.25))

    print(f"jpeg writer subscribed to {camera_topic} at {camera_endpoint}")
    sys.stdout.flush()

    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)

        if topic == "control":
            if msg == "exit":
                print("jpeg writer got control exit")
                sys.stdout.flush()
                break
            continue
        
        if topic != camera_topic:
            continue

        ts, frame = msg[0], msg[1]

        # Keep raw latest; process only if we will write
        latest_frame = frame
        # Normalize timestamp to aware datetime for naming when writing
        if isinstance(ts, datetime):
            latest_ts = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
        else:
            latest_ts = datetime.fromtimestamp(ts / 1_000_000_000, tz=timezone.utc)

        if latest_ts >= next_capture:
            # Reschedule to the aligned time closest to the frame timestamp
            frame_ts_seconds = latest_ts.timestamp()
            nearest = _nearest_aligned_capture(frame_ts_seconds, image_interval_s)
            next_capture = nearest if nearest >= frame_ts_seconds else _compute_next_capture(frame_ts_seconds, image_interval_s)

            should_write = False
            ts_diff = abs(frame_ts_seconds - next_capture)
            if ts_diff <= capture_tolerance_s:
                should_write = True

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
                    filename = f"{platform_uuid}_{camera_topic}_{ts_str}.jpeg"
                    filepath = os.path.join(write_location, filename)

                    try:
                        cv2.imwrite(filepath, frame_to_write, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
                        print(f"jpeg writer saved {filepath}")
                        sys.stdout.flush()
                    except Exception as e:
                        print(f"jpeg writer failed to save {filepath}: {e}")
                        sys.stdout.flush()

            # Schedule the next aligned capture (strictly after current)
            next_capture = _compute_next_capture(next_capture + 1e-6, image_interval_s)

    print("jpeg writer exiting")
    sys.stdout.flush()


if __name__ == "__main__":
    jpeg_writer()


