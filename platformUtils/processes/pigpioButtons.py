import sys
import zmq
import pigpio
import time

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from platformUtils.zmq_codec import ZmqCodec

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

    pub = ctx.socket(zmq.PUB)
    pub.bind(config["button_endpoint"])
    print("pigpio buttons connected to button endpoint")
    sys.stdout.flush()

    pi = pigpio.pi()

    for pin in config["set_high_pins"]:
        pi.set_mode(pin, pigpio.OUTPUT)
        pi.write(pin, 1)
    for pin in config["set_low_pins"]:
        pi.set_mode(pin, pigpio.OUTPUT)
        pi.write(pin, 0)
    for pin, sense in config["button_sense_pins"]:
        pi.set_mode(pin, pigpio.INPUT)
        pi.set_pull_up_down(pin, pigpio.PUD_UP if sense == "up" else pigpio.PUD_DOWN)

    print("pigpio buttons connected to button pins")
    sys.stdout.flush()

    num_buttons = len(config["button_sense_pins"])
    instruction_indexes = [0] * num_buttons

    def _send_instructions(instructions):
        for i in instructions:
            pub.send_multipart(ZmqCodec.encode("control", i))
            print(f"sent instruction: {i}")
            sys.stdout.flush()

    while True:
        # check for the leading edge of a button push
        for i, (pin, sense) in enumerate(config["button_sense_pins"]):
            if (sense == "up" and pi.read(pin) == 0) or (sense == "down" and pi.read(pin) == 1):
                _send_instructions(config["button_message_map"][pin][instruction_indexes[i]])
                instruction_indexes[i] = (instruction_indexes[i] + 1) % len(config["button_message_map"][pin])
                print(f"button {pin} pressed, instruction_indexes: {instruction_indexes}")
                sys.stdout.flush()
        time.sleep(.1) # debounce
