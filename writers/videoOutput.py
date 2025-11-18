import sys
import qoi
import os
import cv2
from datetime import datetime, timedelta
import numpy as np
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
import logging
from config import dt_to_fnString, fnString_to_dt

class video_output:
    def __init__(self,
                    output_base,
                    temp_write_location,
                    hz,
                    camera_width,
                    camera_height,
                    fourcc = "avc1",
                    debug_lvl = 30,
                    **kwargs):
        
        self.output_base = output_base
        self.temp_write_location = temp_write_location
        self.output_hz = max(1, hz)
        self.camera_width = camera_width
        self.camera_height = camera_height
        self.fourcc = fourcc
        self.debug_lvl = debug_lvl

        self.log_name = output_base + "_video-output"
        self.l = logging.getLogger(self.log_name)
        self.l.setLevel(debug_lvl)
        self.l.info(self.log_name + " starting")
        self.file_name = None
        self.output = None
        self.file_base = output_base
        self.persist_location = temp_write_location + output_base + "/"
        os.makedirs(self.persist_location, exist_ok=True)

        self.camera_width = camera_width
        self.camera_height = camera_height
        self.fourcc = cv2.VideoWriter_fourcc(*'avc1')
        self.temp_output_location = temp_write_location + output_base + "/"
        os.makedirs(self.temp_output_location, exist_ok=True)
    
    def persist(self, dt, data):
        for i in range(data.shape[0]):
            frame_dt = dt + timedelta(seconds=i/self.output_hz)
            fn = self.persist_location + dt_to_fnString(frame_dt) + ".qoi"
            qoi.write(fn, data[i])
    
    def load(self):
        files = sorted(os.listdir(self.persist_location))
        if len(files) == 0:
            return
        self.l.info(self.log_name + " found " + str(len(files)) + " files in cache")
        
        for file in files:
            data = qoi.read(self.persist_location + file)
            data = np.expand_dims(data, axis=0)
            yield fnString_to_dt(file), data
    
    def open(self, dt):
        self.file_name = self.file_base + "_" + dt_to_fnString(dt) + ".mp4"
        self.output = cv2.VideoWriter(self.temp_output_location + self.file_name, 
                                self.fourcc, 
                                self.output_hz, 
                                (self.camera_width, self.camera_height))
        if not self.output.isOpened():
            self.l.error("Failed to open video writer")
            return None

        return self.file_name
    
    def close(self, dt):
        if self.output is not None:
            self.output.release()
        self.output = None
        
        new_fn = self.file_name.replace(".mp4", "_" + dt_to_fnString(dt) + ".mp4")
        os.rename(self.temp_output_location + self.file_name, 
                  self.temp_output_location + new_fn)
        self.file_name = None
        return new_fn

    def write(self, data):
        for frame in data:
            self.output.write(frame)
