import logging
import os
import sys
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
from datetime import datetime, timezone, timedelta


class output:
    def __init__(self, file_name):
        self.file_name = file_name
        self.file = open(file_name, "wb")
    
    def write(self, data):
        self.file.write(data)
    
    def close(self):
        self.file.close()


class Writer:
    def __init__(self, config, output, perisist, open_function):
        self.l = logging.getLogger(config["short_name"])
        self.l.setLevel(config['debug_lvl'])
        self.l.info(config["short_name"] + " writer starting")

        self.cache_location = config["cache_location"]
        os.makedirs(self.cache_location, exist_ok=True)
        self.temp_file_location = config["temp_file_location"]
        os.makedirs(self.temp_file_location, exist_ok=True)
        self.completed_file_location = config["completed_file_location"]
        os.makedirs(self.completed_file_location, exist_ok=True)

        self.output_base = config["output_base"]
        self.extension = config["extension"]
        
        self.output = output
        self.output_file = ""
        self.output_start_dt = None

        #deciding to close
        self.previous_dt = None
        self.target_file_size_mb = config["target_file_size_mb"]
        self.expected_hz = config["expected_hz"]

        #check for files in cache and recover


    def _recover_from_cache(self):
        files = os.listdir(self.cache_location).sorted()
        if len(files) == 0:
            return
        self.l.info(config["short_name"] + " writer found " + str(len(files)) + " files in cache")
        
        for file in files:
            self.write(fnString_to_dt(file), open_function(file))

    def _open_file(self, dt): 
        self.output_start_dt = dt
        self.output_file = self.temp_file_location + self.output_base + "_" + dt_to_fnString(dt) + "." + self.extension        
        self.output.open(dt)

    def _close_file(self, dt):
        self.output.close()
        #rename the file with the end timestamp to signal it is complete
        #move the file to the correct location in data
        #delete the cached files older than the last dt
        #delete all the cached files older than the last dt
        pass

    def _should_close(self, dt):
        if dt.date() != self.last_dt.date():
            return True
        if dt - self.last_dt > timedelta(seconds=1/self.expected_hz):
            return True

        #figure out how to get this from the files system
        output_size = None
        if self.output.size > self.target_file_size_mb * 1024 * 1024:
            return True
        return False

    def write(self, dt, data):
        if self._should_close(dt):
            self._close_file(dt)

        if self.output.is_open is False:
            self.output.open(dt)
        
        self.output.write(data)
        
        





