import os
import sys
import zmq
from datetime import datetime, timezone
import numpy as np

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec

from config import csv_writer_process_config, zmq_control_endpoint
config = csv_writer_process_config

def csv_writer():
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    for endpoint in config['subscription_endpoints']:
        sub.connect(endpoint)
    print("csv writer connected to subscription endpoint")
    sys.stdout.flush()


    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    for topic in config['subscription_topics']:
        sub.setsockopt(zmq.SUBSCRIBE, topic.encode())
        print(f"csv writer subscribed to {topic}")
        sys.stdout.flush()
    print("csv writer subscribed to all topics")
    sys.stdout.flush()
    
    os.makedirs(config['write_location'], exist_ok=True)
    #check if the files exist and create directories if needed
    for topic in config['subscription_topics']:
            
        filepath = os.path.join(config['write_location'], f"{topic}.csv")
        if not os.path.exists(filepath):
            print(f"csv writer creating {filepath}")
            sys.stdout.flush()
            with open(filepath, "w") as f:
                f.write("time,data\n")

    while True:
        topic, msg = ZmqCodec.decode(sub.recv_multipart())
        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == "csv"):
                print("csv writer got control exit")
                sys.stdout.flush()
                break
        # this will write the data to a csv file with the topic name
        if topic in config['subscription_topics']:
            ts, value = msg[0], msg[1]
            # Normalize timestamp to ISO 8601 UTC
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                ts_str = ts.isoformat()
            else:
                # assume epoch ns
                ts_str = datetime.fromtimestamp(ts/1_000_000_000, tz=timezone.utc).isoformat()

            # Normalize numpy values for CSV
            if isinstance(value, np.ndarray):
                if value.ndim == 0:
                    value_str = str(float(value))
                else:
                    value_str = np.array2string(value, separator=',')
            elif isinstance(value, np.generic):
                value_str = str(float(value))
            else:
                value_str = str(value)

            with open(f"{config['write_location']}{topic}.csv", "a") as f:
                f.write(f"{ts_str},{value_str}\n")
            #print(f"csv writer wrote {msg} to {topic}.csv")
            #sys.stdout.flush()
        else: 
            print(f"csv writer got unknown topic {topic}")
            sys.stdout.flush()
    print("csv writer exiting")