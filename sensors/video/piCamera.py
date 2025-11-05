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
from platformUtils.zmq_codec import ZmqCodec
import logging
from config import dt_to_fnString
from sensors.sensor import Sensor


class PiCamera:
    def __init__(self, camera_config):
        self.l = logging.getLogger(camera_config["class_name"] + "-" 
                                    + camera_config["bus_location"] + "-" 
                                    + camera_config["device_name"])
        self.l.setLevel(camera_config['debug_lvl'])
        self.camera_config = camera_config
        self.flip_vertical = camera_config['flip_vertical']
        self.subsample_ratio = camera_config['subsample_ratio']
        self.timestamp_images = camera_config['timestamp_images']

        self.camera = picamera2.Picamera2(camera_config['camera_index'])
        self.video_config = self.camera.create_video_configuration(main={
            "size": (camera_config['camera_width'], camera_config['camera_height']), 
            "format": camera_config['format']})
        self.camera.configure(self.video_config)
        self.camera.start()
        
        self.sensor = Sensor(self.camera_config, self._capture)


    def _capture(self):
        frame = self.camera.capture_array().astype(np.uint8)
        if self.subsample_ratio > 1:
            frame = frame[::self.subsample_ratio, ::self.subsample_ratio]
            frame = np.ascontiguousarray(frame)
        if self.flip_vertical:
            frame = cv2.flip(frame, 0)
        if self.timestamp_images:
            frame = self._add_timestamp(frame)

        return frame
    

    def _add_timestamp(self, frame):
        frameTS = datetime.now(tzlocal.get_localzone()).strftime("%Y-%m-%d %H:%M:%S %z")
        cv2.putText(frame, frameTS, (10, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1, 
                (0, 255, 0), 2, cv2.LINE_AA)
        return frame




        # # Prepare frame for QOI: uint8, HxWx3 or 4, C-contiguous, RGB order
        # try:
        #     if not frame.flags.get('C_CONTIGUOUS', True):
        #         frame = np.ascontiguousarray(frame)
        #     if frame.dtype != np.uint8:
        #         frame = frame.astype(np.uint8, copy=False)
        #     # If using OpenCV operations, ensure channel order is RGB for QOI
        #     # picamera2 with format 'RGB888' yields RGB already; if config format suggests BGR, convert
        #     fmt = str(self.camera_config.get('format', 'RGB888')).upper()
        #     if fmt in ('BGR24', 'BGR888', 'BGR'):
        #         frame_qoi = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        #     else:
        #         frame_qoi = frame
        # except Exception:
        #     frame_qoi = frame

        # output_path = os.path.join(self.save_location, dt_to_fnString(dt_utc) + ".qoi")
        # try:
        #     qoi.write(output_path, frame_qoi)
        # except Exception as e:
        #     self.l.error("qoi write failed for " + output_path + ": " + str(e))