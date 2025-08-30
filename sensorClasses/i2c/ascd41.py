from datetime import datetime, timedelta
import adafruit_scd4x
import sys
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "airQualPi/")
from sensor import Sensor


class aSCD41:
    def __init__(self, bus, descriptor, debug_lvl):
        print('starting a ' + descriptor['deviceName'] + '!')
        self.scd4x = adafruit_scd4x.SCD4X(bus)
        self.scd4x.start_periodic_measurement()

        #how to handle this state better?
        #id like it to stay true for the second after it turns true
        self.ready_till = datetime.fromtimestamp(0)
        def ready():
            if self.scd4x.data_ready:
                self.ready_till = datetime.now() + timedelta(seconds=1)
            return datetime.now() < self.ready_till

        self.is_ready = ready
        
        self.get_co2 = lambda: self.scd4x.CO2
        self.get_temp = lambda: self.scd4x.temperature
        self.get_humidity = lambda: self.scd4x.relative_humidity
        
        retrieve_datas = {'temp-c': self.get_temp,
                            'relativeHumidity': self.get_humidity,
                            'co2-ppm': self.get_co2}


        sensor_descriptors = descriptor['sensors']
        self.sensors = []
        for s in sensor_descriptors:
            dd = [descriptor['responsiblePartyName'],
                descriptor['instanceName'],
                descriptor['manufacturer'],
                descriptor['deviceName'],
                s,
                'internal']
            sen = Sensor(sensor_descriptors[s], retrieve_datas[s], self.is_ready, dd, debug_lvl)
            self.sensors.append(sen)
