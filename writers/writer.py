import logging
import os
import sys
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")

import logging
import shutil
from datetime import datetime, timezone, timedelta
import random
import zmq

from platformUtils.zmq_codec import ZmqCodec
class Writer:
    def __init__(self,
                    output,
                    temp_write_location,
                    output_write_location,
                    target_file_size,
                    file_size_check_interval_s_range,
                    platform_uuid,
                    debug_lvl = 30,
                    **kwargs
                    ):
        self.output_base = output.output_base
        self.object_name = self.output_base + "_writer-object"
        self.temp_write_location = temp_write_location
        self.output_write_location = output_write_location
        self.platform_uuid = platform_uuid
        self.target_file_size = target_file_size
        self.file_size_check_interval_s_range = file_size_check_interval_s_range
        self.hz = max(1, output.output_hz)
        self.output = output
        self.output_file = None

        self.l = logging.getLogger(self.object_name)
        self.debug_lvl = debug_lvl
        self.l.setLevel(debug_lvl)
        self.l.info(self.object_name + " starting")

        output_endpoint = f"ipc:///tmp/{self.output_base}.sock"
        self.pub = zmq.Context().socket(zmq.PUB)
        self.pub.bind(output_endpoint)
        self.l.info(self.object_name + " publishing to " + output_endpoint)

        self.persist_location = temp_write_location + self.output_base + "_persist" + "/"
        os.makedirs(self.persist_location, exist_ok=True)
        self.temp_output_location = temp_write_location + self.output_base + "/"
        os.makedirs(self.temp_output_location, exist_ok=True)
        self.completed_output_location = output_write_location + self.output_base + "/"
        os.makedirs(self.completed_output_location, exist_ok=True)

        #deciding to close
        self.last_dt = None
        self.next_size_check_dt = datetime.now(timezone.utc) + \
            timedelta(seconds=random.randint(*self.file_size_check_interval_s_range))

        #if the last move or anything else failed, delete all the temp files
        for file in sorted(os.listdir(self.temp_output_location)):
            os.remove(self.temp_output_location + file)
        
        #check for files in cache and recover
        self._recover_from_cache()

    def _recover_from_cache(self):
        for dt, data in self.output.load():
            self.log(5, lambda:self.object_name + " recovering frame: " + str(dt) + " with shape: " + str(data.shape))
            self.write(dt, data)

    def _open_file(self, dt): 
        self.output_start_dt = dt
       
        self.output_file = self.output.open(dt)

    def _close_file(self, dt):
        self.output_file = self.output.close(dt)
        infile = self.temp_write_location + self.output_base + "/" + self.output_file

        #move the file to the correct location in data
        self.output_file = self.platform_uuid + "_" + self.output_file
        outfile = self.output_write_location + self.output_base + "/" + self.output_file
        shutil.move(infile, outfile)
        self.pub.send_multipart(ZmqCodec.encode(self.object_name, [dt, outfile]))
        self.output_file = None
        self.last_dt = None
        
        #delete all the cached files , they should all be older than the last dt
        for file in sorted(os.listdir(self.persist_location)):
            os.remove(self.persist_location + file)

    def _should_close(self, dt):
        if self.output.file_name is None:
            self.log(10, self.object_name + " file is not open")
            return False

        #new day
        if dt.date() != self.last_dt.date():
            self.log(10, self.object_name + " new day")
            return True
        
        #too long since last write
        if dt - self.last_dt > timedelta(seconds=1/self.hz):
            self.log(10, self.object_name + " too long since last write")
            self.log(10, lambda:self.object_name + " too long since last write: " + str(dt - self.last_dt) + " seconds")
            return True

        # Get the current size on disk of the output file
        if dt < self.next_size_check_dt:
            return False
        
        rand_s = random.randint(*self.file_size_check_interval_s_range)
        self.next_size_check_dt = dt + timedelta(seconds=rand_s)
        
        self.output_file = self.output.file_name
        out_file_and_path = self.temp_write_location + self.output_base + "/" + self.output_file
        output_size = os.path.getsize(out_file_and_path)
        if output_size > self.target_file_size:
            self.log(10, self.object_name + " output size is too large")
            return True
        
        return False

    def log(self, lvl:int, msg):
        if lvl < self.debug_lvl:
            return
        if callable(msg):
            msg = msg()
        if lvl == 5:
            self.l.trace(msg)
        elif lvl == 10:
            self.l.debug(msg)
        elif lvl == 20:
            self.l.info(msg)
        elif lvl == 30:
            self.l.warning(msg)
        elif lvl == 40:
            self.l.error(msg)
        elif lvl == 50:
            self.l.critical(msg)

    def write(self, dt, data):
        
        # handle if we get a chunk of data that spans 2 days
        if data.shape[0] > 1:
            end_dt = dt + timedelta(seconds=(data.shape[0]-1)/self.hz)
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

        if self.debug_lvl <= 5: start_time = datetime.now().timestamp()
        if self._should_close(end_dt):
            self.log(5, lambda:self.object_name + " should close time: " + str(datetime.now().timestamp() - start_time))
            self.log(20, lambda:self.object_name + " should close at " + str(end_dt))
            if self.debug_lvl <= 5: start_time = datetime.now().timestamp()
            self._close_file(end_dt)
            self.log(5, lambda:self.object_name + " close file time: " + str(datetime.now().timestamp() - start_time))
        
        if self.debug_lvl <= 5: start_time = datetime.now().timestamp()
        self.output.persist(dt, data)
        self.log(5, lambda:self.object_name + " persist time: " + str(datetime.now().timestamp() - start_time))
        
        if self.output.file_name is None:
            if self.debug_lvl <= 5: start_time = datetime.now().timestamp()
            self.output.open(dt)
            self.log(5, lambda:self.object_name + " open time: " + str(datetime.now().timestamp() - start_time))
        
        if self.debug_lvl <= 5: start_time = datetime.now().timestamp()
        self.output.write(data)
        self.log(5, lambda:self.object_name + " write time: " + str(datetime.now().timestamp() - start_time))

        self.last_dt = end_dt
    
    def close(self):
        if self.output.file_name is not None:
            if self.debug_lvl <= 5: start_time = datetime.now().timestamp()
            self._close_file(self.last_dt)
            
            self.log(5, lambda:self.object_name + " close time: " + str(datetime.now().timestamp() - start_time))
        self.log(20, lambda:self.object_name + " closing")
        





