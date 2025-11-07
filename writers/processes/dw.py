#data writer

import os
import sys
import zmq
import sqlite3
import time
from datetime import datetime, timezone
import numpy as np

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from platformUtils.zmq_codec import ZmqCodec
import logging
import pickle
from platformUtils.logUtils import worker_configurer, set_process_title
from config import data_writer_process_config, zmq_control_endpoint, dt_to_fnString, fnString_to_dt
from writers.writer import Writer

config = data_writer_process_config
l = logging.getLogger(config["short_name"])
def data_writer(log_queue):
    set_process_title(config["short_name"])
    worker_configurer(log_queue, config["debug_lvl"])
    l.info(config["short_name"] + " writer starting")

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)

    def persist(dt, data):
        path = config["cache_location"] + dt_to_fnString(dt, 6) + ".pkl"
        pickle.dump(data, open(path, "wb"))

    def load(path):
        return fnString_to_dt(path), pickle.load(open(path, "rb"))

    writer = Writer(config, persist, load)
    while True:
        topic, msg = ZmqCodec.decode(sub.recv_multipart())
        if topic == "control" and (msg[0] == "exit_all" or 
                (msg[0] == "exit" and msg[-1] == config["short_name"])):
            l.info(config["short_name"] + " writer exiting")
            break

        if topic != config["sub_topic"]:
            continue

        dt, data = msg
        writer.write(dt, data)


class output:
    def __init__(self):
        self.file_name = None
        self.file = None

    def open(self, dt):
        self.file_name = config["temp_write_location"] + dt_to_fnString(dt, 6) + config["extension"]
        self.file = open(self.file_name, "wb")
    
    def close(self, dt):
        self.file.close()

    def write(self, data):
        self.file.write(data)


import subprocess, numpy as np


import subprocess, numpy as np

class WavPackWriter:
    def __init__(self, out_path, sample_rate, n_channels, dtype="float32", little_endian=True, extra_tags=None):
        bits = 32 if dtype in ("float32", "int32") else 16
        sign = "f" if dtype == "float32" else "s"  # float or signed
        endian = "le" if little_endian else "be"
        raw_spec = f"--raw-pcm={sample_rate},{bits}{sign},{n_channels},{endian}"

        # APEv2 metadata tags are supported with -w "Field=Value"
        tag_args = []
        for k, v in (extra_tags or {}).items():
            tag_args += ["-w", f"{k}={v}"]

        self.proc = subprocess.Popen(
            ["wavpack", "-hh", raw_spec, "-", "-o", out_path] + tag_args,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
        )
        self.dtype = np.float32 if dtype == "float32" else np.int32
        self.n_channels = n_channels

    def write_frames(self, frame_block):
        """
        frame_block: np.ndarray shape (n_frames, n_channels), dtype matches ctor
        """
        assert frame_block.dtype == self.dtype and frame_block.shape[1] == self.n_channels
        self.proc.stdin.write(frame_block.tobytes(order="C"))

    def close(self):
        self.proc.stdin.flush()
        self.proc.stdin.close()
        self.proc.wait()
        if self.proc.returncode != 0:
            raise RuntimeError(self.proc.stderr.read().decode("utf-8"))
