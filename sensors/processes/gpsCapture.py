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

    def _init_gps(uart_obj):
        gps = adafruit_gps.GPS(uart_obj, debug=False)  # Use UART/pyserial
        gps.send_command(b"PMTK386,0")          # no static nav
        gps.send_command(b"PMTK313,1")          # SBAS on
        gps.send_command(b"PMTK301,2")          # WAAS
        gps.send_command(b"PMTK319,1")          # integrity mode (optional)
        #PMTK314 types of messages: GGL,RMC,VTG,GGA,GSA,GSV,...,ZDA,PMTKCHN
        #the number is every how many number of fixes to send the message
        gps.send_command(b"PMTK314,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")  # RMC
        #https://receiverhelp.trimble.com/alloy-gnss/en-us/NMEA-0183messages_MessageOverview.html
        
        #from RMC
        #UTC time (hhmmss.ss), status: A = valid, V = void
        #latitude (ddmm.mmmmm), N/S
        #longitude (dddmm.mmmm), E/W
        #speed over ground (knots), course over ground (degrees)
        #date (ddmmyy),
        #magnetic variation (degrees), E/W, mode - often skipped
        
        #from GGA
        #UTC time (hhmmss.ss), status: A = valid, V = void
        #latitude (ddmm.mmmmm), N/S
        #longitude (dddmm.mmmm), E/W
        #fix type: 0 = invalid, 1 = GPS, 2 = DGPS, 3 = PPS, 4 = RTK, 5 = RTK Float, 6 = EST, 7 = MAN, 8 = SIM
        #satellites used (00-12), HDOP,
        #MSL altitude, altiude units (M = meters, F = feet), geoid height, geoid height units,
        #Age of differential GPS data (seconds), Differential station ID (0000-1023) - often skipped
        #check sum

        #reminder ellipsoid altitude = msl altitude + geoid height

        #from VTG
        #course over ground (degrees), True track indicator (T), Magnetic track indicator (M),
        #Speed over ground (knots), Speed unit (N = knots, K = km/h), Mode indicator (A = autonomous, D = differential, E = estimated, N = not valid, S = simulation)


        #from GSA
        gps.send_command(b"PMTK220,250")        # 4hz (SBAS OK up to 5Hz for PA1616S)
        return gps

    gps = _init_gps(uart)

    
    is_ready = lambda: True
    # handle None values before a fix; use NaN so warmup doesn't crash
    def to_float_or_nan(v):
        if v is None:
            l.trace("to_float_or_nan: v is None: " + str(v))
            return np.nan
        l.trace("float32: " + str(np.float32(v)))
        l.trace("float64: " + str(np.float64(v)))
        return np.float64(v)


    def ellipsoid_alt_km():
        msl_alt = gps.altitude_m
        if msl_alt is None:
            return np.nan
        geoid_alt = gps.height_geoid
        if geoid_alt is None:
            return np.nan
        ellipsoid_alt = msl_alt + geoid_alt
        return np.float64(ellipsoid_alt / 1000.0)

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
    consecutive_parse_errors = 0
    reset_threshold = int(config.get("parse_error_reset_threshold", 5))
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
        # Robust GPS update with checksum-error handling and resync
        try:
            gps.update()
            consecutive_parse_errors = 0
        except ValueError as e:
            # Bad checksum or malformed sentence (e.g., '?D')
            l.warning("gps parse error on NMEA sentence; resetting input buffer")
            try:
                uart.reset_input_buffer()
            except Exception:
                l.exception("gps failed to reset input buffer")
            consecutive_parse_errors += 1
            if consecutive_parse_errors >= reset_threshold:
                l.warning("gps consecutive parse errors exceeded threshold; reopening serial and reinitializing GPS")
                try:
                    uart.close()
                except Exception:
                    pass
                try:
                    uart = serial.Serial(port, baudrate=baudrate, timeout=timeout)
                    gps = _init_gps(uart)
                    consecutive_parse_errors = 0
                except Exception:
                    l.exception("gps failed to reinitialize after parse errors")
            # Skip this cycle
            micros_to_delay = delay_micros - (datetime.now().microsecond % delay_micros)
            time.sleep(micros_to_delay/1_000_000)
            continue
        except Exception:
            l.exception("gps unexpected exception during update")
            micros_to_delay = delay_micros - (datetime.now().microsecond % delay_micros)
            time.sleep(micros_to_delay/1_000_000)
            continue
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