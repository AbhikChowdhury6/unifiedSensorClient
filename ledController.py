import sys
import zmq
import time
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec
import logging
from logUtils import worker_configurer, check_apply_level
from config import led_controller_process_config, zmq_control_endpoint
config = led_controller_process_config
l = logging.getLogger(config["short_name"])

import board
import neopixel_spi

pixels = neopixel_spi.NeoPixel_SPI(board.SPI(), 10, auto_write=False)

def led_controller(log_queue):
    worker_configurer(log_queue, config["debug_lvl"])
    l.info(config["short_name"] + " controller starting")


    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    sub.setsockopt(zmq.RCVTIMEO, 100)
    l.info(config["short_name"] + " controller connected to control topic")

    pub = ctx.socket(zmq.PUB)
    pub.connect(config["pub_endpoint"])
    l.info(config["short_name"] + " controller connected to pub on control topic")
    # Give PUB-SUB time to exchange subscriptions to avoid initial drops
    time.sleep(0.05)

    def _should_exit(obj):
        return obj[0] == "exit_all" or (obj[0] == "exit" and obj[1] == process)

    obj = [None, None, None]
    while True:
        #for each led, send the status requests and wait for a response
        for led in config["states"]:
            relevant_states = config["states"][led]
            l.trace("led: " + str(led) + " relevant states: " + str(relevant_states))
            # Extract unique process short names from the sets of (status, process) tuples
            relevant_processes = list({proc for state_set in relevant_states.values() for _, proc in state_set})
            l.trace("led: " + str(led) + " relevant processes: " + str(relevant_processes))
            
            current_states = set()
            for process in relevant_processes:
                #send a status request and wait for a response
                pub.send_multipart(ZmqCodec.encode(config["pub_topic"], ["status", process]))
                l.debug(config["short_name"] + " controller sent status request for " + str(process))
                
                #wait for a response
                start_time = time.time()
                while True:
                    try:
                        topic, obj = ZmqCodec.decode(sub.recv_multipart())
                    except zmq.Again:
                        if time.time() - start_time > 1:
                            l.error(config["short_name"] + " controller timed out waiting for " + str(process) + " status")
                            break
                        continue
                    l.debug(config["short_name"] + " controller received status response for " + str(process))
                    if check_apply_level(obj, config["short_name"]):
                        continue

                    # Expect response shape: ["status", <0|1>, <process_name>]
                    if topic == "control" and obj[0] == "status" and len(obj) >= 3:
                        status_val, proc_name = obj[1], obj[2]
                        if proc_name == process:
                            current_states.add((status_val, process))
                            break
                    
                    if topic == "control" and _should_exit(obj):
                        l.info(config["short_name"] + " controller got exit for " + str(process))
                        break

                    # fall through to timeout handler above if no message
            
                if _should_exit(obj):
                    break

            if _should_exit(obj):
                break

            led_vals = [k for k, v in relevant_states.items() if v == current_states]
            if led_vals:
                pixels[led] = led_vals[0]
                l.debug(config["short_name"] + " controller set led " + str(led) + " to " + str(led_vals[0]))
            else:
                pixels[led] = (0, 0, 0)
                l.error(config["short_name"] + " controller no valid states for led " + str(led))
        
        if _should_exit(obj):
            break
        
        pixels.show()
        time.sleep(1)
    
    l.info(config["short_name"] + " controller exiting")
    pub.close(0)
    sub.close(0)
    ctx.term()