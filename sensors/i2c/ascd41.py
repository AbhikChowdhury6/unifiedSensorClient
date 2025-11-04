from datetime import datetime, timedelta
import adafruit_scd4x
import sys
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from sensors.i2c.i2cSensor import Sensor

from config import i2c_controller_process_config
device_config = [d for d in i2c_controller_process_config['devices'] if d['module_name'] == 'ascd41'][0]

class aSCD41:
    def __init__(self, bus):
        print('starting a ' + device_config['model'] + '!')
        self.scd4x = adafruit_scd4x.SCD4X(bus)
        self.scd4x.start_periodic_measurement()

        self.is_ready = self.scd4x.data_ready
        
        self.get_co2 = lambda: self.scd4x.CO2
        self.get_temp = lambda: self.scd4x.temperature
        self.get_humidity = lambda: self.scd4x.relative_humidity
        
        retrieve_datas = {'air-temprature-celcius': self.get_temp,
                            'relative-humidity-percent': self.get_humidity,
                            'carbon-dioxide-ppm': self.get_co2}


        sensor_descriptors = device_config['sensors']
        self.sensors = []
        for s in sensor_descriptors:
            sen = Sensor(sensor_descriptors[s], retrieve_datas[s['sensor_type']], self.is_ready)
            self.sensors.append(sen)
