import sys
import zmq
import time

import board
import busio

import adafruit_gps
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec
from config import gps_capture_process_config, zmq_control_endpoint


import serial
uart = serial.Serial("/dev/ttyUSB0", baudrate=9600, timeout=10)

gps = adafruit_gps.GPS(uart, debug=False)  # Use UART/pyserial

# Turn on the basic GGA and RMC info (what you typically want)
gps.send_command(b"PMTK314,0,1,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
# Turn on the basic GGA and RMC info + VTG for speed in km/h
# gps.send_command(b"PMTK314,0,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
# Turn on just minimum info (RMC only, location):
# gps.send_command(b'PMTK314,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0')
# Turn off everything:
# gps.send_command(b'PMTK314,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0')
# Turn on everything (not all of it is parsed!)
# gps.send_command(b'PMTK314,1,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0')


gps.send_command(b'PMTK220,500') #set update rate to 500ms

config = gps_capture_process_config
def gps_capture():
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    print("gps capture connected to control topic")
    sys.stdout.flush()

    pub = ctx.socket(zmq.PUB)
    pub.bind(config["pub_endpoint"])
    print(f"gps capture publishing to {config['pub_topic']} at {config['pub_endpoint']}")
    sys.stdout.flush()

    while True:
        parts = sub.recv_multipart(flags=zmq.NOBLOCK)
        topic, obj = ZmqCodec.decode(parts)
        if topic == "control":
            if obj[0] == "exit_all" or (obj[0] == "exit" and obj[-1] == "gps"):
                print("gps capture exiting")
                sys.stdout.flush()
                break
        
        gps.update()
        if not gps.has_fix:
            #log gps waiting for fix
            continue
        
        #send 3d fix
        pub.send_multipart(ZmqCodec.encode("gps3dFix", [gps.latitude, gps.longitude, gps.altitude]))
        print(gps.latitude, gps.longitude, gps.altitude)
        sys.stdout.flush()
        
        #send speed in km/h
        pub.send_multipart(ZmqCodec.encode("gpsSpeed", [gps.speed]))


        #send EPX, EPY, EPV, EPS
        pub.send_multipart(ZmqCodec.encode("gpsEPEP", [gps.epx, gps.epy, gps.epv, gps.eps]))

        time.sleep(0.5)
    
    