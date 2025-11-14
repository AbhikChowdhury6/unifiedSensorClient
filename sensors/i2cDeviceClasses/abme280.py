from adafruit_bme280 import basic as adafruit_bme280
import sys
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from sensors.sensor import Sensor
import logging
import numpy as np
# open the config
from config import i2c_controller_process_config
config = i2c_controller_process_config
# find the config for this device
device_config = [d for d in i2c_controller_process_config['devices'] if d['module_name'] == 'abme280'][0]

class aBME280():
    def __init__(self, 
                    platform_uuid,
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
                        },
                        {
                            "sensor_type": "barometric-pressure",
                            "units": "pascal",
                            "data_type": "float",
                            "shape": "1x1",
                            "hz": 1,
                            "file_writer_config": {},
                        }
                    ]):
        
        self.device_name = f"{platform_uuid}_{bus_location}_{device_name}"
        self.l = logging.getLogger(self.device_name)
        self.l.setLevel(debug_lvl)
        self.l.info(self.device_name + " starting")
        self.bme280 = adafruit_bme280.Adafruit_BME280_I2C(device_config['bus'], address=device_config['address'])
        
        self.is_ready = lambda: True

        #wrap these so they return a 1x1 numpy array
        self.get_air_temperature = lambda: np.array([self.bme280.temperature])  
        self.get_relative_humidity = lambda: np.array([self.bme280.relative_humidity])
        self.get_barometric_pressure = lambda: np.array([self.bme280.pressure * 100])
        
        retrieve_datas = {'air-temperature': self.get_air_temperature,
                            'relative-humidity': self.get_relative_humidity,
                            'barometric-pressure': self.get_barometric_pressure}


        self.sensors = []
        for s in sensors_config: #add the device info to the sensor config
            if "file_writer_config" in s:
                s["file_writer_config"]["log_queue"] = device_config["log_queue"]
            s["platform_uuid"] = platform_uuid
            s["bus_location"] = bus_location
            s["device_name"] = device_name
            if "debug_lvl" not in s:
                s["debug_lvl"] = debug_lvl
            s["retrieve_data"] = retrieve_datas[s['sensor_type']]
            s["is_ready"] = self.is_ready
            self.sensors.append(Sensor(**s))

        