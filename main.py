# start all of the processes

import os
import sys
import select
import time
import zmq
import multiprocessing as mp

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from i2cController import I2C_BUS
from csvWriter import csv_writer
from sqliteWriter import sqlite_writer
from h264Writer import h264_writer
from jpegWriter import jpeg_writer
from videoController import videoController
from config import (
    zmq_control_endpoint,
    cameras,
)
from zmq_codec import ZmqCodec
from yoloPersonDetector import yolo_person_detector


if __name__ == "__main__":
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.bind(zmq_control_endpoint)

    

    # Start subscribers first to avoid slow-joiner drops
    csv_process = mp.Process(target=csv_writer)
    csv_process.start()

    sqlite_process = mp.Process(target=sqlite_writer)
    sqlite_process.start()

    # Give subscribers a moment to connect and subscribe
    time.sleep(0.5)

    # Start publisher/producer last
    i2c_process = mp.Process(target=I2C_BUS)
    i2c_process.start()


    video_process = mp.Process(target=videoController)
    video_process.start()

    time.sleep(1)

    h264_process = mp.Process(target=h264_writer)
    h264_process.start()

    jpeg_process = mp.Process(target=jpeg_writer)
    jpeg_process.start()

    yolo_person_detector_process = mp.Process(target=yolo_person_detector)
    yolo_person_detector_process.start()

    processes = {
        "i2c": i2c_process,
        "csv": csv_process,
        "sqlite": sqlite_process,
        "h264": h264_process,
        "video": video_process,
        "jpeg": jpeg_process,
        "yolo_person_detector": yolo_person_detector_process,
    }

    while True:
        if any(not processes[p].is_alive() for p in processes):
            for p in processes:
                print(p, processes[p].is_alive())
            pub.send_multipart(ZmqCodec.encode("control", "exit"))
            break


        if select.select([sys.stdin], [], [], 0)[0]:
            if sys.stdin.read(1) == 'q':
                print("got q going to start exiting")
                pub.send_multipart(ZmqCodec.encode("control", "exit"))
                break
    time.sleep(1)
