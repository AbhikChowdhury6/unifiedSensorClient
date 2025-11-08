import logging
import os
import sys
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")

import logging
import shutil
from datetime import datetime, timezone, timedelta
import random



class Writer:
    def __init__(self, config, output):
        self.config = config
        self.process_name = config["topic"] + "_writer-process"
        self.l = logging.getLogger(self.process_name)
        self.l.setLevel(config['debug_lvl'])
        self.l.info(self.process_name + " starting")

        self.persist_location = config["temp_write_location"] + config["topic"] + "_persist" + "/"
        os.makedirs(self.persist_location, exist_ok=True)
        self.temp_output_location = config["temp_write_location"] + config["topic"] + "/"
        os.makedirs(self.temp_output_location, exist_ok=True)
        self.completed_output_location = config["completed_write_location"] + config["topic"] + "/"
        os.makedirs(self.completed_output_location, exist_ok=True)

        #deciding to close
        self.last_dt = None
        self.target_file_size = config["target_file_size"]
        self.next_size_check_dt = datetime.min.replace(tzinfo=timezone.utc)
        self.size_check_interval_s_range = config["file_size_check_interval_s_range"]
        self.hz = max(1, config["hz"])

        #if the last move or anything else failed, delete all the temp files
        for file in os.listdir(self.temp_file_location).sorted():
            os.remove(self.temp_file_location + file)
        
        #check for files in cache and recover
        self._recover_from_cache()

    def _recover_from_cache(self):
        for dt, data in self.output.load():
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
        if dt - self.last_dt > 2 * timedelta(seconds=1/self.hz):
            return True

        # Get the current size on disk of the output file
        if dt < self.next_size_check_dt:
            return False
        
        rand_s = random.randint(*self.size_check_interval_s_range)
        self.next_size_check_dt = dt + timedelta(seconds=rand_s)
        
        out_file_and_path = self.temp_file_location + self.output_file
        output_size = os.path.getsize(out_file_and_path)
        if output_size > self.target_file_size:
            return True
        
        return False

    def write(self, dt, data):
        
        # handle if we get a chunk of data that spans 2 days
        if data.ndim > 1:
            end_dt = dt + timedelta(seconds=data.shape[0]/self.hz)
            if end_dt.date() != dt.date():
                #calc the data index for the end of the day
                start_of_next_day = end_dt.replace(hour=0, minute=0, second=0, microsecond=0)\
                     + timedelta(days=1)
                samples_till_eod = (start_of_next_day.timestamp() - dt.timestamp()) * self.hz
                self.output.persist(dt, data[:samples_till_eod])
                self.output.write(data[:samples_till_eod])
                self.output.close(start_of_next_day-timedelta(seconds=1/self.hz))
                self.output.persist(start_of_next_day, data[samples_till_eod:])
                self.output.open(start_of_next_day)
                self.output.write(data[samples_till_eod:])
                self.last_dt = end_dt
                return
        else:
            end_dt = dt

        
        if self._should_close(end_dt):
            self._close_file(end_dt)

        self.output.persist(dt, data)
        
        if self.output.file_name is None:
            self.output.open(dt)
        
        self.output.write(data)

        self.last_dt = end_dt
    
    def close(self):
        if self.output.file_name is not None:
            self._close_file(self.last_dt)
        self.l.info(self.process_name + " closing")
        





