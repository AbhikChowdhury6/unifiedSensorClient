import sys
import zmq
import pigpio

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec

from config import (
    pigpio_toggle_buttons_process_config,
    zmq_control_endpoint,
)

config = pigpio_toggle_buttons_process_config
def pigpio_buttons():
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    print("pigpio buttons connected to control topic")
    sys.stdout.flush()

    pi = pigpio.pi()
    pi.set_mode(config["button_pin"], pigpio.INPUT)
    pi.set_pull_up_down(config["button_pin"], pigpio.PUD_UP)
    print("pigpio buttons connected to button pin")
    sys.stdout.flush()

    last_button_state = pi.read(config["button_pin"])

    while True:
        continue