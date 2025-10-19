import sys
import time
import math
import gc
import tracemalloc
from collections import Counter
from ultralytics import YOLO
import torch
import os
try:
    import psutil
    _PSUTIL = True
except Exception:
    _PSUTIL = False

import zmq
import logging

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec
from logUtils import worker_configurer, set_process_title

from config import (
    yolo_person_detector_process_config,
    zmq_control_endpoint,
)

config = yolo_person_detector_process_config
"""Optional deep-size support via Pympler (if installed)."""
try:
    from pympler import muppy, summary as pympler_summary
    _PYMPLER = True
except Exception:
    _PYMPLER = False

_tracemalloc_started = False
_last_snapshot = None

def memdiag_start(max_frames: int = 25):
    global _tracemalloc_started, _last_snapshot
    if not _tracemalloc_started:
        tracemalloc.start(max_frames)
        _tracemalloc_started = True
    _last_snapshot = tracemalloc.take_snapshot()

def memdiag_log(logger, tag: str = "", top_n: int = 15):
    global _last_snapshot
    try:
        # Cheap metrics first (avoid OOM): process RSS and GC counters
        rss_mb = None
        if _PSUTIL:
            try:
                proc = psutil.Process(os.getpid())
                rss_mb = proc.memory_info().rss / (1024 * 1024)
            except Exception:
                rss_mb = None
        gen_counts = gc.get_count()
        msg = f"[memdiag] {tag} rss_mb={rss_mb:.1f} gens={gen_counts}" if rss_mb is not None else f"[memdiag] {tag} gens={gen_counts}"
        # Optional CUDA stats
        try:
            if torch.cuda.is_available():
                alloc = torch.cuda.memory_allocated() / 1e6
                reserv = torch.cuda.memory_reserved() / 1e6
                msg += f" cuda_alloc_mb={alloc:.1f} cuda_resv_mb={reserv:.1f}"
        except Exception:
            pass
        logger.info(msg)

        # Heavy diagnostics (tracemalloc, pympler) gated by config
        if bool(config.get("memdiag_heavy", False)):
            # Force GC to reduce noise
            gc.collect()
            # Tracemalloc diff since last snapshot
            if _last_snapshot is None:
                _last_snapshot = tracemalloc.take_snapshot()
            snap_now = tracemalloc.take_snapshot()
            stats = snap_now.compare_to(_last_snapshot, 'lineno')
            _last_snapshot = snap_now
            lines = []
            for st in stats[:top_n]:
                size_kb = st.size_diff / 1024.0
                tb_last = st.traceback.format()[-1].strip() if st.traceback else "<no tb>"
                lines.append(f"{size_kb:9.1f} KiB {st.count_diff:+5d} {tb_last}")
            if lines:
                logger.info("[memdiag] " + tag + " top alloc growth:\n  " + "\n  ".join(lines))

            # Optional deep-size summary
            if _PYMPLER:
                try:
                    all_objs = muppy.get_objects()
                    sum_list = pympler_summary.summarize(all_objs)
                    logger.info("[memdiag] pympler summary (top 10):\n" + pympler_summary.format_(sum_list)[:2000])
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"[memdiag] failed: {e}")

def _compute_next_capture_ts(now_ts: float, interval_s: float) -> float:
    return int(math.ceil(now_ts / interval_s) * interval_s)


def yolo_person_detector(log_queue):
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
    sub.connect(config["camera_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, config["camera_name"].encode())
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


    next_capture = _compute_next_capture_ts(time.time(), interval_s)
    l.debug(config["short_name"] + " starting memdiag")
    memdiag_start()
    l.debug(config["short_name"] + " memdiag started")
    iter_count = 0
    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)

        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == "yolo"):
                l.info(config["short_name"] + " got control exit")
                break
            continue
        if topic != config["camera_name"]:
            continue

        dt_utc, frame = msg[0], msg[1]
        l.trace(config["short_name"] + " got frame: " + str(dt_utc))
        if dt_utc.timestamp() < next_capture:
            l.trace(config["short_name"] + " frame is too early, skipping")
            continue

        next_capture = _compute_next_capture_ts(dt_utc.timestamp(), interval_s)
        l.trace(config["short_name"] + " next capture: " + str(next_capture))
        # Ensure contiguous uint8 input to avoid internal copies
        try:
            is_c_contig = True
            if hasattr(frame, "flags"):
                try:
                    is_c_contig = bool(frame.flags["C_CONTIGUOUS"])  # numpy flagsobj supports __getitem__
                except Exception:
                    is_c_contig = bool(getattr(frame.flags, "c_contiguous", True))
            if not is_c_contig:
                l.trace(config["short_name"] + " frame is not C contiguous, making a copy")
                frame = frame.copy()
            if getattr(frame, "dtype", None) is not None and str(frame.dtype) != "uint8":
                l.trace(config["short_name"] + " frame is not uint8, converting")
                frame = frame.astype("uint8", copy=False)
        except Exception as e:
            l.warning(config["short_name"] + f" failed to convert frame: {e}")
            # proceed with original frame

        # Validate expected shape (H,W,3)
        try:
            if not (hasattr(frame, "ndim") and frame.ndim == 3 and getattr(frame, "shape", (0,0,0))[2] == 3):
                l.warning(config["short_name"] + f" invalid frame shape {getattr(frame, 'shape', None)}, skipping")
                continue
        except Exception:
            l.warning(config["short_name"] + " unable to inspect frame shape, skipping")
            continue

        # No-grad inference to avoid autograd graph allocations
        l.trace(config["short_name"] + " starting inference")
        start_time = time.time()
        try:
            with torch.inference_mode():
                results = model.predict(
                    source=frame,
                    verbose=config["verbose"],
                    conf=conf_thresh,
                    iou=nms_thresh,
                    stream=False,
                    save=False,
                    device=config.get("device", "cpu"),
                )
        except Exception as e:
            l.error(config["short_name"] + f" inference failed: {e}")
            continue
        l.debug(config["short_name"] + " inference completed in " + str(time.time() - start_time) + " seconds")
        person_confidence = 0.0
        # Iterate over detections to find 'person' class
        for r in results:
            boxes = r.boxes
            names = r.names
            if boxes is None:
                continue
            for cls_id, conf in zip(boxes.cls.tolist(), boxes.conf.tolist()):
                name = names.get(int(cls_id), str(int(cls_id)))
                if name.lower() == "person":
                    person_confidence = max(person_confidence, float(conf))


        detected = 1 if person_confidence >= conf_thresh else 0
        pub.send_multipart(ZmqCodec.encode(config["pub_topic"], [dt_utc, detected]))
        l.debug(config["short_name"] + " published " + str(detected) + " (person_conf=" + str(person_confidence) + ")")

        # Proactively drop references and occasionally run GC to curb growth
        del results
        del frame

        iter_count += 1
        if (iter_count % int(config.get("gc_interval", 10))) == 0:
            gc.collect()
        if (iter_count % int(config.get("memdiag_interval", 10))) == 0:
            memdiag_log(l, tag="yolo_loop")


    l.info(config["short_name"] + " exiting")


if __name__ == "__main__":
    yolo_person_detector(None)


