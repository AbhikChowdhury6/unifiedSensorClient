from adafruit_bme280 import basic as adafruit_bme280
import sys
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "airQualPi/")
from sensor import Sensor

# open the config
from config import i2c_controller_config

# find the config for this device
device_config = [d for d in i2c_controller_config['devices'] if d['class'] == 'abme280'][0]

class aBME280:
    def __init__(self, bus):
        print('starting a ' + device_config['model'] + '!')
        self.bme280 = adafruit_bme280.Adafruit_BME280_I2C(bus, address=device_config['address'])
        
        self.is_ready = lambda: True

        self.get_temp_c = lambda: self.bme280.temperature
        self.get_relative_humidity = lambda: self.bme280.relative_humidity
        self.get_pressure_pa = lambda: self.bme280.pressure * 100
        
        retrieve_datas = {'air-temprature': self.get_temp_c,
                            'relative-humidity': self.get_relative_humidity,
                            'barometric-pressure': self.get_pressure_pa}


        sensor_descriptors = device_config['sensors']
        self.sensors = []
        for s in sensor_descriptors:
            dd = [device_config['responsible_party'],
                s['name'],
                device_config['manufacturer'],
                device_config['model'],
                s,
                'internal']
            sen = Sensor(sensor_descriptors[s], retrieve_datas[s], self.is_ready, dd)
            self.sensors.append(sen)

        