from adafruit_bme280 import basic as adafruit_bme280
import sys
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from sensor import Sensor
import logging

# open the config
from config import i2c_controller_process_config
config = i2c_controller_process_config
# find the config for this device
device_config = [d for d in i2c_controller_process_config['devices'] if d['module_name'] == 'abme280'][0]

class aBME280:
    def __init__(self, bus):
        self.l = logging.getLogger(config["short_name"] + "." + device_config['model'])
        self.l.setLevel(device_config['debug_lvl'])
        self.l.info(config["short_name"] + " starting a " + device_config['model'] + "!")
        self.bme280 = adafruit_bme280.Adafruit_BME280_I2C(bus, address=device_config['address'])
        
        self.is_ready = lambda: True

        self.get_temp_c = lambda: self.bme280.temperature
        self.get_relative_humidity = lambda: self.bme280.relative_humidity
        self.get_pressure_pa = lambda: self.bme280.pressure * 100
        
        retrieve_datas = {'air-temprature-celcius': self.get_temp_c,
                            'relative-humidity-percent': self.get_relative_humidity,
                            'barometric-pressure-pa': self.get_pressure_pa}


        self.sensors = []
        for s in device_config['sensors']:
            sen = Sensor(s, retrieve_datas[s['sensor_type']], self.is_ready)
            self.sensors.append(sen)

        