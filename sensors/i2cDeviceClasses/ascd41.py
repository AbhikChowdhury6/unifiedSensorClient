from datetime import datetime, timedelta
import adafruit_scd4x
import sys
import logging
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from sensors.sensor import Sensor


class aSCD41:
    def __init__(self,  
                    bus_location = "i2c-1-0x62",
                    device_name = "sensirion-scd41",
                    debug_lvl = 30,

                    device_config = {
                        "bus": None, # will be set by i2cController,
                        "address": 0x62, # default address for scd41
                        "log_queue": None, # will be set by i2cController,
                    },
                    sensors_config = [
                        {
                            "sensor_type": "co2",
                            "units": "ppm",
                            "data_type": "int",
                            "shape": "1x1",
                            "hz": 1,
                            "file_writer_config": {},
                        },
                        {
                            "sensor_type": "air-temperature",
                            "units": "celsius",
                            "data_type": "float",
                            "shape": "1x1",
                            "hz": 1,
                            "file_writer_config": {},
                        },
                        {
                            "sensor_type": "relative-humidity",
                            "units": "percent",
                            "data_type": "float",
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
        self.scd4x = adafruit_scd4x.SCD4X(device_config['bus'], address=device_config['address'])
        self.scd4x.start_periodic_measurement()
        
        self.is_ready = lambda: self.scd4x.data_ready
        
        self.get_co2 = lambda: self.scd4x.CO2
        self.get_air_temperature = lambda: self.scd4x.temperature
        self.get_relative_humidity = lambda: self.scd4x.relative_humidity
        
        retrieve_datas = {'co2': self.get_co2,
                            'air-temperature': self.get_air_temperature,
                            'relative-humidity': self.get_relative_humidity}


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
            sen = Sensor(**s)
            self.sensors.append(sen)
