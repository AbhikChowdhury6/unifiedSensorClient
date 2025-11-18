from datetime import datetime, timedelta, timezone
import time
import zmq
import numpy as np

import sys

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from platformUtils.zmq_codec import ZmqCodec
import logging
import multiprocessing as mp
from writers.processes.writerProcess import writer_process
from config import camera_topic, camera_endpoint


class Sensor:
    def __init__(self, 
                    platform_uuid = None,
                    bus_location = None,
                    device_name = None,
                    sensor_type = None,
                    units = None,
                    data_type = None,
                    shape = None,
                    hz = None,
                    log_queue = None,
                    file_writer_config = {},
                    debug_lvl = 30,
                    retrieve_data = lambda: None,
                    is_ready=lambda: True,
                    **kwargs
                    ):
        
        if log_queue is None:
            raise ValueError("log_queue is required")
        self.log_queue = log_queue
        self.debug_lvl = debug_lvl
        self.l = logging.getLogger("sensor_startup")
        self.l.setLevel(debug_lvl)
        time.sleep(.25)
        
        if retrieve_data is None:
            raise ValueError("retrieve_data is required")
        self.retrieve_data = retrieve_data
        #timing
        self.hz = hz
        self.delay_micros = int(1_000_000/self.hz)
        #self.timestamp_rounding_bits = config['timestamp_rounding_bits']
        #self.trillionths = 1_000_000_000_000/(2**self.timestamp_rounding_bits)
        self.retrive_after = datetime.fromtimestamp(0, tz=timezone.utc)

        #data descriptor
        self.platform_uuid = platform_uuid
        self.bus_location = bus_location
        self.device_name = device_name # manufacturer-model-address
        self.sensor_type = sensor_type
        self.units = units # dash separated units if multiple
        self.data_type = data_type
        self.shape = shape # nxn
        print(str(self.platform_uuid) + " " +
                     str(self.bus_location) + " " + 
                     str(self.device_name) + " " + 
                     str(self.sensor_type) + " " + 
                     str(self.units) + " " + 
                     str(self.data_type) + " " + 
                     str(self.shape) + " " + 
                     str(self.hz) + "hz")
        sys.stdout.flush()
        #self.float_rounding_precision = config['float_rounding_precision']

        #zmq
        self.topic = "_".join([self.platform_uuid, 
                                self.bus_location, 
                                self.device_name, 
                                self.sensor_type, 
                                self.units, 
                                self.data_type,
                                self.shape,
                                str(self.hz) + "hz"])
        self.endpoint = f"ipc:///tmp/{self.topic}.sock"
        self.ctx = zmq.Context()
        self.pub = self.ctx.socket(zmq.PUB)
        self.pub.bind(self.endpoint)

        #logging setup
        self.l = logging.getLogger(self.topic)
        self.l.setLevel(debug_lvl)
        self.l.info(self.topic + " connected to " + self.endpoint)
        self.l.info(self.topic)
        self.l.info(camera_topic)
        self.l.info(self.endpoint)
        self.l.info(camera_endpoint)


        #ready
        self.is_ready = is_ready
        while not self.is_ready():
            self.l.info(self.topic + " waiting for data...")
            time.sleep(self.delay_micros/1_000_000)
        _ = self.retrieve_data() # a warmup reading
        time.sleep(.25)

        self.last_read_ts = None
        
        #calculate the estimated read time
        ts = datetime.now(timezone.utc)
        _ = self.retrieve_data()
        self.max_read_micros = (datetime.now(timezone.utc) - ts).total_seconds() * 1_000_000
        self.l.info("estimated read time for " + self.topic + " is " + str(self.max_read_micros) + " microseconds")

        #check if the writer is enabled
        self.writer_process = None
        if file_writer_config:
            wc = file_writer_config
            if "additional_output_config" not in wc:
                wc["additional_output_config"] = {}
            wc["additional_output_config"]["log_queue"] = log_queue
            writer_args = {
                           "debug_lvl": debug_lvl,
                           "log_queue": log_queue,
                           "topic": self.topic,
                           "hz": self.hz,
                           "output_hz": wc["output_hz"],
                           "output_base": wc["output_base"],
                           "output_module": wc["output_module"],
                           "file_size_check_interval_s_range": wc["file_size_check_interval_s_range"],
                           "additional_output_config": wc["additional_output_config"]}
            self.writer_process = mp.Process(target=writer_process, name=self.topic + "_writer-process", kwargs=writer_args)
            self.writer_process.start()
            self.writer_process.is_alive()

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
    
    def read_data(self):
        #check if it's the right time to read the data
        now = datetime.now(timezone.utc)
        if now < self.retrive_after:
            return
        
        if not self.is_ready():
            return

        self.log(5, lambda: "reading data from " + self.topic)
        #read the data
        new_data = self.retrieve_data()
        read_micros = (datetime.now(timezone.utc) - now).total_seconds() * 1_000_000
        self.max_read_micros = max(self.max_read_micros, read_micros)
        self.log(5, lambda: "read time: " + str(read_micros) + " microseconds")
        self.log(5, lambda: "max read time: " + str(self.max_read_micros) + " microseconds")
        if new_data is None:
            self.log(40, lambda: "no data read from " + self.topic)
            return
        self.log(5, lambda: "data read from " + self.topic + ": " + str(len(new_data)) + " bytes")
        
        #round ts to the nearest hz seconds
        if self.hz <= 1:
            now = now.replace(microsecond=0)
            prev_second = int(now.timestamp() // self.hz) * self.hz
            now = datetime.fromtimestamp(prev_second, tz=timezone.utc)
        else:
            rounded_down_micros = (now.microsecond//self.delay_micros) * self.delay_micros
            now = now.replace(microsecond=int(rounded_down_micros))# round down to the nearest delay micros
        
        self.retrive_after = now + timedelta(microseconds=self.delay_micros)
        self.log(5, lambda: "next read after" + str(self.retrive_after))

        # convert to numpy array before sending
        new_data_np = np.array(new_data)
        if self.last_read_ts is not None:
            time_since_last_read = now.timestamp() - self.last_read_ts
            if time_since_last_read > 1/self.hz:
                self.log(30, lambda: self.topic + " time since last read is greater than 1/hz")
                self.log(30, lambda: self.topic + " time since last read: " + str(time_since_last_read) + " seconds")
                self.log(30, lambda: self.topic + " 1/hz: " + str(1/self.hz) + " seconds")
                self.log(30, lambda: self.topic + " hz: " + str(self.hz) + "hz")


        self.last_read_ts = now.timestamp()
        self.pub.send_multipart(ZmqCodec.encode(self.topic, [now, new_data_np]))