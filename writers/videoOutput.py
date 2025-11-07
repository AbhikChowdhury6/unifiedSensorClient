import sys
import qoi
import os
import cv2
from datetime import datetime
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
import logging
from config import dt_to_fnString, fnString_to_dt

class video_output:
    def __init__(self, config):
        self.config = config
        self.log_name = self.config["topic"] + "_video-output"
        self.l = logging.getLogger(self.log_name)
        self.l.setLevel(self.config['debug_lvl'])
        self.l.info(self.log_name + " starting")
        self.file_name = None
        self.output = None
        self.file_base = self.config["topic"]

        self.fps = config["fps"]
        self.camera_width = config["camera_width"]
        self.camera_height = config["camera_height"]
        self.fourcc = cv2.VideoWriter_fourcc(*'avc1')
        self.temp_output_location = self.config["temp_write_location"] + self.config["topic"] + "/"
    
    def persist(self, dt, data, path):
        fn = path + dt_to_fnString(dt) + ".qoi"
        qoi.write(fn, data)
    
    def load(self, path):
        return fnString_to_dt(path), qoi.read(path)
    
    def open(self, dt):
        self.file_name = self.file_base + "_" + dt_to_fnString(dt) + ".mp4"
        self.output = cv2.VideoWriter(self.temp_output_location + self.file_name, 
                                self.fourcc, 
                                self.fps, 
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
        self.output.write(data)
