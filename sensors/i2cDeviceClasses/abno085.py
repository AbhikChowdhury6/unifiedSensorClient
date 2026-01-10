from adafruit_bno08x.i2c import BNO08X_I2C
from adafruit_bno08x import (
    BNO_REPORT_ACCELEROMETER,
    BNO_REPORT_GYROSCOPE,
    BNO_REPORT_MAGNETOMETER,
    BNO_REPORT_GAME_ROTATION_VECTOR,
)
import logging
import sys
import numpy as np
import time

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
                        "read_timeout_s": 0.05,
                        "max_consecutive_errors": 5,
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
        self.device_name = f"{bus_location}-{device_name}"
        self.l = logging.getLogger(self.device_name)
        self.l.setLevel(debug_lvl)
        self.l.info(self.device_name + " starting")

        #this is different
        self._bus = device_config['bus']
        self._address = device_config['address']
        self._read_timeout_s = device_config.get("read_timeout_s", 0.05)
        self._max_consecutive_errors = device_config.get("max_consecutive_errors", 5)
        self._consecutive_errors = 0
        self.bno085 = BNO08X_I2C(self._bus, address=self._address)
        self.bno085.enable_feature(BNO_REPORT_ACCELEROMETER) #add interval micros if desired
        self.bno085.enable_feature(BNO_REPORT_GYROSCOPE)
        self.bno085.enable_feature(BNO_REPORT_MAGNETOMETER)
        self.bno085.enable_feature(BNO_REPORT_GAME_ROTATION_VECTOR)
        
        self.is_ready = lambda: True
        
        def _reinit():
            try:
                self.l.warning(self.device_name + " attempting BNO08x re-initialization after error")
                self.bno085 = BNO08X_I2C(self._bus, address=self._address)
                self.bno085.enable_feature(BNO_REPORT_ACCELEROMETER)
                self.bno085.enable_feature(BNO_REPORT_GYROSCOPE)
                self.bno085.enable_feature(BNO_REPORT_MAGNETOMETER)
                self.bno085.enable_feature(BNO_REPORT_GAME_ROTATION_VECTOR)
                self._consecutive_errors = 0
                return True
            except Exception:
                self.l.exception(self.device_name + " BNO08x re-initialization failed")
                return False
        self._reinit = _reinit

        def _safe_read(name, getter):
            start = time.monotonic()
            try:
                value = getter()
            except Exception:
                self._consecutive_errors += 1
                self.l.exception(self.device_name + " " + name + " read raised")
                # Let Sensor handle recovery via on_error
                raise
            duration = time.monotonic() - start
            if duration > self._read_timeout_s:
                self._consecutive_errors += 1
                self.l.warning(self.device_name + f" {name} read timeout {duration:.4f}s > {self._read_timeout_s:.4f}s")
                # Treat timeout as failure; raise to trigger recovery
                raise TimeoutError(f"{name} read exceeded timeout")
            else:
                self._consecutive_errors = 0
            return value

        self.get_accel = lambda: np.array([_safe_read("acceleration", lambda: self.bno085.acceleration)])
        self.get_gyro = lambda: np.array([_safe_read("gyroscope", lambda: self.bno085.gyro)])
        self.get_magnet = lambda: np.array([_safe_read("magnetometer", lambda: self.bno085.magnetic)])
        self.get_game_quaternion = lambda: np.array([_safe_read("game-rotation", lambda: self.bno085.game_quaternion)])

        retrieve_datas = {'acceleration': self.get_accel,
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
