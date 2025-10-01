import logging
import logging.handlers
import colorlog
import sys

# define custom TRACE level (5) and helper methods
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

# for formatter attributes I went to 
# https://docs.python.org/3/library/logging.html
# and went to the LogRecord attributes section

#a reminder about levels and numbers
#- trace (not built in) (5)
#- debug (10)
#- info (20)
#- warning (30)
#- error (40)
#- critical (50)

class NameAndFunctionFilter(logging.Filter):
    def __init__(self, allowed_loggers=None, allowed_funcs=None, passthrough_min_level=logging.INFO):
        super().__init__()
        self.allowed_loggers = set(allowed_loggers or [])
        self.allowed_funcs = set(allowed_funcs or [])
        self.passthrough_min_level = passthrough_min_level

    def filter(self, record):
        match_logger = (not self.allowed_loggers) or (record.name in self.allowed_loggers)
        match_func = (not self.allowed_funcs) or (record.funcName in self.allowed_funcs)
        return (match_logger and match_func) or (record.levelno >= self.passthrough_min_level)

def listener_configurer(
    logfile_path="/home/pi/unifiedSensorClient.log",
    level=logging.DEBUG,
    allowed_loggers=None,
    allowed_funcs=None,
):
    fmt = '[%(asctime)s] [%(name)s] [%(funcName)s] [%(levelname)s] %(message)s'
    formatter = logging.Formatter(fmt)

    # File handler
    file_handler = logging.FileHandler(logfile_path)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(TRACE_LEVEL_NUM)
    file_handler.addFilter(NameAndFunctionFilter(allowed_loggers, allowed_funcs, passthrough_min_level=level))

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
    stream_handler.addFilter(NameAndFunctionFilter(allowed_loggers, allowed_funcs, passthrough_min_level=level))

    root = logging.getLogger()
    root.handlers = []  # reset in listener
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    root.setLevel(TRACE_LEVEL_NUM)  # allow all; filtering done by handlers/filters

def worker_configurer(queue, level=logging.INFO):
    handler = logging.handlers.QueueHandler(queue)
    root = logging.getLogger()
    root.handlers = []  # remove defaults in the worker
    root.addHandler(handler)
    root.setLevel(level)  # this is per-process

def logging_listener(queue, logfile_path, level=logging.INFO, allowed_loggers=None, allowed_funcs=None):
    listener_configurer(
        logfile_path=logfile_path,
        level=level,
        allowed_loggers=allowed_loggers,
        allowed_funcs=allowed_funcs,
    )
    while True:
        record = queue.get()
        if record is None:  # sentinel to stop
            break
        logger = logging.getLogger(record.name)
        logger.handle(record)

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

def check_exit(obj, process_name, logger_name=None):
    # obj shape: ["exit", <target|all>]
    if logger_name is None:
        logger_name = process_name
    if not obj or obj[0] != "exit":
        return False
    target = obj[1] if len(obj) > 1 else None
    if target in ("all", process_name):
        if logger_name:
            logging.getLogger(logger_name).info(f"got exit from control for {process_name}")
        return True
    return False



#### reference notes
class NameAndFunctionFilter(logging.Filter):
    def __init__(self, passthrough_min_level=logging.INFO, state=None):
        super().__init__()
        self.passthrough_min_level = passthrough_min_level
        self.state = state  # Manager dict (schema below)

    def _min_level(self):
        if self.state and "min_level" in self.state:
            try:
                return int(self.state["min_level"])
            except Exception:
                pass
        return self.passthrough_min_level

    @staticmethod
    def _func_ok(allowed_funcs, func):
        if not allowed_funcs:
            return False
        return func in allowed_funcs or "*" in allowed_funcs

    def filter(self, record):
        # always allow at/above min level
        if record.levelno >= self._min_level():
            return True

        proc = getattr(record, "processName", None)
        logger_name = record.name
        func = record.funcName
        s = self.state or {}

        # 1) per (process -> logger -> [funcs])
        by_pl = (s.get("by_proc_logger") or {}).get(proc, {})
        funcs = by_pl.get(logger_name)
        if self._func_ok(funcs, func):
            return True

        # 2) per-logger funcs
        by_l = (s.get("by_logger") or {}).get(logger_name)
        if self._func_ok(by_l, func):
            return True

        # 3) per-process funcs
        by_p = (s.get("by_process") or {}).get(proc)
        if self._func_ok(by_p, func):
            return True

        # 4) global lists
        allowed_loggers = set(s.get("allowed_loggers") or [])
        allowed_funcs = set(s.get("allowed_funcs") or [])
        if allowed_loggers and allowed_funcs:
            return (logger_name in allowed_loggers) and (func in allowed_funcs or "*" in allowed_funcs)
        if allowed_loggers:
            return logger_name in allowed_loggers
        if allowed_funcs:
            return func in allowed_funcs or "*" in allowed_funcs

        # default deny if below min level
        return False

def add_proc_logger_funcs(state, process, logger, funcs):
    m = dict(state.get("by_proc_logger") or {})
    pl = dict(m.get(process) or {})
    cur = set(pl.get(logger) or [])
    cur |= set(funcs)
    pl[logger] = list(cur)
    m[process] = pl
    state["by_proc_logger"] = m

def add_logger_funcs(state, logger, funcs):
    m = dict(state.get("by_logger") or {})
    cur = set(m.get(logger) or [])
    cur |= set(funcs)
    m[logger] = list(cur)
    state["by_logger"] = m

def add_process_funcs(state, process, funcs):
    m = dict(state.get("by_process") or {})
    cur = set(m.get(process) or [])
    cur |= set(funcs)
    m[process] = list(cur)
    state["by_process"] = m


# in listener_configurer(...)
file_handler.addFilter(NameAndFunctionFilter(passthrough_min_level=level, state=filter_state))
stream_handler.addFilter(NameAndFunctionFilter(passthrough_min_level=level, state=filter_state))

# when starting workers in main.py
p = mp.Process(target=target, name=cfg.get("short_name"))

# examples
add_proc_logger_funcs(filter_state, process="yolo", logger="yoloPersonDetector", funcs=["inference_step"])
add_logger_funcs(filter_state, logger="sqliteWriter", funcs=["write_row"])
add_process_funcs(filter_state, process="video", funcs=["_capture_frame"])
# optionally tighten or relax global min level
filter_state["min_level"] = 20  # INFO