from adafruit_bno08x.i2c import BNO08X_I2C
from adafruit_bno08x import (
    BNO_REPORT_ACCELEROMETER,
    BNO_REPORT_GYROSCOPE,
    BNO_REPORT_MAGNETOMETER,
    BNO_REPORT_GAME_ROTATION_VECTOR,
)
import logging
import sys


repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from sensors.sensor import Sensor

class aBNO085:
    def __init__(self, 
                    bus_location = "i2c-0-0x4b",
                    device_name = "bosch-bno085",
                    debug_lvl = 30,

                    device_config = {
                        "bus": None, # will be set by i2cController,
                        "address": 0x4b, # default address for bno085
                        "log_queue": None, # will be set by i2cController,
                    },
                    sensors_config = [
                        {
                            "sensor_type": "acceleration",
                            "units": "mDsE2",
                            "data_type": "float",
                            "shape": "1x3",
                            "hz": 1,
                            "file_writer_config": {},
                        },
                        {
                            "sensor_type": "gyroscope",
                            "units": "radDs",
                            "data_type": "float",
                            "shape": "1x3",
                            "hz": 1,
                            "file_writer_config": {},
                        },
                        {
                            "sensor_type": "magnetometer",
                            "units": "gauss",
                            "data_type": "float",
                            "shape": "1x3",
                            "hz": 1,
                            "file_writer_config": {},
                        },
                        {
                            "sensor_type": "game-rotation",
                            "units": "quaternion",
                            "data_type": "float",
                            "shape": "1x4",
                            "hz": 1,
                            "file_writer_config": {},
                        }
                    ]):
        if device_config['log_queue'] is None:
            raise ValueError("log_queue is required")
        self.log_queue = device_config['log_queue']
        self.device_name = f"{bus_location}_{device_name}"
        self.l = logging.getLogger(self.device_name)
        self.l.setLevel(debug_lvl)
        self.l.info(self.device_name + " starting")

        #this is different
        self.bno085 = BNO08X_I2C(device_config['bus'], address=device_config['address'])
        self.bno085.enable_feature(BNO_REPORT_ACCELEROMETER) #add interval micros if desired
        self.bno085.enable_feature(BNO_REPORT_GYROSCOPE)
        self.bno085.enable_feature(BNO_REPORT_MAGNETOMETER)
        self.bno085.enable_feature(BNO_REPORT_GAME_ROTATION_VECTOR)
        
        self.is_ready = lambda: True

        self.get_accel = lambda: self.bno085.acceleration
        self.get_gyro = lambda: self.bno085.gyro
        self.get_magnet = lambda: self.bno085.magnetic
        self.get_game_quaternion = lambda: self.bno085.game_quaternion

        retrieve_datas = {'accelation': self.get_accel,
                          'gyroscope': self.get_gyro,
                          'magnetometer': self.get_magnet,
                          'game-rotation': self.get_game_quaternion}
        
        #this is the same
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
