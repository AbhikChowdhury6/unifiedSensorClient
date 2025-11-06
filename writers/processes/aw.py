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
     dt_to_fnString, fnString_to_dt
import zmq
import logging
import numpy as np
from platformUtils.logUtils import worker_configurer, set_process_title
from writers.writer import Writer
import pickle

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

    def persist(dt, data):
        path = config["cache_location"] + dt_to_fnString(dt, 6) + ".pkl"
        pickle.dump(data, open(path, "wb"))

    def load(path):
        return fnString_to_dt(path), pickle.load(open(path, "rb"))

    writer = Writer(config["writer_config"], persist, load)
    while True:
        topic, msg = ZmqCodec.decode(sub.recv_multipart())

        if topic == "control" and (msg[0] == "exit_all" or 
                (msg[0] == "exit" and msg[-1] == config["short_name"])):
            l.info(config["short_name"] + " writer exiting")
            break

        if topic != config["sub_topic"]:
            continue

        dt, chunk = msg
        writer.write(dt, chunk)


class output:
    def __init__(self):
        self.ff = None
        self.file_name = None
        self.temp_output_location = config["temp_write_location"]
        self.extension = config["extension"]
    
    def open(self, dt: datetime):
        """Spawn ffmpeg to encode PCM from stdin into Opus segments using config.

        Reads all parameters from audio_writer_config for simplicity.
        Returns a subprocess.Popen handle with stdin PIPE for feeding PCM.
        """
        channels = int(config["channels"])
        sample_rate = int(config["sample_rate"])
        bitrate = str(config["bitrate"])
        frame_duration_ms = int(config["frame_duration_ms"])
        loglevel = str(config["loglevel"])
        sample_fmt = "s16le"
        file_base = config["file_base"]
        self.file_name = file_base + "_" + dt_to_fnString(dt, 6) + self.extension

        file_name_and_path = self.temp_output_location + self.file_name

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
            file_name_and_path,
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
            t = threading.Thread(target=self._stderr_reader, args=(proc,), daemon=True)
            t.start()
            proc._stderr_thread = t  # attach for lifecycle awareness
            self.ff = proc
            self.is_open = True
            return self.file_name
        except FileNotFoundError:
            l.error(config["short_name"] + " writer: ffmpeg not found. Please install ffmpeg.")
            return None
        except Exception as e:
            l.error(config["short_name"] + " writer: failed to start ffmpeg: " + str(e))
            return None


    def _stderr_reader(self, p):
        try:
            for raw in iter(p.stderr.readline, b""):
                line = raw.decode(errors="replace").rstrip()
                if line:
                    l.debug(config["short_name"] + " writer: ffmpeg stderr: " + line)
        except Exception as e:
            l.error(config["short_name"] + " writer: ffmpeg stderr reader error: " + str(e))
        finally:
            l.debug(config["short_name"] + " writer: ffmpeg stderr: [closed]")
    
    def close(self, dt: datetime):
        #close the stdin
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

        #rename the file to seal it
        new_fn = self.file_name.replace(self.extension, 
                                        "_" + dt_to_fnString(dt, 6) + self.extension)
        os.rename(self.temp_output_location + self.file_name, 
                  self.temp_output_location + new_fn)
        self.file_name = None
        return new_fn

    def write(self, data):
        self.ff.stdin.write(data)
        
