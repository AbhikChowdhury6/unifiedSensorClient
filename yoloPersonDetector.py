import sys
import time
import math
from ultralytics import YOLO

import zmq
import logging

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec
from logUtils import worker_configurer

from config import (
    yolo_person_detector_process_config,
    zmq_control_endpoint,
)

config = yolo_person_detector_process_config
def _compute_next_capture_ts(now_ts: float, interval_s: float) -> float:
    return int(math.ceil(now_ts / interval_s) * interval_s)


def yolo_person_detector(log_queue):
    worker_configurer(log_queue, config["debug_lvl"])
    l = logging.getLogger(config["short_name"])
    l.info(config["short_name"] + " process starting")

    #subscribe to control topic
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    l.info(config["short_name"] + " process connected to control topic")


    #subscribe to camera topic
    sub.connect(config["camera_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, config["camera_name"].encode())
    l.info(config["short_name"] + " process connected to camera topic")


    #connect to pub endpoint
    pub = ctx.socket(zmq.PUB)
    pub.bind(config["pub_endpoint"])
    l.info(config["short_name"] + " process connected to pub topic")


    interval_s = float(config.get("interval_seconds", 4))
    conf_thresh = float(config.get("confidence_threshold", 0.7))
    nms_thresh = float(config.get("nms_threshold", 0.7))

    model_name = config.get("model", "yolo11m")
    model = YOLO(model_name)
    l.info(config["short_name"] + " loaded YOLO model " + model_name)


    next_capture = _compute_next_capture_ts(time.time(), interval_s)
    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)

        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == "yolo"):
                l.info(config["short_name"] + " got control exit")
                break
            continue
        if topic != config["camera_name"]:
            continue

        dt_utc, frame = msg[0], msg[1]

        if dt_utc.timestamp() < next_capture:
            continue

        next_capture = _compute_next_capture_ts(dt_utc.timestamp(), interval_s)

        results = model.predict(source=frame, verbose=config["verbose"], conf=conf_thresh, iou=nms_thresh)

        person_confidence = 0.0
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


        detected = 1 if person_confidence >= conf_thresh else 0
        pub.send_multipart(ZmqCodec.encode(config["pub_topic"], [dt_utc, detected]))
        l.debug(config["short_name"] + " published " + str(detected) + " (person_conf=" + str(person_confidence) + ")")

    l.info(config["short_name"] + " exiting")


if __name__ == "__main__":
    yolo_person_detector(None)


