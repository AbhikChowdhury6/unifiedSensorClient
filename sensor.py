from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import time
import zmq
import numpy as np

import sys
from icecream import ic

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec



def secs_since_midnight(dt):
    return (dt - dt.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()

class Sensor:
    def __init__(self, config, retrieve_data, is_ready):
        print('starting sensor!')
        sys.stdout.flush()
        self.hz = config['update_hz']
        self.delay_micros = int(1_000_000/self.hz)
        self.rounding_bits = config['rounding_bits']
        self.trillionths = 1_000_000_000_000/(2**self.rounding_bits)

        self.retrive_after = datetime.fromtimestamp(0, tz=timezone.utc)

        self.retrieve_data = retrieve_data
        self.topic = config['topic']
        self.endpoint = config['endpoint']
        self.ctx = zmq.Context()
        self.pub = self.ctx.socket(zmq.PUB)
        self.pub.bind(self.endpoint)
        time.sleep(.25)

        self.is_ready = is_ready
        while not self.is_ready():
            print("Waiting for data...")
            time.sleep(self.delay_micros/1_000_000)
        _ = self.retrieve_data() # a warmup reading
    
    def _round_data(self, new_data):
        rounded_data = int(new_data)
        this_trillionths = int((new_data%1) * 1_000_000_000_000)
        floord =  (this_trillionths // self.trillionths)  *  self.trillionths
        error =  this_trillionths - floord
        
        if error >= self.trillionths/2:
            rounded_data += (floord + self.trillionths)/1_000_000_000_000
        else:
            rounded_data += floord/1_000_000_000_000
        return rounded_data

    def read_data(self):
        # i'd like it to automatically wait till the rounded hz seconds
        # up to 128 seconds
        # calc the offset seconds from the start of the day

        #check if it's the right time
        now = datetime.now().astimezone(ZoneInfo("UTC"))

        # skip till the rounded hz seconds 
        if self.hz < 1 and int(secs_since_midnight(now)) % int(self.delay_micros/1_000_000) != 0:
            return

        if now >= self.retrive_after:
            #wait till the next timestep
            dm = self.delay_micros - (now.microsecond % self.delay_micros)
            self.retrive_after = now + timedelta(microseconds=dm)

            if not self.is_ready():
                return
            
            #round ts
            if self.hz <= 1:
                now = now.replace(microsecond=0)
            else:
                rounded_down_micros = (now.microsecond//self.delay_micros) * self.delay_micros
                now = now.replace(microsecond=int(rounded_down_micros))

            new_data = self.retrieve_data()

            if new_data is None:
                return
            
            if self.rounding_bits == 0:
                #make a tensor out of the data I think
                self.pub.send_multipart(ZmqCodec.encode(self.topic, new_data))
                return

            #ic(new_data)
            #sys.stdout.flush()
            #we need 5 didgits to prefecly define afloat 5 and same for 6 and 7 and 8
            # honestly let's just handle up to 9 bits of rounding for now and that should even cover our quats ok
            npd = np.array(new_data)
            npd = np.vectorize(self._round_data)(npd)
            # change this to send via zmq 
            self.pub.send_multipart(ZmqCodec.encode(self.topic, npd))
            return
        
