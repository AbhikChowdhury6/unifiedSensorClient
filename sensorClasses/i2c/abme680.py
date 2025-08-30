import adafruit_bme680

import sys

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "airQualPi/")
from sensor import Sensor


class aBME680:
    def __init__(self, bus, descriptor, debug_lvl):
        print('starting a ' + descriptor['deviceName'] + '!')
        self.bme680 = adafruit_bme680.Adafruit_BME680_I2C(bus, debug=False)

        self.is_ready = lambda: True

        self.get_temp_c = lambda: self.bme680.temperature
        self.get_relative_humidity = lambda: self.bme680.relative_humidity
        self.get_pressure_pa = lambda: self.bme680.pressure * 100
        self.get_voc_ohm = lambda: self.bme680.gas

        retrieve_datas = {'temp-c': self.get_temp_c,
                          'relativeHumidity': self.get_relative_humidity,
                          'pressure-pa': self.get_pressure_pa,
                          'voc-ohm': self.get_voc_ohm,}

        sensor_descriptors = descriptor['sensors']
        self.sensors = []
        for s in sensor_descriptors:
            dd = [descriptor['responsiblePartyName'],
                  descriptor['instanceName'],
                  descriptor['manufacturer'],
                  descriptor['deviceName'],
                  s,
                  'internal']
            sen = Sensor(sensor_descriptors[s], retrieve_datas[s],
                         self.is_ready, dd, debug_lvl)
            self.sensors.append(sen)

