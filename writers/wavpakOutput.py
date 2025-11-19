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
        self.persist_recovery_fn = self.persist_location + "persistRecovery.pkl"
        #create the pickle file if it doesn't exist
        if not os.path.exists(self.persist_fn):
            with open(self.persist_fn, "ab") as f:
                pickle.dump([], f)
        
        if os.path.exists(self.persist_recovery_fn):
            with open(self.persist_recovery_fn, "ab") as f:
                pickle.dump([], f)

        self.extension = ".wv"
        self.raw_spec = f"--raw-pcm={self.output_hz},{self.bits}{self.sign},{self.channels},{self.endian}"

        self.st = self.additional_output_config.get("int16_storage_type", None)
        #uint16-f9
        if self.st is None:
            raise ValueError("int16_storage_type is required")
        self.offset = 0 if self.st[0] == "u" else 2**15
        self.scale = 2**int(self.st.split("-")[1])


    def persist(self, dt, data):
        obj = [dt, data]
        with open(self.persist_fn, "ab") as f:
            pickle.dump(obj, f)
    
    def load(self): #I would like this to be an iterator that returns the next line
        if not os.path.exists(self.persist_fn) or os.path.getsize(self.persist_fn) == 0:
            self.l.info(self.log_name + " no cache found")
            return
        
        #if there is a persist file there, append it to persistRecovery.pkl
        self.l.info(self.log_name + " appending cache to recovery file")
        with open(self.persist_recovery_fn, "ab") as f:
            with open(self.persist_fn, "rb") as f2:
                f.write(f2.read())

        #and delete the original file
        self.l.info(self.log_name + " deleting original cache file")
        os.remove(self.persist_fn)

        self.l.info(self.log_name + " recovering from cache")
        #then load and write the contents of persistRecovery.pkl
        with open(self.persist_recovery_fn, "rb") as f:
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

        
        #then delete persistRecovery.pkl
        self.l.info(self.log_name + " deleting recovery file")
        os.remove(self.persist_recovery_fn)
    

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
        self.file_name = self.file_name + self.extension
    
    def write(self, data):
        #the array is numsamples x 1 for 1 channel, so we need to flatten it
        data = data.flatten()
        self.proc.stdin.write(data.tobytes(order="C"))

    def close(self, dt):
        self.proc.stdin.flush()
        self.proc.stdin.close()
        self.proc.wait()
        if self.proc.returncode != 0:
            raise RuntimeError(self.proc.stderr.read().decode("utf-8"))
        os.sync()
        new_fn = self.file_name.replace(".wv", "_" + dt_to_fnString(dt) + ".wv")
        os.rename(self.temp_output_location + self.file_name, 
                  self.temp_output_location + new_fn)
        self.file_name = None
        return new_fn