import adafruit_bme680

import sys

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from sensor import Sensor

from config import i2c_controller_process_config
device_config = [d for d in i2c_controller_process_config['devices'] if d['module_name'] == 'abme680'][0]

class aBME680:
    def __init__(self, bus):
        print('starting a ' + device_config['model'] + '!')
        self.bme680 = adafruit_bme680.Adafruit_BME680_I2C(bus, debug=False)

        self.is_ready = lambda: True

        self.get_temp_c = lambda: self.bme680.temperature
        self.get_relative_humidity = lambda: self.bme680.relative_humidity
        self.get_pressure_pa = lambda: self.bme680.pressure * 100
        self.get_voc_ohm = lambda: self.bme680.gas

        retrieve_datas = {'air-temprature-celcius': self.get_temp_c,
                          'relative-humidity-percent': self.get_relative_humidity,
                          'barometric-pressure-pa': self.get_pressure_pa,
                          'volatile-organic-compounds-ohm': self.get_voc_ohm,}

        sensor_descriptors = device_config['sensors']
        self.sensors = []
        for s in sensor_descriptors:
            sen = Sensor(sensor_descriptors[s], retrieve_datas[s['sensor_type']],
                         self.is_ready)
            self.sensors.append(sen)

