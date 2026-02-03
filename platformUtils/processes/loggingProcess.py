import os
import sys
import logging
import zmq
from datetime import datetime, timezone, timedelta
from config import logging_process_config, zmq_control_endpoint, zmq_logger_endpoint
from platformUtils.zmq_codec import ZmqCodec
from platformUtils.logUtils import set_process_title, TRACE_LEVEL_NUM
import colorlog
import fnmatch
from config import all_process_configs

max_time_to_shutdown = max(v[1].get("time_to_shutdown") for v in all_process_configs.values())

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
    os.makedirs(os.path.dirname(config["logfile_path"]), exist_ok=True)
    file_handler = logging.FileHandler(config["logfile_path"])
    file_handler.setFormatter(formatter)
    file_handler.setLevel(TRACE_LEVEL_NUM)
    #file_handler.addFilter(NameAndFunctionFilter(allow_dict, deny_dict))

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
    #stream_handler.addFilter(NameAndFunctionFilter(allow_dict, deny_dict))

    root = logging.getLogger()
    root.handlers = []  # reset in listener
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    root.setLevel(TRACE_LEVEL_NUM)  # allow all; filtering done by handlers/filters


 
def logging_process(allow_dict, deny_dict):
    config = logging_process_config
    # set process title for the logging listener
    try:
        from config import logging_process_config as _cfg
        set_process_title(_cfg["short_name"])
    except Exception:
        pass
    listener_configurer(config, allow_dict, deny_dict)
    l = logging.getLogger(config["short_name"])
    l.info(config["short_name"] + " process starting")

    ctx = zmq.Context()
    # Single SUB: bind to logger endpoint (workers PUB connect), and connect to control bus
    sub = ctx.socket(zmq.SUB)
    sub.bind(zmq_logger_endpoint)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"log")
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    sub.setsockopt(zmq.RCVTIMEO, 50)
    l.info(config["short_name"] + " process listening on logger " + zmq_logger_endpoint + " and control " + zmq_control_endpoint)
    exit_time = datetime.max.replace(tzinfo=timezone.utc)

    while True:
        if datetime.now(timezone.utc) > exit_time:
            l.info(config["short_name"] + " process exiting")
            break

        try:
            parts = sub.recv_multipart()
            topic, obj = ZmqCodec.decode(parts)
        except zmq.Again:
            continue

        if topic == "log" and isinstance(obj, dict):
            try:
                rec = logging.LogRecord(
                    name=obj.get("name", ""),
                    level=obj.get("levelno", logging.INFO),
                    pathname=obj.get("pathname", ""),
                    lineno=obj.get("lineno", 0),
                    msg=obj.get("msg", ""),
                    args=(),
                    exc_info=None,
                    func=obj.get("funcName", None),
                )
                rec.processName = obj.get("processName", "")
                rec.threadName = obj.get("threadName", "")
                rec.created = obj.get("created", rec.created)
                rec.msecs = obj.get("msecs", rec.msecs)
                logging.getLogger(rec.name).handle(rec)
            except Exception:
                pass
            continue

        if topic == "control":
            if obj[0] == "exit_all":
                l.info(config["short_name"] + " process got control exit exiting in " + str(max_time_to_shutdown + .5) + " seconds")
                exit_time = datetime.now(timezone.utc) + timedelta(seconds=max_time_to_shutdown + .5)
                continue
            if obj[0] != "log":
                continue

            log_cmd = obj[1]
            target_process = obj[2]

            if log_cmd == "e":
                target_method = obj[3]
                if target_process not in allow_dict:
                    allow_dict[target_process] = []
                allow_dict[target_process].append(target_method)
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
                if target_process in allow_dict:
                    if target_method == "all":
                        del allow_dict[target_process]
                    else:
                        if "all" not in allow_dict[target_process]:
                            allow_dict[target_process].remove(target_method)
    print("logUtils: logging process exiting")
    sys.stdout.flush()
