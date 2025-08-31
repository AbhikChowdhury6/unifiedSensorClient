import os
import sys
import zmq

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec

from config import csv_writer_subscription_endpoints, zmq_control_endpoint
from config import csv_writer_subscription_topics, csv_writer_write_location

def csv_writer():
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    for subscription in csv_writer_subscription_endpoints:
        sub.connect(subscription)
        print(f"csv writer connected to {subscription}")
        sys.stdout.flush()
    print("csv writer connected to all endpoints")
    sys.stdout.flush()


    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    for topic in csv_writer_subscription_topics:
        sub.setsockopt(zmq.SUBSCRIBE, topic.encode())
        print(f"csv writer subscribed to {topic}")
        sys.stdout.flush()
    print("csv writer subscribed to all topics")
    sys.stdout.flush()
    
    #check if the files exist
    for topic in csv_writer_subscription_topics:
        if not os.path.exists(f"{csv_writer_write_location}{topic}.csv"):
            print(f"csv writer creating {topic}.csv")
            sys.stdout.flush()
            with open(f"{csv_writer_write_location}{topic}.csv", "w") as f:
                f.write("time,data\n")


    while True:
        topic, msg = ZmqCodec.decode(sub.recv_multipart())
        if topic == "control":
            if msg == "exit":
                print("csv writer got control exit")
                sys.stdout.flush()
                break
        # this will write the data to a csv file with the topic name
        if topic in csv_writer_subscription_topics:
            with open(f"{csv_writer_write_location}{topic}.csv", "a") as f:
                f.write(f"{msg}\n")
            print(f"csv writer wrote {msg} to {topic}.csv")
            sys.stdout.flush()
        else:
            print(f"csv writer got unknown topic {topic}")
            sys.stdout.flush()
    print("csv writer exiting")