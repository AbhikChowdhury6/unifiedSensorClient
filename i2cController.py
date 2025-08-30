import board
import busio
import time
from datetime import datetime

import importlib.util
import os
import sys

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
class_loc = repoPath + "unifiedSensorClient/sensorClasses/i2c/"

#import the config
from config import i2c_controller_config

def load_class_and_instantiate(filepath, class_name, *args, **kwargs):
    module_name = os.path.splitext(os.path.basename(filepath))[0]
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    tcls = getattr(module, class_name)
    instance = tcls(*args, **kwargs)
    return instance

def I2C_BUS():
    # init a bus using smbus2
    I2C_BUS = busio.I2C(board.SCL, board.SDA, frequency=100000) 
    # compile a list of all of the devices

    # loop through the devices and instantiate them

    # loop through the devices and collect the sensors