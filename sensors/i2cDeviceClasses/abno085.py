from adafruit_extended_bus import ExtendedI2C as I2C
from adafruit_bno08x.i2c import BNO08X_I2C

import sys

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from sensors.i2c.i2cSensor import Sensor

from config import i2c_controller_process_config
device_config = [d for d in i2c_controller_process_config['devices'] if d['module_name'] == 'abme680'][0]

class aBNO085:
    def __init__(self, bus):
        self.bno085 = BNO08X_I2C(I2C(bus))

        # we'll be getting raw and calibrated accel and gyro data

        #we'll also get the clabration data
        self.bno085.enable_feature(BNO08X_I2C.BNO_REPORT_ACCELEROMETER) #add inetrval micros
        self.bno085.enable_feature(BNO08X_I2C.BNO_REPORT_GYROSCOPE)
        self.bno085.enable_feature(BNO08X_I2C.BNO_REPORT_MAGNETOMETER)
        self.bno085.enable_feature(BNO08X_I2C.BNO_REPORT_GAME_ROTATION_VECTOR)

        self.is_ready = lambda: True

        self.get_accel = lambda: self.bno085.acceleration
        self.get_gyro = lambda: self.bno085.gyro
        self.get_magnet = lambda: self.bno085.magnetic
        self.get_game_quaternion = lambda: self.bno085.game_quaternion

        retrieve_datas = {'accelation-mDs2': self.get_accel,
                          'gyro-radDs2': self.get_gyro,
                          'magnet-gauss': self.get_magnet,
                          'game-rotation-quaternion': self.get_game_quaternion}
        
        sensor_descriptors = device_config['sensors']
