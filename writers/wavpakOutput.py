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
                    endian = "le",
                    **kwargs):
        self.output_base = output_base
        self.temp_write_location = temp_write_location
        self.output_hz = max(1, output_hz)
        self.channels = channels
        self.bits = bits
        self.sign = sign
        self.endian = endian

        self.file_name = None
        self.temp_output_location = temp_write_location + output_base + "/"
        os.makedirs(self.temp_output_location, exist_ok=True)

        self.log_name = output_base + "_wavpak-output"
        self.l = logging.getLogger(self.log_name)
        self.l.setLevel(debug_lvl)
        self.l.info(self.log_name + " starting")


        self.persist_location = temp_write_location + output_base + "_persist/"
        os.makedirs(self.persist_location, exist_ok=True)
        self.persist_fn = self.persist_location + "persist.pkl"
        #create the pickle file if it doesn't exist
        if not os.path.exists(self.persist_fn):
            with open(self.persist_fn, "ab") as f:
                pickle.dump([], f)

        self.extension = ".wv"
        self.raw_spec = f"--raw-pcm={self.output_hz},{self.bits}{self.sign},{self.channels},{self.endian}"

    def persist(self, dt, data):
        obj = [dt, data]
        with open(self.persist_fn, "ab") as f:
            pickle.dump(obj, f)
    
    def load(self): #I would like this to be an iterator that returns the next line
        if not os.path.exists(self.persist_fn) or os.path.getsize(self.persist_fn) == 0:
            return
        try:
            with open(self.persist_fn, "rb") as f:
                while True:
                    try:
                        obj = pickle.load(f)
                    except EOFError:
                        break
                    except Exception as e:
                        self.l.warning(self.log_name + " skipping corrupt cache entry: " + str(e))
                        break
                    if isinstance(obj, (list, tuple)) and len(obj) == 2:
                        yield obj[0], obj[1]
        except FileNotFoundError:
            return
    

    def _stderr_reader(self, p):
        try:
            for raw in iter(p.stderr.readline, b""):
                line = raw.decode(errors="replace").rstrip()
                if line:
                    self.l.debug(self.log_name + " wavpack stderr: " + line)
        except Exception as e:
            self.l.error(self.log_name + " wavpack stderr reader error: " + str(e))
        finally:
            self.l.debug(self.log_name + " wavpack stderr: [closed]")
    

    def open(self, dt):
        # for some reason, the cli adds the extension
        self.file_name = self.output_base + "_" + dt_to_fnString(dt)# + self.extension
        
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
        os.sync()
