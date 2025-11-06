import os
import sys
import time
import subprocess
import threading
from datetime import datetime, timezone, timedelta

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from platformUtils.zmq_codec import ZmqCodec
from config import audio_writer_process_config, zmq_control_endpoint,\
 dt_to_path, dt_to_fnString, fnString_to_dt
import zmq
import logging
import numpy as np
from platformUtils.logUtils import worker_configurer, set_process_title
import shutil
from writers.writer import Writer

config = audio_writer_process_config
l = logging.getLogger(config["short_name"])
def audio_writer(log_queue):
    set_process_title(config["short_name"])
    worker_configurer(log_queue, config["debug_lvl"])
    l.info(config["short_name"] + " writer starting")

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(config["sub_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, config["sub_topic"].encode())
    l.info(config["short_name"] + " writer subscribed to " + config["sub_topic"])

    persist = lambda x, y: pickle.dump(y, open(x, "wb"))
    persist_open = lambda x: pickle.load(open(x, "rb"))

    class output:
        def __init__(self, file_name):
            self.file_name = file_name
            self.file = open(file_name, "wb")
        def write(self, data):
            self.file.write(data)
        def close(self):
            self.file.close()


    writer = Writer(config["writer_config"])
    while True:
        topic, msg = ZmqCodec.decode(sub.recv_multipart())

#takes in a dt and returns a file object

class output:
    def __init__(self):
        self.ff = None
        self.is_open = False
    
    def open(self, dt: datetime):
        """Spawn ffmpeg to encode PCM from stdin into Opus segments using config.

        Reads all parameters from audio_writer_config for simplicity.
        Returns a subprocess.Popen handle with stdin PIPE for feeding PCM.
        """
        channels = int(config["channels"])
        sample_rate = int(config["sample_rate"])
        bitrate = str(config["bitrate"])
        frame_duration_ms = int(config["frame_duration_ms"])
        output_root = config["temp_write_location_base"]
        loglevel = str(config["loglevel"])
        sample_fmt = "s16le"
        file_base = config["file_base"]
        temp_file_name = file_base + "_" + dt_to_fnString(dt, 6) + ".opus"

        file_name = output_root + temp_file_name

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", loglevel,
            "-f", sample_fmt,
            "-ac", str(channels),
            "-ar", str(sample_rate),
            "-i", "pipe:0",
            "-c:a", "libopus",
            "-b:a", bitrate,
            "-frame_duration", str(frame_duration_ms),
            file_name,
        ]

        #standard error reader and running ffmpeg
        try:
            # Force UTC for strftime in ffmpeg so paths match UTC-based folders
            env = os.environ.copy()
            env["TZ"] = "UTC"
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                bufsize=0, env=env
            )
            l.debug(config["short_name"] + " writer: started ffmpeg: " + " ".join(cmd))

            # Start a background stderr reader for diagnostics
            t = threading.Thread(target=_stderr_reader, args=(proc,), daemon=True)
            t.start()
            proc._stderr_thread = t  # attach for lifecycle awareness
            self.ff = proc
            self.is_open = True
        except FileNotFoundError:
            l.error(config["short_name"] + " writer: ffmpeg not found. Please install ffmpeg.")
            return None
        except Exception as e:
            l.error(config["short_name"] + " writer: failed to start ffmpeg: " + str(e))
            return None


    def _stderr_reader(p):
        try:
            for raw in iter(p.stderr.readline, b""):
                line = raw.decode(errors="replace").rstrip()
                if line:
                    l.debug(config["short_name"] + " writer: ffmpeg stderr: " + line)
        except Exception as e:
            l.error(config["short_name"] + " writer: ffmpeg stderr reader error: " + str(e))
        finally:
            l.debug(config["short_name"] + " writer: ffmpeg stderr: [closed]")
    
    def close(self):
        if self.ff.stdin is not None:
            self.ff.stdin.close()
        
        try:
            self.ff.terminate()
            self.ff.wait(timeout=3)
        except Exception as e:
            l.error(config["short_name"] + " writer: failed to terminate ffmpeg: " + str(e))
        try:
            self.ff.kill()
            self.ff.wait(timeout=2)
        except Exception as e:
            l.error(config["short_name"] + " writer: failed to kill ffmpeg: " + str(e))
        self.ff = None

    def write(self, data):
        self.ff.stdin.write(data)
        
