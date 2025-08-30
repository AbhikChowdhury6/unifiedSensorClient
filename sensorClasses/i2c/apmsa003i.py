from datetime import datetime, timedelta
from adafruit_pm25.i2c import PM25_I2C
import sys
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "airQualPi/")
from sensor import Sensor


class aPMSA003I:
    def __init__(self, bus, descriptor, debug_lvl):
        print('starting a ' + descriptor['deviceName'] + '!')
        self.pm25 = PM25_I2C(bus, None)
        
        self.is_ready = lambda: True
        
        self.fresh_till = datetime.fromtimestamp(0)
        self.aqdata = None
        def get_aqdata_field(s):
            # if data expired refresh
            now = datetime.now()
            if now <= self.fresh_till:
                return self.aqdata[s]
            
            try:
                self.aqdata = self.pm25.read()
                self.fresh_till = now + timedelta(seconds=1)
            except RuntimeError:
                print("Unable to read from sensor")
                return None
            return self.aqdata[s]

        self.get_envpm1um = lambda: get_aqdata_field("pm10 env")
        self.get_envpm2p5um = lambda: get_aqdata_field("pm25 env")
        self.get_envpm10um = lambda: get_aqdata_field("pm100 env")
        self.get_gtpm0p3um = lambda: get_aqdata_field("particles 03um")
        
        retrieve_datas = {'envpm1um-ugperm3': self.get_envpm1um,
                            'envpm2.5um-ugperm3': self.get_envpm2p5um,
                            'envpm10um-ugperm3': self.get_envpm10um,
                            'gtpm0.3um-per.1l': self.get_gtpm0p3um}

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
