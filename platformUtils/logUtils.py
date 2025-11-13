import logging
import logging.handlers
import fnmatch
import os
import sys
import colorlog
from queue import Empty
import ctypes
import ctypes.util
from datetime import datetime, timezone, timedelta
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import zmq
from platformUtils.zmq_codec import ZmqCodec
from config import logging_process_config, zmq_control_endpoint, all_process_configs

max_time_to_shutdown = max(v[1].get("time_to_shutdown") for v in all_process_configs.values())


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
        # ensure the caller is reported, not this wrapper
        kwargs["stacklevel"] = kwargs.get("stacklevel", 2)
        self._log(TRACE_LEVEL_NUM, message, args, **kwargs)

logging.Logger.trace = _logger_trace

def trace(message, *args, **kwargs):
    # ensure the caller is reported, not this wrapper
    kwargs["stacklevel"] = kwargs.get("stacklevel", 2)
    logging.log(TRACE_LEVEL_NUM, message, *args, **kwargs)

logging.trace = trace

def set_process_title(short_name: str):
    try:
        import setproctitle
        setproctitle.setproctitle(f"usc:{short_name}:{os.getpid()}")
        return
    except Exception:
        pass
    # Fallback: set PR_SET_NAME (15 chars limit)
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c"))
        PR_SET_NAME = 15
        name = f"usc:{short_name}"[:15].encode()
        libc.prctl(PR_SET_NAME, ctypes.c_char_p(name), 0, 0, 0)
    except Exception:
        # Ignore if not supported
        pass

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
