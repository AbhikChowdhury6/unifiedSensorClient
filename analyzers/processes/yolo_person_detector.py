import sys
import time
import math
from ultralytics import YOLO
from datetime import datetime
import zmq


from platformUtils.zmq_codec import ZmqCodec
from platformUtils.utils import configure_process, should_exit


def _compute_next_capture_dt(now_dt: datetime, interval_s: float) -> datetime:
    return int(math.ceil(now_dt.timestamp() / interval_s) * interval_s)


def yolo_person_detector(config_name):
    ctx = zmq.Context()
    l, sub, config = configure_process(ctx, config_name)
    l.info(config_name + " process starting")


    #subscribe to camera topic
    l.info(" camera endpoint: " + config["camera_endpoint"])
    l.info(" camera topic: " + config["camera_topic"])
    sub.connect(config["camera_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, config["camera_topic"].encode())
    l.info(" process connected to camera topic")


    #connect to pub endpoint
    pub = ctx.socket(zmq.PUB)
    pub.bind(config["pub_endpoint"])
    l.info(" process connected to pub topic")


    interval_s = float(config.get("interval_seconds", 4))
    conf_thresh = float(config.get("confidence_threshold", 0.7))

    model_name = config.get("model", "yolo11m")
    model = YOLO(model_name)
    l.info(" loaded YOLO model " + model_name)


    next_capture = None


    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)

        if should_exit(topic,msg, config_name):
            l.info(config_name + " got control exit")
            break

        if topic != config["camera_topic"]:
            continue

        dt_utc, frame = msg[0], msg[1]
        l.trace("got frame: " + str(dt_utc))
        
        if next_capture is None:
            next_capture = _compute_next_capture_dt(dt_utc, interval_s)
        
        if dt_utc.timestamp() < next_capture:
            l.trace("frame is too early, skipping")
            continue

        next_capture = None #it computes the next capture based on the next frame
        l.trace("next capture: " + str(next_capture))


        l.trace("starting inference")
        start_time = time.time()
        results = model.predict(frame[0], verbose=config["verbose"])

        l.debug(" inference completed in " + str(time.time() - start_time) + " seconds")
        
        indexesOfPeople = [i for i, x in enumerate(results[0].boxes.cls) if x == 0]
        if len(indexesOfPeople) > 0:
            l.debug("saw %d people",len(indexesOfPeople))
            sys.stdout.flush()
            maxPersonConf = max([results[0].boxes.conf[i] for i in indexesOfPeople])
            l.debug("the most confident recognition was %f", maxPersonConf)
            if maxPersonConf > conf_thresh:
                detected = 1
            else:
                detected = 0
        else:
            l.debug("didn't see anyone")
            detected = 0


        pub.send_multipart(ZmqCodec.encode(config["pub_topic"], [dt_utc, detected]))
        l.debug("published %d at %s", detected, str(dt_utc))


    l.info("exiting")



if __name__ == "__main__":
    config_name = sys.argv[1]
    yolo_person_detector(config_name)
