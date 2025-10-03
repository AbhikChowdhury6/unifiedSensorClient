import logging
from multiprocessing import Manager
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import zmq
from zmq_codec import ZmqCodec
from config import all_process_configs, logging_process_config

#a reminder about levels and numbers
#- trace (not built in) (5)
#- debug (10)
#- info (20)
#- warning (30)
#- error (40)
#- critical (50)


#### define custom TRACE level (5) and helper methods ####
TRACE_LEVEL_NUM = 5
logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")
logging.TRACE = TRACE_LEVEL_NUM

def _logger_trace(self, message, *args, **kwargs):
    if self.isEnabledFor(TRACE_LEVEL_NUM):
        self._log(TRACE_LEVEL_NUM, message, args, **kwargs)

logging.Logger.trace = _logger_trace

def trace(message, *args, **kwargs):
    logging.log(TRACE_LEVEL_NUM, message, *args, **kwargs)

logging.trace = trace

#### helpers for configuring logging from control ####
LEVELS = {
    "trace": logging.TRACE,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}

def parse_level(v):
    if isinstance(v, str):
        return LEVELS[v.lower()]
    return int(v)

def set_process_log_level(level):
    logging.getLogger().setLevel(parse_level(level))

def check_apply_level(obj, process_name, logger_name=None):
    # obj shape: ["loglevel", <target|all>, <level>]
    if logger_name is None:
        logger_name = process_name
    if not obj or obj[0] != "log":
        return False
    target = obj[1] if len(obj) > 1 else None
    level = obj[2] if len(obj) > 2 else None
    if target in ("all", process_name) and level is not None:
        set_process_log_level(level)
        if logger_name:
            logging.getLogger(logger_name).info(f"set log level to {parse_level(level)} for {process_name}")
        return True
    return False

def worker_configurer(queue, level=logging.INFO):
    handler = logging.handlers.QueueHandler(queue)
    root = logging.getLogger()
    root.handlers = []  # remove defaults in the worker
    root.addHandler(handler)
    root.setLevel(level)  # this is per-process



# define the filter
class NameAndFunctionFilter(logging.Filter):
    def __init__(self, allow_dict, deny_dict):
        super().__init__()
        self.allow_dict = allow_dict
        self.deny_dict = deny_dict

    def filter(self, record):
        if record.name not in self.allow_dict:
            return False
        if record.name in self.deny_dict and \
            record.funcName in self.deny_dict[record.name]:
            return False
        if self.allow_dict[record.name] == "all" or \
            record.funcName in self.allow_dict[record.name]:
            return True
        return False


def listener_configurer(config, allow_dict, deny_dict):
    fmt = '[%(asctime)s] [%(name)s] [%(funcName)s] [%(levelname)s] %(message)s'
    formatter = logging.Formatter(fmt)

    # File handler
    file_handler = logging.FileHandler(config["logfile_path"])
    file_handler.setFormatter(formatter)
    file_handler.setLevel(TRACE_LEVEL_NUM)
    file_handler.addFilter(NameAndFunctionFilter(allow_dict, deny_dict))

    # Stream handler (stdout)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(colorlog.ColoredFormatter(
        '%(log_color)s' + fmt,
        log_colors={
            'TRACE':    'white',
            'DEBUG':    'cyan',
            'INFO':     'green',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'bold_red',
        }
    ))
    stream_handler.setLevel(TRACE_LEVEL_NUM)
    stream_handler.addFilter(NameAndFunctionFilter(allow_dict, deny_dict))

    root = logging.getLogger()
    root.handlers = []  # reset in listener
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    root.setLevel(TRACE_LEVEL_NUM)  # allow all; filtering done by handlers/filters


def logging_process():
    listener_configurer()
    config = logging_process_config
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(config["pub_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    print("logging process connected to control topic")
    sys.stdout.flush()
    
    while True:
        parts = sub.recv_multipart()
        topic, obj = ZmqCodec.decode(parts)
        if topic == "control" and obj[0] == "log":
            log_cmd = obj[1]
            target_process = obj[2]
            target_method = obj[3]
            if log_cmd == "e":
                logging.getLogger(target_process).error(f"error in {target_method}")