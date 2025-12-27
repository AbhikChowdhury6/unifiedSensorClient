import sys
import pickle
import os
import subprocess
import threading
from datetime import datetime
from tkinter import Y
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from config import dt_to_fnString, fnString_to_dt
import logging
import numpy as np


#float32 sign=f, bits=32, endian=le, channels=1
#int32 sign=s, bits=32, endian=le, channels=1
#int16 sign=s, bits=16, endian=le, channels=1
#int8 sign=s, bits=8, endian=le, channels=1
#uint8 sign=u, bits=8, endian=le, channels=1

class wavpak_output:
    def __init__(self,
                    output_base,
                    output_hz = "1",
                    temp_write_location = "/home/pi/data/temp/",
                    debug_lvl = "warning",
                    channels = 1,
                    bits = 32,
                    sign = "f",
                    endian = "le",
                    **kwargs):
        self.output_base = output_base
        self.temp_write_location = temp_write_location
        self.channels = channels
        self.bits = bits
        self.sign = sign
        self.endian = endian
        self.variable_hz = False

        if output_hz == "variable":
            self.variable_hz = True
            self.output_hz = 48000
            self.bits = 32
            self.sign = "u"
            self.endian = "le"
            self.conversion_code = "<u4" #uint32
            self.channels += 2
        else:
            self.output_hz = max(1, int(output_hz))
            self.conversion_code = self.get_conversion_code()

        

        #this will be called casting and not rounding
        self._casting_function = None
        #parse the output base and get the data type
        self.data_type = output_base.split("_")[-3]
        if "-" in self.data_type:
            target_type = self.data_type.split("-")[0]
            try:
                self.target_dtype = getattr(np, target_type)
            except AttributeError:
                raise ValueError("Invalid target type: " + target_type)
            
            f_bits_str = self.data_type.split("-")[1][1:]
            float_bits = int(f_bits_str)
            float_scale = 2**float_bits

            info = np.iinfo(self.target_dtype)

            def _casting_function(data):
                # Compute in float to avoid overflow during scaling
                y = np.rint(np.asarray(data, dtype=np.float64) * float_scale)
                # Clamp before casting to prevent wraparound
                y = np.clip(y, info.min, info.max)
                y = y.astype(self.target_dtype)
                self.l.trace(self.log_name + " casted data: " + str(y))
                return y

            self._casting_function = _casting_function

            #now check if we are adding time or datetime channels
                    
        
        self.file_name = None
        self.temp_output_location = temp_write_location + output_base + "/"
        os.makedirs(self.temp_output_location, exist_ok=True)

        self.log_name = output_base + "_wavpak-output"
        self.l = logging.getLogger(self.log_name)
        self.l.setLevel(debug_lvl)
        self.l.info(self.log_name + " starting")

        self.l.info(self.sign + " " + str(self.bits))
        self.l.info(self.log_name + " conversion code: " + self.conversion_code)


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

        # self.st = self.additional_output_config.get("int16_storage_type", None)
        # #uint16-f9
        # if self.st is None:
        #     raise ValueError("int16_storage_type is required")
        # self.offset = 0 if self.st[0] == "u" else 2**15
        # self.scale = 2**int(self.st.split("-")[1][1:])
    
    # def convert_to_int16(self, data):
    #     return (data * self.scale + self.offset).astype(np.int16)

    def _get_casting_function(self, input_dtype_str, output_dtype_str, float_bits=None):
        input_ints = ["int16", "int32", "int64"]
        output_ints = ["int16", "int24", "int32"]
        input_floats = ["float32", "float64"]
        output_floats = ["float32"]
        input_uints = ["uint8", "uint16", "uint32", "uint64"]
        output_uints = ["uint8", "uint16", "uint32"]

        output_dtype = getattr(np, output_dtype_str)
        
        if input_dtype_str in input_ints and output_dtype_str in output_ints:
            return lambda x: self.int_to_int(x, output_dtype)

        elif input_dtype_str in input_floats and output_dtype_str in output_floats:
            return lambda x: self.float_to_float(x, output_dtype)

        elif input_dtype_str in input_uints and output_dtype_str in output_uints:
            return lambda x: self.int_to_int(x, output_dtype)
        
        elif input_dtype_str in input_ints and output_dtype_str in output_uints:
            return lambda x: self.int_to_uint(x, output_dtype)

        elif input_dtype_str in input_floats and output_dtype_str in output_ints: #add the bits
            return lambda x: self.float_to_int(x, output_dtype, float_bits)

        elif input_dtype_str in input_floats and output_dtype_str in output_uints:
            return lambda x: self.int_to_uint(self.float_to_int(x, np.int64, float_bits), output_dtype)

        else:
            raise ValueError("Invalid input or output dtype: " + input_dtype_str + " or " + output_dtype_str)
    
    def float_to_float(self, data, target_dtype):
        info = np.finfo(target_dtype)
        y = np.asarray(data, dtype=np.float64)
        y = np.clip(y, info.min, info.max)
        y = y.astype(target_dtype)
        
        if np.any(y < info.min) or np.any(y > info.max):
            self.l.warning(self.log_name + " float_to_float: values outside range: " + str(y) + " for data: " + str(data))
        return y


    def int_to_int(self, data, target_dtype):
        info = np.iinfo(target_dtype)
        y = np.asarray(data, dtype=np.int64)
        y = np.clip(y, info.min, info.max)
        y = y.astype(target_dtype)
        
        #log a warning if any values are outside the range
        if np.any(y < info.min) or np.any(y > info.max):
            self.l.warning(self.log_name + " int_to_int: values outside range: " + str(y) + " for data: " + str(data))
        return y

    def float_to_int(self, data, target_dtype, float_bits):
        if float_bits is None:
            raise ValueError("float_bits is required")

        float_scale = 2**float_bits
        info = np.iinfo(target_dtype)
        
        
        y = np.asarray(data, dtype=np.float64)
        y = y * float_scale
        y = np.rint(y)
        y = np.clip(y, info.min, info.max)
        y = y.astype(target_dtype)
        
        #log a warning if any values are outside the range
        if np.any(y < info.min) or np.any(y > info.max):
            self.l.warning(self.log_name + " float_to_int: values outside range: " + str(y) + " for data: " + str(data))

        return y

    def int_to_uint(self, data, target_dtype):
        #put data in an int64 for now
        y = data.astype(np.int64)

        #get target dtype info
        info = np.iinfo(target_dtype)
        range = info.max - info.min
        offset = int(range/2)
        
        #add the offset and convert to the target dtype
        y = y + offset
        y = np.clip(y, info.min, info.max)
        y = y.astype(target_dtype)

        #log a warning if any values are outside the range
        if np.any(y < info.min) or np.any(y > info.max):
            self.l.warning(self.log_name + " int_to_uint: values outside range: " + str(y))
        
        return y
    
    def get_conversion_code(self):
        #float16, float32, float64
        if self.sign == "f":
            if self.bits == 32:
                return "<f4"
            else:
                raise ValueError("Invalid bits: " + str(self.bits))
        
        #int16, int32, int64
        elif self.sign == "s":
            if self.bits == 16:
                return "<i2"
            elif self.bits == 24:
                return "<i3"
            elif self.bits == 32:
                return "<i4"
            else:
                raise ValueError("Invalid bits: " + str(self.bits))
        
        #uint8, uint16, uint32
        elif self.sign == "u":
            if self.bits == 8:
                return "<u1"
            elif self.bits == 16:
                return "<u2"
            elif self.bits == 32:
                return "<u4"
            else:
                raise ValueError("Invalid bits: " + str(self.bits))
        else:
            raise ValueError("Invalid sign: " + self.sign)
    
    def persist(self, dt, data):
        if self._casting_function is not None:
            data = self._casting_function(data)
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

        wavpack_cmd = ["wavpack", "-hh", self.raw_spec, "-", "-o", self.temp_output_location + self.file_name]
        self.l.debug(self.log_name + " wavpack command: " + " ".join(wavpack_cmd))
        self.proc = subprocess.Popen(wavpack_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        t = threading.Thread(target=self._stderr_reader, args=(self.proc,), daemon=True)
        t.start()
        self.proc._stderr_thread = t  # attach for lifecycle awareness
        self.file_name = self.file_name + self.extension
        self.l.info(self.log_name + " opened wavpack writer: " + self.file_name)
        return self.file_name
    
    def write(self, data):        
        if self._casting_function is not None:
            data = self._casting_function(data)
        
        # I think flatten will put all of the values in the right order
        data = data.flatten()
        self.l.trace(self.log_name + " writing data: " + str(data))
        data_le = data.astype(self.conversion_code, copy=False)

        #order="C" is for ???
        self.l.trace(self.log_name + " writing " + str(data_le.tobytes(order="C").hex()))
        self.proc.stdin.write(data_le.tobytes(order="C"))

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