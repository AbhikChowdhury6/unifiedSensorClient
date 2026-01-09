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
                    bus_location = None,
                    device_name = None,
                    sensor_type = None,
                    units = None,
                    data_type = None,
                    shape = None,
                    hz = None,
                    grace_period_samples = 0,
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
        self.sensor_hz = hz
        self.message_hz = max(1, hz)
        self.sensor_delay_micros = int(1_000_000/self.sensor_hz)
        self.message_delay_micros = int(1_000_000/self.message_hz)
        #self.timestamp_rounding_bits = config['timestamp_rounding_bits']
        #self.trillionths = 1_000_000_000_000/(2**self.timestamp_rounding_bits)
        self.sensor_update_after = datetime.fromtimestamp(0, tz=timezone.utc)
        self.message_update_after = datetime.fromtimestamp(0, tz=timezone.utc)
        self.grace_period_samples = grace_period_samples
        self.curr_data = None


        #data descriptor
        self.bus_location = bus_location
        self.device_name = device_name # manufacturer-model-address
        self.sensor_type = sensor_type
        self.units = units # dash separated units if multiple
        self.data_type = data_type
        self.shape = shape # nxn
        print(
                     str(self.bus_location) + " " + 
                     str(self.device_name) + " " + 
                     str(self.sensor_type) + " " + 
                     str(self.units) + " " + 
                     str(self.data_type) + " " + 
                     str(self.shape) + " " + 
                     str(self.hz).replace(".", "P") + "hz")
        sys.stdout.flush()
        #self.float_rounding_precision = config['float_rounding_precision']

        #zmq
        self.topic = "_".join([ 
                                self.bus_location, 
                                self.device_name, 
                                self.sensor_type, 
                                self.units, 
                                self.data_type,
                                self.shape,
                                str(self.hz).replace(".", "P") + "hz"])

        #if topic was passed in 
        if "topic" in kwargs:
            if self.topic != kwargs["topic"]:
                self.l.error("topic mismatch: generated topic: " + self.topic + 
                " != passed in topic: " + kwargs["topic"])

        self.endpoint = f"ipc:///tmp/{self.topic}.sock"
        self.ctx = zmq.Context()
        self.pub = self.ctx.socket(zmq.PUB)
        self.pub.bind(self.endpoint)

        #logging setup
        self.l = logging.getLogger(self.topic)
        self.l.setLevel(debug_lvl)
        self.l.debug(self.topic + " connected to " + self.endpoint)
        self.l.debug(self.topic)
        self.l.debug(camera_topic)
        self.l.debug(self.endpoint)
        self.l.debug(camera_endpoint)


        #ready
        self.is_ready = is_ready
        while not self.is_ready():
            self.l.debug(self.topic + " waiting for data...")
            time.sleep(self.sensor_delay_micros/1_000_000)
        _ = self.retrieve_data() # a warmup reading
        time.sleep(.25)

        self.last_read_dt = None
        self.last_message_dt = None
        self.interp_seconds = (1/self.message_hz) * (self.grace_period_samples+1)
        self.messages_per_sensor_update = self.message_hz // self.sensor_hz
        self.messages_to_interp = self.messages_per_sensor_update * self.grace_period_samples
        self.curr_interped_messages = -1

        #calculate the estimated read time
        ts = datetime.now(timezone.utc)
        _ = self.retrieve_data()
        self.max_read_micros = (datetime.now(timezone.utc) - ts).total_seconds() * 1_000_000
        self.l.debug("estimated read time for " + self.topic + " is " + str(self.max_read_micros) + " microseconds")

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
        self.log(20, lambda: self.topic + " initialized")

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
        if not self.is_ready():
            return
        
        #check if it's the right time to read the data
        now = datetime.now(timezone.utc)
        rounded_down_micros = (now.microsecond//self.sensor_delay_micros) * self.sensor_delay_micros
        now = now.replace(microsecond=int(rounded_down_micros))
        
        #The highest frequency thing will be the message hz, so we can check that first
        if now < self.message_update_after:
            return
        
        #if it has been longer than the update hz, fill the messages (for higher hz sensors)
        if self.last_read_dt is not None and (now - self.last_read_dt).total_seconds() > 1/self.sensor_hz:
            messages_to_fill = min(int((now - self.last_read_dt).total_seconds() * self.message_hz) - 1, self.messages_to_interp)
            self.log(5, lambda: "messages to fill: " + str(messages_to_fill))
            if messages_to_fill > 0:
                self.log(5, lambda: "it has been " + str(now - self.last_read_dt) + " seconds since the last read")
                self.log(5, lambda: "we have a maximum of " + str(self.messages_to_interp) + " messages to interp")
                self.log(5, lambda: "we will be writing " + str(messages_to_fill) + " number of messages")
                
                for i in range(messages_to_fill):
                    dt = self.last_read_dt + timedelta(seconds=i/self.message_hz)
                    self.log(5, lambda: "filling message " + str(i) + " of " + str(messages_to_fill) + " at " + str(dt))
                    self.pub.send_multipart(ZmqCodec.encode(self.topic, [dt, self.curr_data]))
            


        #check if it's the right time to update the data
        if now >= self.sensor_update_after:            
            self.log(5, lambda: "updating data from " + self.topic)

            #ts = now.timestamp()
            self.curr_data = np.array(self.retrieve_data())
            if self.curr_data is None:
                return
            #self.log(5, lambda: "read time: " + str(now.timestamp() - ts) + " seconds")
            #self.max_read_micros = max(self.max_read_micros, (now.timestamp() - ts) * 1_000_000)
            #self.log(5, lambda: "max read time: " + str(self.max_read_micros) + " microseconds")

            
            self.sensor_update_after = now + timedelta(microseconds=self.sensor_delay_micros)
            self.log(5, lambda: "next sensor update after" + str(self.sensor_update_after))
            self.stop_sending_messages_after = now + timedelta(seconds=self.messages_to_interp/self.message_hz)

        
        #for lower hz sensors, we need to fill the messages
        #if it's not time to get new data but it is time to send the interpolate as well
        self.pub.send_multipart(ZmqCodec.encode(self.topic, [now, self.curr_data]))
        self.message_update_after = now + timedelta(microseconds=self.message_delay_micros)
        #we currently aren't supporting interpolation for lower hz sensors     

        
