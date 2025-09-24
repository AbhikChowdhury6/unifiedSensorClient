import logging
import logging.handlers
import colorlog


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
