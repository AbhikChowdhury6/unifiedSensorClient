import adafruit_bme680
import sys

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from sensors.sensor import Sensor
import logging
import numpy as np

class aBME680:
    def __init__(self, 
                    bus_location = "i2c-1-0x77",
                    device_name = "bosch-bme680",
                    debug_lvl = 30,

                    device_config = {
                        "bus": None, # will be set by i2cController,
                        "address": 0x77, # default address for bme680
                        "log_queue": None, # will be set by i2cController,
                    },
                    sensors_config = [
                        {
                            "sensor_type": "barometric-pressure",
                            "units": "kpa",
                            "data_type": "float",
                            "shape": "1x1",
                            "hz": 16,
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
                            "sensor_type": "air-temperature",
                            "units": "celsius",
                            "data_type": "float",
                            "shape": "1x1",
                            "hz": 1,
                            "file_writer_config": {},
                        },
                        {
                            "sensor_type": "volatile-organic-compounds",
                            "units": "LNohm",
                            "data_type": "float",
                            "shape": "1x1",
                            "hz": 1,
                            "file_writer_config": {},
                        }
                    ]):
        if device_config['log_queue'] is None:
            raise ValueError("log_queue is required")
        self.log_queue = device_config['log_queue']
        self.logger_name = f"{bus_location}-{device_name}"
        self.l = logging.getLogger(self.logger_name)
        self.l.setLevel(debug_lvl)
        self.l.info(self.logger_name + " starting")



        self.bme680 = adafruit_bme680.Adafruit_BME680_I2C(device_config['bus'], address=device_config['address'], debug=False)

        self.is_ready = lambda: True

        self.get_temp_c = lambda: np.array([self.bme680.temperature])
        self.get_relative_humidity = lambda: np.array([self.bme680.relative_humidity])
        self.get_pressure_kpa = lambda: np.array([self.bme680.pressure / 10])
        self.get_voc_lnohm = lambda: np.array([np.log(self.bme680.gas)])

        retrieve_datas = {'air-temperature': self.get_temp_c,
                          'relative-humidity': self.get_relative_humidity,
                          'barometric-pressure': self.get_pressure_kpa,
                          'volatile-organic-compounds': self.get_voc_lnohm,}



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

