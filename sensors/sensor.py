from datetime import datetime, timedelta, timezone
import time
import zmq
import numpy as np

import sys

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from platformUtils.zmq_codec import ZmqCodec
import logging


class Sensor:
    def __init__(self, config, retrieve_data, is_ready=lambda: True):
        #timing
        self.hz = config['update_hz']
        self.delay_micros = int(1_000_000/self.hz)
        #self.timestamp_rounding_bits = config['timestamp_rounding_bits']
        #self.trillionths = 1_000_000_000_000/(2**self.timestamp_rounding_bits)
        self.retrive_after = datetime.fromtimestamp(0, tz=timezone.utc)

        #data descriptor
        self.platform_uuid = config['platform_uuid']
        self.bus_location = config['bus_location']
        self.device_name = config['device_name'] # manufacturer-model-address
        self.sensor_type = config['sensor_type']
        self.units = config['units'] # dash separated units if multiple
        self.data_type = config['data_type']
        #self.float_rounding_precision = config['float_rounding_precision']

        #zmq
        self.topic = "_".join([self.platform_uuid, 
                                self.bus_location, 
                                self.device_name, 
                                self.sensor_type, 
                                self.units, 
                                self.data_type])
        self.endpoint = f"ipc:///tmp/{self.topic}.sock"
        self.ctx = zmq.Context()
        self.pub = self.ctx.socket(zmq.PUB)
        self.pub.bind(self.endpoint)

        #logging setup
        self.l = logging.getLogger(self.topic)
        self.l.setLevel(config["debug_lvl"])
        self.l.info(self.topic + " connected to " + self.endpoint)
        time.sleep(.25)

        #ready
        self.is_ready = is_ready
        while not self.is_ready():
            self.l.info(self.topic + " waiting for data...")
            time.sleep(self.delay_micros/1_000_000)
        _ = self.retrieve_data() # a warmup reading
        time.sleep(.25)
        
        #calculate the estimated read time
        ts = datetime.now(timezone.utc)
        _ = self.retrieve_data()
        self.max_read_micros = (datetime.now(timezone.utc) - ts).total_seconds() * 1_000_000
        self.l.info("estimated read time for " + self.topic + " is " + str(self.max_read_micros) + " microseconds")


    def read_data(self):
        #check if it's the right time to read the data
        now = datetime.now(timezone.utc)
        if now < self.retrive_after:
            return
        
        if not self.is_ready():
            return

        #read the data
        new_data = self.retrieve_data()
        read_micros = (datetime.now() - now).total_seconds() * 1_000_000
        self.max_read_micros = max(self.max_read_micros, read_micros)
        self.l.trace("read time: " + str(read_micros) + " microseconds")
        self.l.trace("max read time: " + str(self.max_read_micros) + " microseconds")
        if new_data is None:
            self.l.error("no data read from " + self.topic)
            return
        self.l.trace("data read from " + self.topic + ": " + str(len(new_data)) + " bytes")
        
        #round ts to the nearest hz seconds
        if self.hz <= 1:
            now = now.replace(microsecond=0)
            prev_second = int(now.timestamp() // self.hz) * self.hz
            now = datetime.fromtimestamp(prev_second, tz=timezone.utc)
        else:
            rounded_down_micros = (now.microsecond//self.delay_micros) * self.delay_micros
            now = now.replace(microsecond=int(rounded_down_micros))# round down to the nearest delay micros
        
        self.retrive_after = now + timedelta(microseconds=self.delay_micros)
        self.l.trace("next read after" + str(self.retrive_after))

        # convert to numpy array before sending
        new_data_np = np.array(new_data)
        self.pub.send_multipart(ZmqCodec.encode(self.topic, [now, new_data_np]))