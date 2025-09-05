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


def audioController():
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    print("audio controller connected to control topic")
    sys.stdout.flush()

    # Start audio capture publisher
    cap = AudioCapture({
        "sample_rate": 16000,
        "channels": 1,
        "hz": 16,
        "dtype": "int16",
        "pub_topic": audio_publisher_config["pub_topic"],
        "pub_endpoint": audio_publisher_config["pub_endpoint"],
    })
    cap.start()

    last_publish_check = time.time()

    try:
        while True:
            # Publish any pending audio frames
            cap.publish_pending()

            try:
                parts = sub.recv_multipart(flags=zmq.NOBLOCK)
                topic, obj = ZmqCodec.decode(parts)
                if topic == "control" and obj == "exit":
                    print("audio controller exiting")
                    sys.stdout.flush()
                    break
            except zmq.Again:
                pass

            time.sleep(0.01)
    finally:
        cap.stop()
        try:
            sub.close(0)
        except Exception:
            pass


if __name__ == "__main__":
    audioController()


