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
import random

class output:
    def __init__(self, file_name):
        self.file_name = file_name
        self.file = open(file_name, "wb")
    
    def write(self, data):
        self.file.write(data)
    
    def close(self):
        self.file.close()


class Writer:
    def __init__(self, config, output, persist, load_function):
        self.config = config
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
        self.persist = persist
        self.load = load_function
        
        self.output = output
        self.output_file = ""
        self.output_start_dt = None

        #deciding to close
        self.last_dt = None
        self.target_file_size_mb = config["target_file_size_mb"]
        self.next_size_check_dt = datetime.min.replace(tzinfo=timezone.utc)
        self.size_check_interval_s_range = (30, 60)
        self.expected_hz = config["expected_hz"]

        #if the last move or anything else failed, delete all the temp files
        for file in os.listdir(self.temp_file_location).sorted():
            os.remove(self.temp_file_location + file)
        
        #check for files in cache and recover
        self._recover_from_cache()

    def _recover_from_cache(self):
        files = os.listdir(self.cache_location).sorted()
        if len(files) == 0:
            return
        self.l.info(self.config["short_name"] + " writer found " + str(len(files)) + " files in cache")
        
        for file in files:
            dt, data = self.load(self.cache_location + file)
            self.write(dt, data)

    def _open_file(self, dt): 
        self.output_start_dt = dt
       
        self.output_file = self.output.open(dt)

    def _close_file(self, dt):
        self.output_file = self.output.close(dt)

        #move the file to the correct location in data
        finished_file_name = self.output_base + self.output_file
        infile = self.temp_file_location + self.output_file
        outfile = self.completed_file_location + finished_file_name
        shutil.move(infile, outfile)
        self.output_file = None
        self.last_dt = None
        
        #delete all the cached files , they should all be older than the last dt
        for file in os.listdir(self.cache_location).sorted():
            os.remove(self.cache_location + file)

    def _should_close(self, dt):
        if self.output.file_name is None:
            return False
        #new day
        if dt.date() != self.last_dt.date():
            return True
        #too long since last write
        if dt - self.last_dt > 2 * timedelta(seconds=1/self.expected_hz):
            return True

        # Get the current size on disk of the output file
        if dt < self.next_size_check_dt:
            return False
        
        rand_s = random.randint(*self.size_check_interval_s_range)
        self.next_size_check_dt = dt + timedelta(seconds=rand_s)
        
        out_file_and_path = self.temp_file_location + self.output_file
        output_size = os.path.getsize(out_file_and_path)
        if output_size > self.target_file_size_mb * 1024 * 1024:
            return True
        
        return False

    def write(self, dt, data):
        if self._should_close(dt):
            self._close_file(dt)

        self.persist(dt, data)
        
        if self.output.file_name is None:
            self.output.open(dt)
        
        self.output.write(data)

        self.last_dt = dt
        





