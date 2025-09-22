import sys
import zmq
import time
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec

from config import led_controller_process_config, zmq_control_endpoint
config = led_controller_process_config

import board
import neopixel_spi

pixels = neopixel_spi.NeoPixel_SPI(board.SPI(), 10, auto_write=False)

def led_controller():
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    print("led controller connected to control topic")
    sys.stdout.flush()

    pub = ctx.socket(zmq.PUB)
    pub.connect(config["pub_endpoint"])
    print("led controller connected to pub on controltopic")
    sys.stdout.flush()

    def _should_exit(obj):
        return obj[0] == "exit_all" or (obj[0] == "exit" and obj[1] == process)

    obj = [None, None, None]
    while True:
        #for each led, send the status requests and wait for a response
        for led in config["states"]:
            relevant_states = config["states"][led]
            relevant_processes = list(set([state[1] for state in relevant_states]))
            
            current_states = set()
            for process in relevant_processes:
                #send a status request and wait for a response
                pub.send_multipart(ZmqCodec.encode(config["pub_topic"], ["status", process]))
                
                #wait for a response
                start_time = time.time()
                while True:
                    topic, obj = ZmqCodec.decode(sub.recv_multipart())
                    if topic == "control" and obj[0] == "status" and obj[1] == process:
                        current_states.add((obj[2], process))
                        break
                    
                    if topic == "control" and _should_exit(obj):
                        print(f"led controller got exit for {process}")
                        sys.stdout.flush()
                        break

                    if time.time() - start_time > 1:
                        print(f"led controller timed out waiting for {process} status")
                        sys.stdout.flush()
                        break
            
                if _should_exit(obj):
                    break

            if _should_exit(obj):
                break

            led_vals = [k for k, v in relevant_states.items() if v == current_states]
            if led_vals:
                pixels[led] = led_vals[0]
            else:
                pixels[led] = (0, 0, 0)
                print(f"led controller no valid states for led {led}")
                sys.stdout.flush()
        
        if _should_exit(obj):
            break
        
        pixels.show()
        time.sleep(1)
    
    print("led controller exiting")
    sys.stdout.flush()
    pub.close(0)
    sub.close(0)
    ctx.term()