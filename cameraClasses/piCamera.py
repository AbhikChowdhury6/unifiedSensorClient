import zmq
import numpy as np
import sys
import os
import picamera2
import cv2
from datetime import datetime, timezone
import tzlocal
import gc
import qoi

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec
import logging
from config import dt_to_fnString


class PiCamera:
    def __init__(self, camera_config):
        self.l = logging.getLogger(camera_config["short_name"])
        self.l.setLevel(camera_config['debug_lvl'])
        self.camera_config = camera_config
        self.flip_vertical = camera_config['flip_vertical']
        self._enabled = False
        self.ctx = zmq.Context()
        self.pub = self.ctx.socket(zmq.PUB)
        self.pub.bind(self.camera_config['camera_endpoint'])
        self.l.info(f"camera {self.camera_config['camera_name']} connected to {self.camera_config['camera_endpoint']}")
        sys.stdout.flush()

        self.topic = self.camera_config['camera_name']
        self.save_location = self.camera_config['save_location']
        
        st = datetime.now()
        self.camera = picamera2.Picamera2(self.camera_config['camera_index'])
        self.video_config = self.camera.create_video_configuration(main={
            "size": (self.camera_config['camera_width'], self.camera_config['camera_height']), 
            "format": self.camera_config['format']})
        self.camera.configure(self.video_config)
        self.camera.start()
        self.l.info("Camera initialized in %s", str(datetime.now()  - st))
        st = datetime.now()
        frame = self.camera.capture_array()
        self.l.info("The first Frame took %s to capture", str(datetime.now()  - st))
        st = datetime.now()
        frame = self.camera.capture_array()
        self.l.info("The second Frame took %s to capture", str(datetime.now()  - st))
        del frame
        gc.collect()

        self.subsample_ratio = self.camera_config['subsample_ratio']
        self.timestamp_images = self.camera_config['timestamp_images']

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    def capture(self):
        dt_utc = datetime.now(timezone.utc)
        frame = self.camera.capture_array().astype(np.uint8)
        if self.subsample_ratio > 1:
            frame = frame[::self.subsample_ratio, ::self.subsample_ratio]
            frame = np.ascontiguousarray(frame)
        if self.flip_vertical:
            frame = cv2.flip(frame, 0)
        if self.timestamp_images:
            frame = self.add_timestamp(frame)
        

        output_path = self.save_location + dt_to_fnString(dt_utc) + ".qoi"
        qoi.write(output_path, frame)
        self.pub.send_multipart(ZmqCodec.encode(self.topic, [dt_utc, frame]))
    
    def is_enabled(self):
        return self._enabled
    
    def add_timestamp(self, frame):
        frameTS = datetime.now(tzlocal.get_localzone()).strftime("%Y-%m-%d %H:%M:%S %z")
        cv2.putText(frame, frameTS, (10, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1, 
                (0, 255, 0), 2, cv2.LINE_AA)
        return frame