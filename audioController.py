import os
import sys
import time
from datetime import datetime, timezone

import zmq

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")

from config import (
    zmq_control_endpoint,
    audio_publisher_config,
)
from zmq_codec import ZmqCodec
from audioCapture import AudioCapture


def audio_controller():
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    print("audio controller connected to control topic")
    sys.stdout.flush()

    # Start audio capture publisher
    cap = AudioCapture({
        "sample_rate": audio_publisher_config["sample_rate"],
        "channels": audio_publisher_config["channels"],
        "hz": audio_publisher_config["hz"],
        "dtype": audio_publisher_config["dtype"],
        "pub_topic": audio_publisher_config["pub_topic"],
        "pub_endpoint": audio_publisher_config["pub_endpoint"],
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
                if topic == "control" and obj == "exit":
                    print("audio controller exiting")
                    sys.stdout.flush()
                    break
                if topic == audio_publisher_config['pub_topic']:
                    if obj == "enable":
                        cap.enable()
                    if obj == "disable":
                        cap.disable()
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
    audioController()


