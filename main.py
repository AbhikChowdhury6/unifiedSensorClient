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

    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    # Wake up at least once per second if no messages arrive
    sub.setsockopt(zmq.RCVTIMEO, 1000)
    print("main connected to control topic")
    sys.stdout.flush()

    processes = _start_processes_dynamically()


    def _start_process(process_name):
        if process_name in processes:
            print(f"Process {process_name} is already running")
            return
        cfg = all_process_configs.get(process_name)
        module_name = cfg.get("module_name")
        class_name = cfg.get("class_name")
        module = importlib.import_module(module_name)
        target = getattr(module, class_name)
        p = mp.Process(target=target)
        p.start()
        processes[process_name] = p
        return p

    def _stop_process(process_name):
        if process_name not in all_process_configs:
            print(f"Process {process_name} is not in the config")
            return
        if process_name not in processes:
            print(f"Process {process_name} is not running")
            return
        cfg = all_process_configs.get(process_name)
        time_to_shutdown = cfg.get("time_to_shutdown")
        pub.send_multipart(ZmqCodec.encode("control", ["exit", process_name]))
        print(f"Waiting {time_to_shutdown} seconds for process {process_name} to shut down")
        time.sleep(time_to_shutdown)
        del processes[process_name]
        return
    
    def _is_process_running(process_name):
        if process_name not in all_process_configs:
            print(f"Process {process_name} is not in the config")
            pub.send_multipart(ZmqCodec.encode("control", ["status", 0, process_name]))
            return False
        if process_name not in processes:
            pub.send_multipart(ZmqCodec.encode("control", ["status", 0, process_name]))
            return False
        pub.send_multipart(ZmqCodec.encode("control", ["status", 1, process_name]))
        return True

    def _handle_control_message(command):
        if command[0] == "q":
            _exit_all()
            return
        elif command[0] == "e":
            _start_process(command[1])
            return
        elif command[0] == "d":
            _stop_process(command[1])
            return
        elif command[0] == "l":
            print("active processes:")
            for process in processes.keys():
                print(process)
            print("available processes:")
            for process in all_process_configs.keys():
                print(process)
            return

        elif command[0] == "s":
            if _is_process_running(command[1]):
                print(f"Process {command[1]} is running")
            else:
                print(f"Process {command[1]} is not running")
            return

        elif command[0] in ("log", "loglevel"):
            # usage: log <process|all> <level>  e.g., "log led debug" or "log all 5"
            target = command[1]
            level = command[2]
            pub.send_multipart(ZmqCodec.encode("control", ["set_loglevel", target, level]))
            return

        elif command[0] == "h":
            print("Available commands:")
            print("q, quit, exit: Exit the program")
            print("e: Start a process")
            print("l: List active processes and possible processes")
            print("d: Stop a process")
            print("h: Show this help message")
            return
        else:
            print(f"Unknown command: {command}")
            return



    def _exit_all():
        for p in processes:
            pub.send_multipart(ZmqCodec.encode("control", ["exit", p]))
        return

    while True:
        if processes and any(not processes[p].is_alive() for p in processes):
            for p in processes:
                print(p, processes[p].is_alive())
            _exit_all()
            break

        try:
            parts = sub.recv_multipart()
            topic, obj = ZmqCodec.decode(parts)
            print(f"main got control message: {obj}")
            _handle_control_message(obj)
        except zmq.Again:
            # timeout after ~1s: fall through to stdin/health checks
            pass

        if select.select([sys.stdin], [], [], 0)[0]:
            command = sys.stdin.readline().strip().split(" ")
            _handle_control_message(command)
    
    
    time.sleep(.1)
