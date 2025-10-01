import logging
from multiprocessing import Manager
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    if not obj or obj[0] != "loglevel":
        return False
    target = obj[1] if len(obj) > 1 else None
    level = obj[2] if len(obj) > 2 else None
    if target in ("all", process_name) and level is not None:
        set_process_log_level(level)
        if logger_name:
            logging.getLogger(logger_name).info(f"set log level to {parse_level(level)} for {process_name}")
        return True
    return False