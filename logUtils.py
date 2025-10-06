import logging
import logging.handlers
import fnmatch
import os
import sys
import colorlog
from queue import Empty
from datetime import datetime, timezone, timedelta
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import zmq
from zmq_codec import ZmqCodec
from config import logging_process_config, zmq_control_endpoint

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
    # obj shape: ["log", "s", <process>, <level>]
    if not obj or obj[0] != "log":
        return False
    if obj[1] != "s":
        return False
    
    if logger_name is None:
        logger_name = process_name
    if obj[2] != process_name:
        return False
    
    level = obj[3] if len(obj) > 3 else None
    if level is not None:
        set_process_log_level(level)
        logging.getLogger(logger_name).info(f"set log level to {parse_level(level)} for {process_name}")
        return True
    else:
        logging.getLogger(logger_name).error(f"log level not given for {process_name}")
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
        self.allow_dict = allow_dict   # { processName: [func patterns] }
        self.deny_dict = deny_dict     # { processName: [func patterns] }

    @staticmethod
    def _match_any(value, patterns):
        for pat in (patterns or []):
            if pat in ("all", "*"):
                return True
            if value == pat or (pat in value) or fnmatch.fnmatch(value, pat):
                return True
        return False

    def filter(self, record):
        proc = getattr(record, "processName", None)
        func = record.funcName

        allowed = self.allow_dict.get(proc, [])
        if not allowed:
            return False

        denied = self.deny_dict.get(proc, [])
        if self._match_any(func, denied):
            return False

        return self._match_any(func, allowed)


def listener_configurer(config, allow_dict, deny_dict):
    fmt = '[%(asctime)s] [%(name)s] [%(funcName)s] [%(levelname)s] [%(lineno)d] %(message)s'
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


def logging_process(q, allow_dict, deny_dict):
    config = logging_process_config
    listener_configurer(config, allow_dict, deny_dict)
    l = logging.getLogger(config["short_name"])
    l.info(config["short_name"] + " process starting")

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    sub.setsockopt(zmq.RCVTIMEO, 50)
    l.info(config["short_name"] + " process connected to control topic")
    exit_time = datetime.max.replace(tzinfo=timezone.utc)

    while True:
        if datetime.now(timezone.utc) > exit_time:
            l.info(config["short_name"] + " process exiting")
            break
        # Drain log queue first (non-blocking)
        while True:
            try:
                record = q.get_nowait()
            except Empty:
                break
            if record is None:
                return
            logger = logging.getLogger(record.name)
            logger.handle(record)

        # Then handle control messages (non-blocking via timeout)
        try:
            parts = sub.recv_multipart()
            topic, obj = ZmqCodec.decode(parts)
        except zmq.Again:
            continue
        
        if topic == "control" and obj[0] == "exit_all":
            l.info(config["short_name"] + " process got control exit exiting in 5 seconds")
            exit_time = datetime.now(timezone.utc) + timedelta(seconds=5)
            continue
        
        if not (topic == "control" and obj[0] == "log"):
            continue

        log_cmd = obj[1]
        target_process = obj[2]

        if log_cmd == "e":
            target_method = obj[3]
            if target_process not in allow_dict:
                allow_dict[target_process] = []
            allow_dict[target_process].append(target_method)
            
            # update the deny dict
            if target_process in deny_dict:
                if target_method == "all":
                    del deny_dict[target_process]
                else:
                    deny_dict[target_process].remove(target_method)
            
            
        elif log_cmd == "d":           
            target_method = obj[3]
            if target_process not in deny_dict:
                deny_dict[target_process] = []
            deny_dict[target_process].append(target_method)

            # update the allow dict
            if target_process in allow_dict:
                if target_method == "all":
                    del allow_dict[target_process]
                else:
                    if "all" not in allow_dict[target_process]:
                        allow_dict[target_process].remove(target_method)
