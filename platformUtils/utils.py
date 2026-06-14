import os
from datetime import datetime, timezone
from config import all_process_configs, zmq_control_endpoint, platform_uuid
import zmq
import logging
from platformUtils.logUtils import worker_configurer, set_process_title
from platformUtils.zmq_codec import ZmqCodec
import signal

def dt_to_fnString(dt, decimal_places=3):
    microseconds = dt.microsecond / 1_000_000
    truncated_microseconds = f"{microseconds:.6f}"[2:2+decimal_places]
    return dt.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S') + \
        f"p{truncated_microseconds}Z"

def dt_to_path(dt, base_path):
    hour_base_path = os.path.join(base_path, dt.astimezone(timezone.utc).strftime("%Y/%m/%d/%H/%M/"))
    os.makedirs(hour_base_path, exist_ok=True)
    return hour_base_path

def fnString_to_dt(s):
    ts_str = s
    if "/" in s:
        ts_str = ts_str.split("/")[-1]
    if "\\" in s:
        ts_str = ts_str.split("\\")[-1]
    if "_" in s: #if it's like a whole file name
        ts_str = ts_str.split("_")[-1]
    if "." in s:#if it has a file extension
        ts_str = ts_str.split(".")[0]
    ts_str = ts_str.replace("p",".")
    return datetime.fromisoformat(ts_str)

max_time_to_shutdown = max(v[1].get("time_to_shutdown") for v in all_process_configs.values())


def handle_args(args):
    #for debian the size limit of an arg is 2MB says AI
    #if there is a shared memory dictionary with the name of the process, return the config from it
    if os.path.exists(args[1]):
        pass
    if len(args) == 2:
        config_name = args[1]
        return all_process_configs[config_name][1].copy()
    raise ValueError("Invalid number of arguments")

#AI says that the default sigterm timeout is 90 seconds
class SignalHandler:
    def __init__(self):
        self.stop = False
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        signal.signal(signal.SIGINT, self.exit_gracefully) # Also handle Ctrl+C

    def exit_gracefully(self, *args):
        print("Termination signal received. Setting stop flag...")
        self.stop = True


#returns logger, zmq sub
def configure_process(config):
    ctx = zmq.Context()
    set_process_title(config["name"])
    worker_configurer(config["debug_lvl"])
    logger = logging.getLogger(config["name"])
    
    zmq_sub = ctx.socket(zmq.SUB)
    zmq_sub.connect(zmq_control_endpoint)
    zmq_sub.setsockopt(zmq.SUBSCRIBE, b"control")

    signal_handler = SignalHandler()
    
    return logger, zmq_sub, signal_handler

def should_exit(topic, msg, config_name):
    if topic != "control": 
        return False
    return msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == config_name)

def send_orchestrator_command(pub, command, config_name):
    topic = platform_uuid + "_orchestrator"
    message = [command, config_name]
    pub.send_multipart(ZmqCodec.encode(topic, message))

# def handle_control_message(msg, config_name, logger, config):
#     if should_exit(msg, config_name):
#         return True

#     if msg[0] == "update_config":
#         #we expect a dictionary of config overrides
#         config.update(msg[1])
#         logger.info(config_name + " process updated config")


#     return False