import sys
import time
import math
import gc
import tracemalloc
from collections import Counter
from ultralytics import YOLO
import numpy as np
import torch
import os
from datetime import datetime
try:
    import psutil
    _PSUTIL = True
except Exception:
    _PSUTIL = False

import zmq
import logging

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from platformUtils.zmq_codec import ZmqCodec
from platformUtils.logUtils import worker_configurer, set_process_title

from config import (
    zmq_control_endpoint,
)

"""Optional deep-size support via Pympler (if installed)."""
try:
    from pympler import muppy, summary as pympler_summary
    _PYMPLER = True
except Exception:
    _PYMPLER = False

_tracemalloc_started = False
_last_snapshot = None

# def memdiag_start(max_frames: int = 25):
#     global _tracemalloc_started, _last_snapshot
#     # Start tracemalloc only for heavy diagnostics
#     if bool(config.get("memdiag_heavy", False)):
#         if not _tracemalloc_started:
#             tracemalloc.start(max_frames)
#             _tracemalloc_started = True
#         _last_snapshot = tracemalloc.take_snapshot()

# def memdiag_log(logger, tag: str = "", top_n: int = 15):
#     global _last_snapshot
#     try:
#         # Cheap metrics first (avoid OOM): process RSS and GC counters
#         rss_mb = None
#         if _PSUTIL:
#             try:
#                 proc = psutil.Process(os.getpid())
#                 rss_mb = proc.memory_info().rss / (1024 * 1024)
#             except Exception:
#                 rss_mb = None
#         gen_counts = gc.get_count()
#         msg = f"[memdiag] {tag} rss_mb={rss_mb:.1f} gens={gen_counts}" if rss_mb is not None else f"[memdiag] {tag} gens={gen_counts}"
#         # Optional CUDA stats
#         try:
#             if torch.cuda.is_available():
#                 alloc = torch.cuda.memory_allocated() / 1e6
#                 reserv = torch.cuda.memory_reserved() / 1e6
#                 msg += f" cuda_alloc_mb={alloc:.1f} cuda_resv_mb={reserv:.1f}"
#         except Exception:
#             pass
#         logger.info(msg)

#         # Heavy diagnostics (tracemalloc, pympler) gated by config
#         if bool(config.get("memdiag_heavy", False)):
#             # Force GC to reduce noise
#             gc.collect()
#             # Tracemalloc diff since last snapshot
#             if _last_snapshot is None:
#                 _last_snapshot = tracemalloc.take_snapshot()
#             snap_now = tracemalloc.take_snapshot()
#             stats = snap_now.compare_to(_last_snapshot, 'lineno')
#             _last_snapshot = snap_now
#             lines = []
#             for st in stats[:top_n]:
#                 size_kb = st.size_diff / 1024.0
#                 tb_last = st.traceback.format()[-1].strip() if st.traceback else "<no tb>"
#                 lines.append(f"{size_kb:9.1f} KiB {st.count_diff:+5d} {tb_last}")
#             if lines:
#                 logger.info("[memdiag] " + tag + " top alloc growth:\n  " + "\n  ".join(lines))

#             # Optional deep-size summary
#             if _PYMPLER:
#                 try:
#                     all_objs = muppy.get_objects()
#                     sum_list = pympler_summary.summarize(all_objs)
#                     logger.info("[memdiag] pympler summary (top 10):\n" + pympler_summary.format_(sum_list)[:2000])
#                 except Exception:
#                     pass
#     except Exception as e:
#         logger.warning(f"[memdiag] failed: {e}")

def _compute_next_capture_dt(now_dt: datetime, interval_s: float) -> datetime:
    return int(math.ceil(now_dt.timestamp() / interval_s) * interval_s)


#should we make this more like a senor?
#like we would want to add
#timestamp rounding (although it will be the same as the received one)
#this is one where latency is expected

#for downstream systems, as long as order is preserved,
#actually nahhh, it also has to be timely
#but it would just have to show up before time till irrelevance
#like 32 seconds, we could run the model every n seconds based on the platform
#like 8 seconds on the pi5 and 8 seconds on the pi4 with a smaller model


def yolo_person_detector(log_queue, config):
    set_process_title(config["short_name"])
    worker_configurer(log_queue, config["debug_lvl"])
    l = logging.getLogger(config["short_name"])
    l.info(config["short_name"] + " process starting")

    #subscribe to control topic
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    l.info(config["short_name"] + " process connected to control topic")


    #subscribe to camera topic
    l.info(config["short_name"] + " camera endpoint: " + config["camera_endpoint"])
    l.info(config["short_name"] + " camera topic: " + config["camera_topic"])
    sub.connect(config["camera_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, config["camera_topic"].encode())
    l.info(config["short_name"] + " process connected to camera topic")


    #connect to pub endpoint
    pub = ctx.socket(zmq.PUB)
    pub.bind(config["pub_endpoint"])
    l.info(config["short_name"] + " process connected to pub topic")


    interval_s = float(config.get("interval_seconds", 4))
    conf_thresh = float(config.get("confidence_threshold", 0.7))
    nms_thresh = float(config.get("nms_threshold", 0.7))

    model_name = config.get("model", "yolo11m")
    model = YOLO(model_name)
    l.info(config["short_name"] + " loaded YOLO model " + model_name)


    next_capture = None
#    l.debug(config["short_name"] + " starting memdiag")
#    memdiag_start()
#    l.debug(config["short_name"] + " memdiag started")
    iter_count = 0
    
    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)

        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == "yolo"):
                l.info(config["short_name"] + " got control exit")
                break
            continue
        if topic != config["camera_topic"]:
            continue

        dt_utc, frame = msg[0], msg[1]
        l.trace(config["short_name"] + " got frame: " + str(dt_utc))
        
        if next_capture is None:
            next_capture = _compute_next_capture_dt(dt_utc, interval_s)
        
        if dt_utc.timestamp() < next_capture:
            l.trace(config["short_name"] + " frame is too early, skipping")
            continue

        next_capture = None #it computes the next capture based on the next frame
        l.trace(config["short_name"] + " next capture: " + str(next_capture))
 

        l.trace(config["short_name"] + " starting inference")
        start_time = time.time()
        results = model.predict(frame[0], verbose=config["verbose"])

        l.debug(config["short_name"] + " inference completed in " + str(time.time() - start_time) + " seconds")
        
        indexesOfPeople = [i for i, x in enumerate(results[0].boxes.cls) if x == 0]
        if len(indexesOfPeople) > 0:
            l.debug("saw %d people",len(indexesOfPeople))
            sys.stdout.flush()
            maxPersonConf = max([results[0].boxes.conf[i] for i in indexesOfPeople])
            l.debug("the most confident recognition was %f", maxPersonConf)
            if maxPersonConf > config["confidence_threshold"]:
                detected = 1
            else:
                detected = 0
        else:
            l.debug("didn't see anyone")
            detected = 0


        pub.send_multipart(ZmqCodec.encode(config["pub_topic"], [dt_utc, detected]))
        l.debug(config["short_name"] + " published " + str(detected))



        iter_count += 1
#        if (iter_count % int(config.get("memdiag_interval", 10))) == 0:
#            memdiag_log(l, tag="yolo_loop")


    l.info(config["short_name"] + " exiting")




