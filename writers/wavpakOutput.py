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
    def __init__(self,
                    output_base,
                    output_hz = 1,
                    temp_write_location = "/home/pi/data/temp/",
                    debug_lvl = "warning",
                    channels = 1,
                    bits = 16,
                    sign = "s",
                    endian = "le"):
        self.output_base = output_base
        self.temp_write_location = temp_write_location
        self.output_hz = max(1, output_hz)
        self.channels = channels
        self.bits = bits
        self.sign = sign
        self.endian = endian

        self.log_name = output_base + "_wavpak-output"
        self.l = logging.getLogger(self.log_name)
        self.l.setLevel(debug_lvl)
        self.l.info(self.log_name + " starting")


        self.persist_fn = temp_write_location + output_base + "_persist/persist.pkl"
        self.extension = ".wavpack"
        self.raw_spec = f"--raw-pcm={self.output_hz},{self.bits}{self.sign},{self.channels},{self.endian}"

    def persist(self, dt, data):
        obj = [dt, data]
        with open(self.persist_fn, "a") as f:
            pickle.dump(obj, f)
    
    def load(self): #I would like this to be an iterator that returns the next line
        with open(self.persist_fn, "r") as f:
            for obj in pickle.load(f):
                yield obj[0], obj[1]
    

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
        self.file_name = self.file_base + "_" + dt_to_fnString(dt) + self.extension
        self.proc = subprocess.Popen(
            ["wavpack", "-hh", self.raw_spec, "-", "-o", self.temp_output_location + self.file_name],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
        )
        t = threading.Thread(target=self._stderr_reader, args=(self.proc,), daemon=True)
        t.start()
        self.proc._stderr_thread = t  # attach for lifecycle awareness
    
    def write(self, data):
        #the array is numsamples x 1 for 1 channel, so we need to flatten it
        data = data.flatten()
        self.proc.stdin.write(data.tobytes(order="C"))

    def close(self):
        self.proc.stdin.flush()
        self.proc.stdin.close()
        self.proc.wait()
        if self.proc.returncode != 0:
            raise RuntimeError(self.proc.stderr.read().decode("utf-8"))
