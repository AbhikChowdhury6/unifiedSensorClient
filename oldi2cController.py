import board
import busio
import time
from datetime import datetime, timedelta

# at the end of the day it'll spawn a process to convert the message thing to a df
#   it can spawn it at a random minute offset between 1 and 55
# the os will move all the df's at the end of the day + 1 hour

# the storage server will integrate the data into the dataset

import importlib.util
import os
import sys

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "airQualPi/")
class_loc = repoPath + "airQualPi/"

def load_class_and_instantiate(filepath, class_name, *args, **kwargs):
    module_name = os.path.splitext(os.path.basename(filepath))[0]
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    tcls = getattr(module, class_name)
    instance = tcls(*args, **kwargs)
    return instance


# this is a process to be spawned
def I2C_BUS(bus_descriptor, debug_lvl, exitSignal):
    print('in i2c!')
    sys.stdout.flush()

    # init a bus using smbus2
    I2C_BUS = busio.I2C(board.SCL, board.SDA, frequency=100000) 
    sensors = []
    devices = []
    for device in bus_descriptor:
        newDevice = load_class_and_instantiate(
            class_loc + device + '.py',
            bus_descriptor[device]['class_name'],
            I2C_BUS,
            bus_descriptor[device],
            debug_lvl
        )
        devices.append(newDevice)
        sensors += newDevice.sensors


    max_hz = max(s.hz for s in sensors)
    # works perfectly up to 64 hz
    delay_micros = 1_000_000/max_hz

    # Start loop
    time.sleep(1 - datetime.now().microsecond/1_000_000)
    while True:
        for sensor in sensors:
            sensor.read_data()

        # check if there's any messages in the control signal topic
        if any(not s.write_process.is_alive() for s in sensors) or exitSignal[0] == 1:
            print('sending write exit signals to i2c sensors')
            for s in sensors:
                print("_".join(s.dd), s.write_process.is_alive())
                s.write_exit_signal[0] = 1
            break
        
        micros_to_delay = delay_micros - (datetime.now().microsecond % delay_micros)
        time.sleep(micros_to_delay/1_000_000)
        
    print('i2c waiting 3 seconds for writers to exit')
    time.sleep(3)
    print('i2c exiting')  



