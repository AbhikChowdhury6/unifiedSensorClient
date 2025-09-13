import os
import sys
import time
import math
from datetime import datetime, timezone
from ultralytics import YOLO

import zmq
import numpy as np

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec

from config import (
    yolo_person_detector_config,
    zmq_control_endpoint,
)


def _compute_next_capture_ts(now_ts: float, interval_s: float) -> float:
    return int(math.ceil(now_ts / interval_s) * interval_s)


def yolo_person_detector():
    cfg = yolo_person_detector_config
    interval_s = float(cfg.get("interval_seconds", 4))
    conf_thresh = float(cfg.get("confidence_threshold", 0.7))
    nms_thresh = float(cfg.get("nms_threshold", 0.7))
    camera_topic = cfg["camera_name"]
    camera_endpoint = cfg["camera_endpoint"]
    pub_endpoint = cfg["pub_endpoint"]
    pub_topic = cfg["pub_topic"]

    # ZMQ setup
    ctx = zmq.Context()

    sub = ctx.socket(zmq.SUB)
    # Keep only latest few frames in buffer
    sub.setsockopt(zmq.RCVHWM, 2)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    sub.connect(camera_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, camera_topic.encode())

    pub = ctx.socket(zmq.PUB)
    pub.bind(pub_endpoint)

    print(f"yolo person detector subscribed to {camera_topic} at {camera_endpoint}")
    print(f"yolo person detector publishing to {pub_topic} at {pub_endpoint}")
    sys.stdout.flush()

    # Load model
    try:
        model_name = cfg.get("model", "yolo11m")
        model = YOLO(model_name)
        print(f"loaded YOLO model {model_name}")
        sys.stdout.flush()
    except Exception as e:
        print(f"failed to load YOLO model: {e}")
        sys.stdout.flush()
        return

    latest_frame = None
    latest_ts = None
    next_capture = _compute_next_capture_ts(time.time(), interval_s)

    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)

        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == "yolo"):
                print("yolo person detector got control exit")
                sys.stdout.flush()
                break
            continue
        if topic != camera_topic:
            continue

        dt_utc, frame = msg[0], msg[1]

        # Keep latest frame only
        latest_frame = frame


        frame_ts_seconds = dt_utc.timestamp()
        #print(f"yolo person detector frame ts seconds: {frame_ts_seconds}, next capture: {next_capture}, latest ts: {latest_ts}")
        #sys.stdout.flush()
        if frame_ts_seconds < next_capture:
            continue

        next_capture = _compute_next_capture_ts(frame_ts_seconds, interval_s)

        # Run detection on this frame
        if not isinstance(latest_frame, np.ndarray):
            continue

        img = latest_frame
        #print(f"yolo person detector img: {img.shape}")
        #sys.stdout.flush()
        if not (img.ndim == 3 and img.shape[2] == 3 and img.dtype == np.uint8):
            continue

        try:
            # YOLO expects RGB by default; convert if needed here
            results = model.predict(source=img, verbose=True, conf=conf_thresh, iou=nms_thresh)
            #print(f"yolo person detector results: {results}")
            #sys.stdout.flush()
        except Exception as e:
            print(f"yolo inference failed: {e}")
            sys.stdout.flush()
            continue

        person_confidence = 0.0
        try:
            # Iterate over detections to find 'person' class
            for r in results:
                boxes = r.boxes
                names = r.names
                if boxes is None:
                    continue
                for cls_id, conf in zip(boxes.cls.tolist(), boxes.conf.tolist()):
                    name = names.get(int(cls_id), str(int(cls_id)))
                    if name.lower() == "person":
                        person_confidence = max(person_confidence, float(conf))
        except Exception as e:
            print(f"postprocess failed: {e}")
            sys.stdout.flush()
            continue

        detected = 1 if person_confidence >= conf_thresh else 0
        pub.send_multipart(ZmqCodec.encode(pub_topic, [dt_utc, detected]))
        print(f"yolo person detector published {detected} (person_conf={person_confidence:.3f})")
        sys.stdout.flush()

    print("yolo person detector exiting")
    sys.stdout.flush()


if __name__ == "__main__":
    yolo_person_detector()


