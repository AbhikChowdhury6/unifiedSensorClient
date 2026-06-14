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
from platformUtils.zmq_codec import ZmqCodec
from adafruit_extended_bus import ExtendedI2C as I2C
import traceback
from platformUtils.utils import configure_process, should_exit

def load_class_and_instantiate(filepath, class_name, l, *args, **kwargs):
    module_name = os.path.splitext(os.path.basename(filepath))[0]
    l.debug("loading class " + class_name + " from " + filepath)
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    tcls = getattr(module, class_name)
    instance = tcls(*args, **kwargs)
    return instance

def i2c_controller(config_name):
    ctx = zmq.Context()
    l, sub, config = configure_process(ctx, config_name)
    l.info(config_name + " controller starting")

    # initialize I2C bus by bus number (e.g., /dev/i2c-1) using ExtendedI2C
    try:
        I2C_BUS = I2C(config['bus_number'])
        l.debug(f"{config_name} using /dev/i2c-{config['bus_number']}")
    except Exception as e:
        l.error(f"Failed to open /dev/i2c-{config['bus_number']}: {e}")
        raise
    # compile a list of all of the devices
    
    
    devices = []
    for device in config['devices']:
        devices.append(load_class_and_instantiate(
            config['device_class_loc'] + device['module_name'] + '.py',
            device['class_name'],
            l,
            **{
            "bus_location": device['bus_location'],
            "device_name": device['device_name'],
            "debug_lvl": device['debug_lvl'],
            "sensors_config": device['sensors_config'],
            "device_config": {
                "bus": I2C_BUS,
                "address": device['address'],
                },
            },
        ))
    # loop through the devices and collect the sensors
    sensors = []
    for device in devices:
        sensors.extend(device.sensors)

    max_hz = max(s.hz for s in sensors)
    l.info(config_name + " controller max hz: " + str(max_hz))
    # works perfectly up to 64 hz
    delay_micros = 1_000_000/max_hz

    # Start loop
    time.sleep(1 - datetime.now().microsecond/1_000_000)
    try:
        while True:
            #print(f"in loop time is {datetime.now()}")
            #sys.stdout.flush()
            for sensor in sensors:
                sensor.read_data()

            # check if there's any messages in the control signal topic
            try:
                parts = sub.recv_multipart(flags=zmq.NOBLOCK)
                topic, obj = ZmqCodec.decode(parts)
                l.debug(config_name + " controller control message: " + str(obj))
                if should_exit(topic, obj, config_name):
                    break
            except zmq.Again:
                # No message available
                pass
                    
            micros_to_delay = delay_micros - (datetime.now().microsecond % delay_micros)
            time.sleep(micros_to_delay/1_000_000)
    except Exception as e:
        # Log full traceback to logs and stderr immediately, then terminate this process
        l.exception(f"{config_name} controller encountered an unhandled exception and will exit")
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)
        
    l.info(config_name + " controller exiting")  

if __name__ == "__main__":
    config_name = sys.argv[1]
    i2c_controller(config_name)