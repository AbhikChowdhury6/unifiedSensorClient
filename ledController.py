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
    l.info(config["short_name"] + " controller connected to control topic")

    pub = ctx.socket(zmq.PUB)
    pub.connect(config["pub_endpoint"])
    l.info(config["short_name"] + " controller connected to pub on control topic")

    def _should_exit(obj):
        return obj[0] == "exit_all" or (obj[0] == "exit" and obj[1] == process)

    obj = [None, None, None]
    while True:
        #for each led, send the status requests and wait for a response
        for led in config["states"]:
            relevant_states = config["states"][led]
            l.trace(str(led) + " relevant states: " + str(relevant_states))
            # Extract unique process short names from the sets of (status, process) tuples
            relevant_processes = list({proc for state_set in relevant_states.values() for _, proc in state_set})
            l.trace(str(led) + " relevant processes: " + str(relevant_processes))
            
            current_states = set()
            for process in relevant_processes:
                #send a status request and wait for a response
                pub.send_multipart(ZmqCodec.encode(config["pub_topic"], ["status", process]))
                l.debug(config["short_name"] + " controller sent status request for " + str(process))
                
                #wait for a response
                start_time = time.time()
                while True:
                    topic, obj = ZmqCodec.decode(sub.recv_multipart())
                    l.debug(config["short_name"] + " controller received status response for " + str(process))
                    if check_apply_level(obj, config["short_name"]):
                        continue

                    if topic == "control" and obj[0] == "status" and obj[1] == process:
                        current_states.add((obj[2], process))
                        break
                    
                    if topic == "control" and _should_exit(obj):
                        l.info(config["short_name"] + " controller got exit for " + str(process))
                        break

                    if time.time() - start_time > 1:
                        l.error(config["short_name"] + " controller timed out waiting for " + str(process) + " status")
                        break
            
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