import os
from datetime import datetime, timezone
from config import all_process_configs, zmq_control_endpoint
import zmq
import logging
from platformUtils.logUtils import worker_configurer, set_process_title


def get_config(config_name):
    return all_process_configs[config_name]


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


#returns logger, zmq sub, config
def configure_process(ctx, config_name):
    config = get_config(config_name)
    
    set_process_title(config_name)
    worker_configurer(config["debug_lvl"])
    logger = logging.getLogger(config_name)
    
    zmq_sub = ctx.socket(zmq.SUB)
    zmq_sub.connect(zmq_control_endpoint)
    zmq_sub.setsockopt(zmq.SUBSCRIBE, b"control")
    return logger, zmq_sub, config

def should_exit(topic, msg, config_name):
    if topic != "control": 
        return False
    return msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == config_name)


# def handle_control_message(msg, config_name, logger, config):
#     if should_exit(msg, config_name):
#         return True

#     if msg[0] == "update_config":
#         #we expect a dictionary of config overrides
#         config.update(msg[1])
#         logger.info(config_name + " process updated config")


#     return False