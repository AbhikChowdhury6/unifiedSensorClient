import board
import busio
import time
from datetime import datetime

import importlib.util
import os
import sys
import zmq

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
class_loc = repoPath + "unifiedSensorClient/sensorClasses/i2c/"
from zmq_codec import ZmqCodec

#import the config
from config import i2c_controller_config, zmq_control_endpoint

def load_class_and_instantiate(filepath, class_name, *args, **kwargs):
    module_name = os.path.splitext(os.path.basename(filepath))[0]
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    tcls = getattr(module, class_name)
    instance = tcls(*args, **kwargs)
    return instance

def I2C_BUS():
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    
    # init a bus using smbus2
    I2C_BUS = busio.I2C(board.SCL, board.SDA, frequency=100000) 
    # compile a list of all of the devices
    devices = []
    for device in i2c_controller_config['devices']:
        devices.append(load_class_and_instantiate(
            class_loc + device['class'] + '.py',
            device['class'],
            I2C_BUS,
            device))


    # loop through the devices and collect the sensors
    sensors = []
    for device in devices:
        sensors.extend(device.sensors)

    max_hz = max(s.hz for s in sensors)
    # works perfectly up to 64 hz
    delay_micros = 1_000_000/max_hz

    # Start loop
    time.sleep(1 - datetime.now().microsecond/1_000_000)
    while True:
        for sensor in sensors:
            sensor.read_data()

        # check if there's any messages in the control signal topic
        try:
            parts = sub.recv_multipart(flags=zmq.NOBLOCK)
            topic, obj = ZmqCodec.decode(parts)
            print("i2c control message:", obj)
            if obj == "exit":
                print('i2c exiting')
                break
        except zmq.Again:
            # No message available
            pass
                
        micros_to_delay = delay_micros - (datetime.now().microsecond % delay_micros)
        time.sleep(micros_to_delay/1_000_000)
        
    print('i2c exiting')  