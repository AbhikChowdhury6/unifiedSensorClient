from datetime import datetime, timedelta
from adafruit_pm25.i2c import PM25_I2C

import sys
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from sensors.sensor import Sensor
import logging

class aPMSA003I:
    def __init__(self, 
                    bus_location = "i2c-1-0x12",
                    device_name = "pmsa003i",
                    debug_lvl = 30,

                    device_config = {
                        "bus": None, # will be set by i2cController,
                        "address": 0x12, # default address for pmsa003i
                        "log_queue": None, # will be set by i2cController,
                    },
                    sensors_config = [
                        {
                            "sensor_type": "air-particulate-pm1",
                            "units": "ugDmE3",
                            "data_type": "int",
                            "shape": "1x1",
                            "hz": 1,
                            "file_writer_config": {},
                        },
                        {
                            "sensor_type": "air-particulate-pm2P5",
                            "units": "ugDmE3",
                            "data_type": "int",
                            "shape": "1x1",
                            "hz": 1,
                            "file_writer_config": {},
                        },
                        {
                            "sensor_type": "air-particulate-pm10",
                            "units": "ugDmE3",
                            "data_type": "int",
                            "shape": "1x1",
                            "hz": 1,
                            "file_writer_config": {},
                        },
                        {
                            "sensor_type": "air-particulate-particle-count",
                            "units": "greaterthan0p3umD0P1l",
                            "data_type": "int",
                            "shape": "1x1",
                            "hz": 1,
                            "file_writer_config": {},
                        }
                    ]):
        if device_config['log_queue'] is None:
            raise ValueError("log_queue is required")
        self.log_queue = device_config['log_queue']
        self.device_name = f"{bus_location}_{device_name}"
        self.l = logging.getLogger(self.device_name)
        self.l.setLevel(debug_lvl)
        self.l.info(self.device_name + " starting")
        self.pm25 = PM25_I2C(device_config['bus'], None)
        self.is_ready = lambda: True
        
        #this is to reduce updates to 1hz
        self.fresh_till = datetime.fromtimestamp(0)
        self.aqdata = None
        def get_aqdata_field(s):
            # if data expired refresh
            now = datetime.now()
            if now <= self.fresh_till:
                return self.aqdata[s]
            
            try:
                self.aqdata = self.pm25.read()
                self.fresh_till = now + timedelta(seconds=1)
            except RuntimeError:
                print("Unable to read from sensor")
                return None
            return self.aqdata[s]

        self.get_pm1 = lambda: get_aqdata_field("pm10 env")
        self.get_pm2P5 = lambda: get_aqdata_field("pm25 env")
        self.get_pm10 = lambda: get_aqdata_field("pm100 env")
        self.get_particle_count = lambda: get_aqdata_field("particles 03um")
        
        retrieve_datas = {'air-particulate-pm1': self.get_pm1,
                            'air-particulate-pm2P5': self.get_pm2P5,
                            'air-particulate-pm10': self.get_pm10,
                            'air-particulate-particle-count': self.get_particle_count}

        self.sensors = []
        for s in sensors_config:
            if "file_writer_config" in s:
                s["file_writer_config"]["log_queue"] = device_config["log_queue"]
            s["log_queue"] = device_config["log_queue"]
            s["bus_location"] = bus_location
            s["device_name"] = device_name
            if "debug_lvl" not in s:
                s["debug_lvl"] = debug_lvl
            s["retrieve_data"] = retrieve_datas[s['sensor_type']]
            s["is_ready"] = self.is_ready
            self.sensors.append(Sensor(**s))
