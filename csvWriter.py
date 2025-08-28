import zmq

ctx = zmq.Context()
sub = ctx.socket(zmq.SUB)
# change this to the ipc port
sub.connect("tcp://localhost:5555")



# Subscribe to multiple topics
# we'll have an object of all the topics we want to subscribe to

sub.setsockopt(zmq.SUBSCRIBE, b"images")
sub.setsockopt(zmq.SUBSCRIBE, b"sensors")

while True:
    topic, msg = sub.recv_multipart()
    if topic == b"images":
        print("Got image:", msg)
    elif topic == b"sensors":
        print("Got sensor reading:", msg)
