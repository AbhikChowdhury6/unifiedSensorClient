import sys
import time
import math
from ultralytics import YOLO

import zmq

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec

from config import (
    yolo_person_detector_process_config,
    zmq_control_endpoint,
)

config = yolo_person_detector_process_config
def _compute_next_capture_ts(now_ts: float, interval_s: float) -> float:
    return int(math.ceil(now_ts / interval_s) * interval_s)


def yolo_person_detector():
    #subscribe to control topic
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    print("yolo person detector connected to control topic")
    sys.stdout.flush()

    #subscribe to camera topic
    sub.connect(config["camera_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, config["camera_name"].encode())
    print("yolo person detector connected to camera topic")
    sys.stdout.flush()

    #connect to pub endpoint
    pub = ctx.socket(zmq.PUB)
    pub.bind(config["pub_endpoint"])
    print("yolo person detector connected to pub topic")
    sys.stdout.flush()


    interval_s = float(config.get("interval_seconds", 4))
    conf_thresh = float(config.get("confidence_threshold", 0.7))
    nms_thresh = float(config.get("nms_threshold", 0.7))

    model_name = config.get("model", "yolo11m")
    model = YOLO(model_name)
    print(f"loaded YOLO model {model_name}")
    sys.stdout.flush()


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
        print(f"yolo person detector published {detected} (person_conf={person_confidence:.3f})")
        sys.stdout.flush()

    print("yolo person detector exiting")
    sys.stdout.flush()


if __name__ == "__main__":
    yolo_person_detector()


