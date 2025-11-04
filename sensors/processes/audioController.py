import os
import sys
import time
from datetime import datetime, timezone

import zmq
import logging

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from platformUtils.logUtils import worker_configurer, set_process_title
from config import (
    zmq_control_endpoint,
    audio_controller_process_config,
)
from platformUtils.zmq_codec import ZmqCodec
from sensors.audio.audioCapture import AudioCapture

config = audio_controller_process_config
def audio_controller(log_queue):
    set_process_title(config["short_name"])
    worker_configurer(log_queue, config["debug_lvl"])
    l = logging.getLogger(config["short_name"])
    l.info(config["short_name"] + " controller starting")

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    l.info(config["short_name"] + " controller connected to control topic")
    

    # Start audio capture publisher
    cap = AudioCapture({
        "short_name": config["short_name"],
        "debug_lvl": config["debug_lvl"],
        "sample_rate": config["sample_rate"],
        "channels": config["channels"],
        "hz": config["hz"],
        "dtype": config["dtype"],
        "pub_topic": config["pub_topic"],
        "pub_endpoint": config["pub_endpoint"],
        "device": config.get("device", None),
    })
    cap.start()
    cap.enable()

    last_publish_check = time.time()
    target_hz = 16
    delay_micros = 1_000_000/target_hz

    try:
        while True:
            # Publish any pending audio frames
            if cap.is_enabled():
                cap.publish_pending()

            try:
                parts = sub.recv_multipart(flags=zmq.NOBLOCK)
                topic, obj = ZmqCodec.decode(parts)
                if topic == "control" and (obj[0] == "exit_all" or (obj[0] == "exit" and obj[-1] == "audio")):
                    l.info(config["short_name"] + " controller exiting")
                    break
            except zmq.Again:
                pass

            micros_to_delay = delay_micros - (datetime.now().microsecond % delay_micros)
            time.sleep(micros_to_delay/1_000_000)
    finally:
        cap.stop()
        try:
            sub.close(0)
        except Exception:
            pass


if __name__ == "__main__":
    audio_controller(None)


