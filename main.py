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

        short_name = cfg.get("short_name")
        processes[short_name] = p

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
            pub.send_multipart(ZmqCodec.encode("control", ["exit_all"]))
            break

        if select.select([sys.stdin], [], [], 0)[0]:
            command = sys.stdin.readline().strip().split(" ")
            if command[0] == 'q':
                print("Got exit command, shutting down...")
                pub.send_multipart(ZmqCodec.encode("control", ["exit_all"]))
                break
            elif command[0] == 'e':
                # check if the process is running
                if command[1] in processes.keys():
                    print(f"Process {command[1]} is running")
                else:
                    print(f"Process {command[1]} is not running, starting it")
                    # find the module and class name with the short name
                    cfg = all_process_configs.get(command[1])
                    module_name = cfg.get("module_name")
                    class_name = cfg.get("class_name")
                    module = importlib.import_module(module_name)
                    target = getattr(module, class_name)
                    p = mp.Process(target=target)
                    p.start()
                    processes[command[1]] = p
            elif command[0] == 'd':
                # check if the process is running
                if command[1] in processes.keys():
                    print(f"Process {command[1]} is running, stopping it")
                    cfg = all_process_configs.get(command[1])
                    time_to_shutdown = cfg.get("time_to_shutdown")
                    pub.send_multipart(ZmqCodec.encode("control", ["exit", command[1]]))
                    print(f"Waiting {time_to_shutdown} seconds for process {command[1]} to shut down")
                    time.sleep(time_to_shutdown)
                    del processes[command[1]]
                else:
                    print(f"Process {command[1]} is not running")
            elif command[0] == 'l':
                print("active processes:")
                for process in processes.keys():
                    print(process)
                print("available processes:")
                for process in all_process_configs.keys():
                    print(process)
            elif command[0] == 'h':
                print("Available commands:")
                print("q, quit, exit: Exit the program")
                print("e: Start a process")
                print("l: List active processes and possible processes")
                print("d: Stop a process")
                print("h: Show this help message")
            else:
                print(f"Unknown command: {command}")
    
    
    time.sleep(1)
