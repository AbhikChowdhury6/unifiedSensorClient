import sys
import pickle
import os
import subprocess
import threading
from datetime import datetime
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from config import dt_to_fnString, fnString_to_dt
import logging

class wavpak_output:
    def __init__(self,config):
        self.config = config
        self.log_name = self.config["topic"] + "_wavpak-output"
        self.l = logging.getLogger(self.log_name)
        self.l.setLevel(self.config['debug_lvl'])
        self.l.info(self.log_name + " starting")
        self.proc = None
        self.file_name = None
        self.temp_output_location = self.config["temp_write_location"] + self.config["topic"] + "/"
        self.persist_location = self.config["persist_location"] + self.config["topic"] + "/"

        os.makedirs(self.persist_location, exist_ok=True)
        os.makedirs(self.temp_output_location, exist_ok=True)


        self.persist_fn = self.persist_location + "persist.csv"
        self.data_type = config["data_type"]

        self.extension = ".wavpack"
        self.sample_rate = config["hz"]
    
        self.n_channels = config["channels"]

        bits = config["bits"]
        sign = config["sign"]
        endian = config["endian"]
        self.raw_spec = f"--raw-pcm={self.sample_rate},{bits}{sign},{self.n_channels},{endian}"

    def persist(self, dt, data):
        csv_line = f"{dt_to_fnString(dt)},{data}"
        with open(self.persist_fn, "a") as f:
            f.write(csv_line + "\n")
    
    def load(self): #I would like this to be an iterator that returns the next line
        with open(self.persist_fn, "r") as f:
            for line in f:
                dt, data = line.split(",")
                yield fnString_to_dt(dt), self.data_type(data)
    

    def _stderr_reader(self, p):
        try:
            for raw in iter(p.stderr.readline, b""):
                line = raw.decode(errors="replace").rstrip()
                if line:
                    self.l.debug(self.log_name + " ffmpeg stderr: " + line)
        except Exception as e:
            self.l.error(self.file_base + " writer: ffmpeg stderr reader error: " + str(e))
        finally:
            self.l.debug(self.file_base + " writer: ffmpeg stderr: [closed]")
    

    def open(self, dt):
        self.file_name = self.temp_output_location + dt_to_fnString(dt) + self.extension
        self.proc = subprocess.Popen(
            ["wavpack", "-hh", self.raw_spec, "-", "-o", self.file_name],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
        )
        t = threading.Thread(target=self._stderr_reader, args=(self.proc,), daemon=True)
        t.start()
        self.proc._stderr_thread = t  # attach for lifecycle awareness
    def write(self, data):
        self.proc.stdin.write(data.tobytes(order="C"))

    def close(self):
        self.proc.stdin.flush()
        self.proc.stdin.close()
        self.proc.wait()
        if self.proc.returncode != 0:
            raise RuntimeError(self.proc.stderr.read().decode("utf-8"))
