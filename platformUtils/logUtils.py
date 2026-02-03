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
from config import logging_process_config, zmq_control_endpoint, all_process_configs, zmq_logger_endpoint



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

class ZmqLogHandler(logging.Handler):
    """
    Logging handler that publishes formatted log records over ZMQ to the logger endpoint.
    """
    def __init__(self, endpoint: str, topic: str = "log"):
        super().__init__()
        self._ctx = zmq.Context.instance()
        self._pub = self._ctx.socket(zmq.PUB)
        # Workers connect to the logger SUB endpoint bound by the logging process
        self._pub.connect(endpoint)
        self._topic = topic

    def emit(self, record: logging.LogRecord):
        try:
            payload = {
                "name": record.name,
                "levelno": record.levelno,
                "levelname": record.levelname,
                "pathname": record.pathname,
                "lineno": record.lineno,
                "funcName": record.funcName,
                "processName": getattr(record, "processName", ""),
                "threadName": getattr(record, "threadName", ""),
                "created": record.created,
                "msecs": record.msecs,
                # send formatted message to avoid args/exc serialization issues
                "msg": record.getMessage(),
            }
            self._pub.send_multipart(ZmqCodec.encode(self._topic, payload))
        except Exception:
            # never raise from logging; fallback to stderr
            try:
                sys.stderr.write("ZmqLogHandler failed to emit log record\n")
                sys.stderr.flush()
            except Exception:
                pass

def worker_configurer(level=logging.INFO):
    handler = ZmqLogHandler(zmq_logger_endpoint, topic="log")
    root = logging.getLogger()
    root.handlers = []  # remove defaults in the worker
    root.addHandler(handler)
    root.setLevel(level)  # this is per-process
