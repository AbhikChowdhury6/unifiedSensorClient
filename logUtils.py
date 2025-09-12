import logging
import logging.handlers
import colorlog
from datetime import datetime
import sys
import os

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from config import (
    log_queue,
    allowed_loggers,
    allowed_funcs,
    debugLvl,
)


# for formatter attributes I went to 
# https://docs.python.org/3/library/logging.html
# and went to the LogRecord attributes section

class NameAndFunctionFilter(logging.Filter):
    def __init__(self, allowed_loggers=None, allowed_funcs=None):
        super().__init__()
        self.allowed_loggers = set(allowed_loggers or [])
        self.allowed_funcs = set(allowed_funcs or [])

    def filter(self, record):
        match_logger = (not self.allowed_loggers) or (record.name in self.allowed_loggers)
        match_func = (not self.allowed_funcs) or (record.funcName in self.allowed_funcs)
        return (match_logger and match_func) or record.levelno > debugLvl

def listener_configurer(logfile_path="/home/pi/unifiedSensorClient.log"):
    formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(funcName)s] [%(levelname)s] %(message)s')

    # File handler
    file_handler = logging.FileHandler(logfile_path)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(NameAndFunctionFilter(allowed_loggers, allowed_funcs))

    # Stream handler (stdout)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(colorlog.ColoredFormatter(
        '%(log_color)s[%(asctime)s] [%(name)s] [%(funcName)s] [%(levelname)s] %(message)s',
        log_colors={
            'DEBUG':    'cyan',
            'INFO':     'green',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'bold_red',
        }
    ))
    stream_handler.addFilter(NameAndFunctionFilter(allowed_loggers, allowed_funcs))

    # Root logger
    root = logging.getLogger()
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    root.setLevel(debugLvl)

def worker_configurer(queue):
    handler = logging.handlers.QueueHandler(queue)
    root = logging.getLogger()
    root.handlers = []  # Remove default handlers
    root.addHandler(handler)
    root.setLevel(debugLvl)

def listener_process(queue, exitSignal):
    listener_configurer()
    while True:
        if exitSignal[0] == 1:
            startExitTime = datetime.now()
            while (datetime.now() - startExitTime).total_seconds() < buffSecs + 2:
                record = queue.get()
                logger = logging.getLogger(record.name)
                logger.handle(record)
            break
        try:
            record = queue.get()
            if record is None:
                break
            logger = logging.getLogger(record.name)
            logger.handle(record)
        except Exception:
            import traceback
            print("Error in logger listener:")
            traceback.print_exc()
