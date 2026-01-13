import sys
import zmq
import time
from datetime import datetime
import queue
import logging
import board
import busio
import numpy as np
import adafruit_gps
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from platformUtils.zmq_codec import ZmqCodec
from config import zmq_control_endpoint
from platformUtils.logUtils import worker_configurer, set_process_title
from sensors.sensor import Sensor

import serial



def gps_capture(log_queue: queue.Queue, config: dict):
    l = logging.getLogger(config["short_name"])
    set_process_title(config["short_name"])
    worker_configurer(log_queue, config["debug_lvl"])
    l.info(config["short_name"] + " process starting")


    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    print("gps capture connected to control topic")
    sys.stdout.flush()

    # use configured serial parameters
    port = f"/dev/{config.get('port', 'serial0')}"
    baudrate = int(config.get("baudrate", 9600))
    timeout = float(config.get("timeout", 10))
    uart = serial.Serial(port, baudrate=baudrate, timeout=timeout)

    gps = adafruit_gps.GPS(uart, debug=False)  # Use UART/pyserial

    # Enable RMC + VTG + GGA + GSA (GSA provides PDOP/HDOP/VDOP)
    gps.send_command(b"PMTK314,0,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
    # Turn on just minimum info (RMC only, location):
    # gps.send_command(b'PMTK314,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0')
    # Turn off everything:
    # gps.send_command(b'PMTK314,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0')
    # Turn on everything (not all of it is parsed!)
    # gps.send_command(b'PMTK314,1,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0')


    gps.send_command(b'PMTK220,500') #set update rate to 500ms

    
    is_ready = lambda: True
    # handle None values before a fix; use NaN so warmup doesn't crash
    def to_float_or_nan(v):
        if v is None:
            l.trace("to_float_or_nan: v is None: " + str(v))
            return np.nan
        return float(v)


    def ellipsoid_alt_km():
        msl_alt = gps.altitude_m
        if msl_alt is None:
            return np.nan
        geoid_alt = gps.height_geoid
        if geoid_alt is None:
            return np.nan
        ellipsoid_alt = msl_alt + geoid_alt
        return ellipsoid_alt / 1000.0

    def values_or_none(vals):
        if np.any(np.isnan(np.array(vals, dtype=float))):
            return None
        return vals


    def get_3dFix():
        vals = [
            to_float_or_nan(gps.latitude),
            to_float_or_nan(gps.longitude),
            to_float_or_nan(ellipsoid_alt_km())
        ]
        r = values_or_none(vals)
        if r is None:
            return None
        return np.array([r])

    def get_speed():
        vals = [
            to_float_or_nan(gps.speed_kmh)
        ]
        r = values_or_none(vals)
        if r is None:
            l.trace("get_speed: r is None")
            return None
        return np.array([r])
    
    def get_dop():
        vals = [
            to_float_or_nan(gps.hdop), 
            to_float_or_nan(gps.pdop), 
            to_float_or_nan(gps.vdop)
        ]
        r = values_or_none(vals)
        if r is None:
            l.trace("get_dop: r is None")
            return None
        return np.array([r])


    retrieve_datas = {'3d-fix': get_3dFix,
                      'speed': get_speed,
                      'dop': get_dop}
    
    sensors = []
    for sensor in config["sensors"]:
        if "file_writer_config" in sensor:
            sensor["file_writer_config"]["log_queue"] = log_queue
        if "debug_lvl" not in sensor:
            sensor["debug_lvl"] = config["debug_lvl"]
        sensor["log_queue"] = log_queue
        sensor["is_ready"] = is_ready
        sensor["retrieve_data"] = retrieve_datas[sensor["sensor_type"]]
        sensor["bus_location"] = config["bus_location"]
        sensor["device_name"] = config["device_name"]
        sensors.append(Sensor(**sensor))

    

    delay_micros = 1_000_000/config["hz"]
    time.sleep(1 - datetime.now().microsecond/1_000_000)
    while True:
        # non-blocking control receive; ignore when no message
        try:
            parts = sub.recv_multipart(flags=zmq.NOBLOCK)
            topic, obj = ZmqCodec.decode(parts)
            if topic == "control":
                if obj[0] == "exit_all" or (obj[0] == "exit" and obj[-1] == "gps"):
                    print("gps capture exiting")
                    sys.stdout.flush()
                    break
        except zmq.Again:
            pass
        
        gps.update()
        if not gps.has_fix:
            #log gps waiting for fix
            l.debug("gps waiting for fix")
            #time.sleep(0.25)
        
        else:
            for sensor in sensors:
                sensor.read_data()
        
        micros_to_delay = delay_micros - (datetime.now().microsecond % delay_micros)
        time.sleep(micros_to_delay/1_000_000)
    
    l.info(config["short_name"] + " process exiting")