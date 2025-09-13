import os
import sys
import select
import time
import importlib
import zmq
import multiprocessing as mp

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    zmq_control_endpoint,
    init_log_queue,
    all_process_configs,
)
from zmq_codec import ZmqCodec



def _start_processes_dynamically():
    processes = {}
    for name in all_process_configs.keys():
        cfg = all_process_configs.get(name)

        module_name = cfg.get("module_name")
        class_name = cfg.get("class_name")
        module = importlib.import_module(module_name)
        target = getattr(module, class_name)

        p = mp.Process(target=target)
        p.start()
        processes[name] = p

    return processes


if __name__ == "__main__":
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.bind(zmq_control_endpoint)

    processes = _start_processes_dynamically()

    while True:
        if processes and any(not processes[p].is_alive() for p in processes):
            for p in processes:
                print(p, processes[p].is_alive())
            pub.send_multipart(ZmqCodec.encode("control", "exit"))
            break

        if select.select([sys.stdin], [], [], 0)[0]:
            if sys.stdin.read(1) == 'q':
                print("got q going to start exiting")
                pub.send_multipart(ZmqCodec.encode("control", "exit"))
                break
    time.sleep(1)
