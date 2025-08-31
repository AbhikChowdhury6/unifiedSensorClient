import os
import sys
import zmq

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec

from config import csv_writer_subscriptions_endpoints, zmq_control_endpoint
from config import csv_writer_subscriptions_topics, csv_writer_write_location
ctx = zmq.Context()
sub = ctx.socket(zmq.SUB)
sub.connect(zmq_control_endpoint)
for subscription in csv_writer_subscriptions_endpoints:
    sub.connect(subscription)


sub.setsockopt(zmq.SUBSCRIBE, b"control")
for topic in csv_writer_subscriptions_topics:
    sub.setsockopt(zmq.SUBSCRIBE, topic.encode())

while True:
    topic, msg = sub.recv_multipart()
    if topic == b"control":
        if msg == b"exit":
            break
    # this will write the data to a csv file with the topic name
    if topic in csv_writer_subscriptions_topics:
        with open(f"{csv_writer_write_location}{topic.decode()}.csv", "a") as f:
            f.write(f"{msg}\n")