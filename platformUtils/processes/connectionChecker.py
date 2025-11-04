import sys
import zmq
import time
import subprocess

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from platformUtils.zmq_codec import ZmqCodec

from config import connection_check_process_config, zmq_control_endpoint
config = connection_check_process_config

def connection_check():
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    print("connection checker connected to control topic")
    sys.stdout.flush()

    pub = ctx.socket(zmq.PUB)
    pub.bind(config["pub_endpoint"])
    print("connection checker connected to pub topic")
    sys.stdout.flush()

    interval_s = float(config.get("interval_seconds", 1))
    states = config["states"]

    last_check = time.time()
    while True:
        #check if there is a connection
        if not subprocess.check_output(["iwgetid", "-r"]).decode("utf-8").strip():
            pub.send_multipart(ZmqCodec.encode(config["pub_topic"], [states[0]]))
            sys.stdout.flush()
            continue


        #check the ssid of the current connection
        ssid = subprocess.check_output(["iwgetid", "-r"]).decode("utf-8").strip()
        if ssid in config["ssids"]:
            pub.send_multipart(ZmqCodec.encode(config["pub_topic"], [states[config["ssids"].index(ssid)]]))
            sys.stdout.flush()
            continue

        if time.time() - last_check > interval_s:
            last_check = time.time()
            pub.send_multipart(ZmqCodec.encode(config["pub_topic"], [states[0]]))
            sys.stdout.flush()

        time.sleep(interval_s)