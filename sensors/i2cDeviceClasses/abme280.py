from adafruit_bme280 import basic as adafruit_bme280
import sys
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from sensors.sensor import Sensor
import logging
import numpy as np

class aBME280:
    def __init__(self, 
                    bus_location = "i2c-1-0x76",
                    device_name = "bosch-bme280",
                    debug_lvl = 30,

                    device_config = {
                        "bus": None, # will be set by i2cController,
                        "address": 0x76, # default address for bme280
                        "log_queue": None, # will be set by i2cController,
                    },
                    sensors_config = [
                        {
                            "sensor_type": "air-temp",
                            "units": "celsius",
                            "data_type": "float",
                            "shape": "1x1",
                            "hz": 1,
                            "file_writer_config": {},
                        },
                        {
                            "sensor_type": "rel-hum",
                            "units": "percent",
                            "data_type": "float",
                            "shape": "1x1",
                            "hz": 1,
                            "file_writer_config": {},
                        },
                        {
                            "sensor_type": "air-pressure",
                            "units": "pascal",
                            "data_type": "float",
                            "shape": "1x1",
                            "hz": 1,
                            "file_writer_config": {},
                        }
                    ]):
        
        if device_config['log_queue'] is None:
            raise ValueError("log_queue is required")
        self.log_queue = device_config['log_queue']
        self.device_name = f"{bus_location}-{device_name}"
        self.l = logging.getLogger(self.device_name)
        self.l.setLevel(debug_lvl)
        self.l.info(self.device_name + " starting")
        self.bme280 = adafruit_bme280.Adafruit_BME280_I2C(device_config['bus'], address=device_config['address'])
        
        self.is_ready = lambda: True

        #wrap these so they return a 1x1 numpy array
        self.get_air_temperature = lambda: np.array([self.bme280.temperature])  
        self.get_relative_humidity = lambda: np.array([self.bme280.relative_humidity])
        self.get_barometric_pressure = lambda: np.array([self.bme280.pressure * 100])
        
        retrieve_datas = {'air-temp': self.get_air_temperature,
                            'rel-hum': self.get_relative_humidity,
                            'air-pressure': self.get_barometric_pressure}


        self.sensors = []
        for s in sensors_config: #add the device info to the sensor config
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

        