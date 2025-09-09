import os
import sys
import time
import bisect
from datetime import datetime, timezone, timedelta

import zmq

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec

from config import (
    detector_based_deleter_config,
    zmq_control_endpoint,
)

# Optional writer roots if present in config; used as defaults for managed roots
try:
    from config import audio_writer_config, h264_writer_config, jpeg_writer_config
except Exception:
    audio_writer_config = h264_writer_config = jpeg_writer_config = None


def _parse_ts_from_filename(path: str):
    """
    Extract UTC timestamp seconds from filename by parsing the last underscore-separated
    token before the extension, using the unified format: YYYYMMDDTHHMMSSpMSZ.
    Returns integer epoch seconds (UTC) or None if unparseable.
    """
    try:
        base = os.path.basename(path)
        name, _ext = os.path.splitext(base)
        last = name.split("_")[-1]
        # Unified style: 20240101T120000p123Z
        if last.endswith("Z") and "T" in last and "p" in last:
            core = last[:-1]  # drop Z
            dt_str, ms_str = core.split("p", 1)
            dt = datetime.strptime(dt_str, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
            ms = int(ms_str)
            return int((dt + timedelta(milliseconds=ms)).timestamp())
    except Exception:
        return None
    return None


def _iter_hour_dirs_between(root: str, start_utc: datetime, end_utc: datetime):
    """Yield existing hour directories under root between [start_utc, end_utc]."""
    # Normalize to hour boundaries (UTC)
    cur = start_utc.replace(minute=0, second=0, microsecond=0)
    end = end_utc.replace(minute=0, second=0, microsecond=0)
    while cur <= end:
        rel = cur.strftime("%Y/%m/%d/%H")
        path = os.path.join(root, rel)
        if os.path.isdir(path):
            yield path
        cur += timedelta(hours=1)


def _index_initial_files(roots, lookback_seconds: int):
    now = datetime.now(timezone.utc)
    start = now - timedelta(seconds=max(lookback_seconds, 0))
    files_by_second: dict[int, list[str]] = {}
    seen_paths: set[str] = set()
    for root in roots:
        try:
            for hour_dir in _iter_hour_dirs_between(root, start, now):
                try:
                    with os.scandir(hour_dir) as it:
                        for entry in it:
                            if not entry.is_file():
                                continue
                            p = entry.path
                            if p in seen_paths:
                                continue
                            sec = _parse_ts_from_filename(p)
                            if sec is None:
                                continue
                            files_by_second.setdefault(sec, []).append(p)
                            seen_paths.add(p)
                except FileNotFoundError:
                    continue
        except Exception:
            continue
    return files_by_second, seen_paths


def _scan_recent_hours_for_new(roots, seen_paths: set[str]):
    """Scan only current and previous UTC hour directories for new files."""
    now = datetime.now(timezone.utc)
    recent_dirs = []
    for root in roots:
        for dt in (now, now - timedelta(hours=1)):
            d = os.path.join(root, dt.strftime("%Y/%m/%d/%H"))
            if os.path.isdir(d):
                recent_dirs.append(d)
    updates: dict[int, list[str]] = {}
    for d in recent_dirs:
        try:
            with os.scandir(d) as it:
                for entry in it:
                    if not entry.is_file():
                        continue
                    p = entry.path
                    if p in seen_paths:
                        continue
                    sec = _parse_ts_from_filename(p)
                    if sec is None:
                        continue
                    updates.setdefault(sec, []).append(p)
                    seen_paths.add(p)
        except FileNotFoundError:
            continue
    return updates


def _sorted_add(lst: list[int], value: int):
    i = bisect.bisect_left(lst, value)
    if i == len(lst) or lst[i] != value:
        lst.insert(i, value)


def detector_based_deleter():
    # Load config with defaults
    cfg = detector_based_deleter_config or {}
    detector_topic = cfg.get("detector_name")
    detector_endpoint = cfg.get("detector_endpoint")
    if not detector_topic or not detector_endpoint:
        print("detector_based_deleter: missing detector config")
        sys.stdout.flush()
        return

    seconds_before_keep = int(cfg.get("seconds_before_keep", 8))
    seconds_after_keep = int(cfg.get("seconds_after_keep", 4))
    min_file_age_seconds = int(cfg.get("min_file_age_seconds", 8))
    rescan_interval_seconds = float(cfg.get("rescan_interval_seconds", 5.0))

    # Determine managed roots
    manage_root = cfg.get("manage_root")


    # ZMQ setup
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(detector_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, detector_topic.encode())
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")

    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)

    print("detector_based_deleter subscribed to control and detector")
    print("detector_based_deleter managing root: ", manage_root)
    sys.stdout.flush()

    # Build initial index: only look back a bounded window
    lookback = max(seconds_before_keep + seconds_after_keep + 3600, 3600)
    files_by_second, seen_paths = _index_initial_files(manage_root, lookback)
    seconds_index = sorted(files_by_second.keys())

    # Detection seconds (UTC) where detected == 1
    detection_seconds_set: set[int] = set()
    detection_seconds_sorted: list[int] = []

    last_rescan = time.monotonic()

    try:
        while True:
            # Poll with 1s cadence to align to seconds
            timeout_ms = 1000
            events = dict(poller.poll(timeout_ms))

            if sub in events and events[sub] & zmq.POLLIN:
                try:
                    parts = sub.recv_multipart(zmq.NOBLOCK)
                except zmq.Again:
                    parts = None
                if parts is not None:
                    topic, obj = ZmqCodec.decode(parts)
                    if topic == "control":
                        if obj == "exit":
                            print("detector_based_deleter got control exit")
                            sys.stdout.flush()
                            break
                    elif topic == detector_topic:
                        try:
                            ts, detected = obj
                        except Exception:
                            ts, detected = None, None
                        if ts is not None and detected:
                            if isinstance(ts, datetime):
                                if ts.tzinfo is None:
                                    ts = ts.replace(tzinfo=timezone.utc)
                                sec = int(ts.timestamp())
                            else:
                                # assume epoch ns integer
                                sec = int((ts // 1_000_000_000))
                            if sec not in detection_seconds_set:
                                detection_seconds_set.add(sec)
                                _sorted_add(detection_seconds_sorted, sec)
                                # Optionally log
                                print(f"detector_based_deleter recorded detection at {sec}")
                                sys.stdout.flush()

            # Periodic light rescan for new files in current/previous hour
            if (time.monotonic() - last_rescan) >= rescan_interval_seconds:
                updates = _scan_recent_hours_for_new(manage_root, seen_paths)
                if updates:
                    for sec, paths in updates.items():
                        files_by_second.setdefault(sec, []).extend(paths)
                        if sec not in seconds_index:
                            _sorted_add(seconds_index, sec)
                last_rescan = time.monotonic()

            # Decide deletions for seconds far enough in the past
            now_sec = int(time.time())
            decision_cutoff = now_sec - seconds_before_keep - 1
            if seconds_index and seconds_index[0] <= decision_cutoff:
                # Prune old detection seconds that cannot protect anything at/after current cutoff
                prune_threshold = decision_cutoff - seconds_after_keep
                # remove all d <= prune_threshold
                prune_count = bisect.bisect_right(detection_seconds_sorted, prune_threshold)
                if prune_count > 0:
                    for d in detection_seconds_sorted[:prune_count]:
                        detection_seconds_set.discard(d)
                    detection_seconds_sorted = detection_seconds_sorted[prune_count:]

                # Evaluate candidate seconds up to cutoff
                idx = 0
                to_remove_seconds = []
                while idx < len(seconds_index) and seconds_index[idx] <= decision_cutoff:
                    sec = seconds_index[idx]
                    # Check if protected: does any detection d lie in [sec - seconds_after_keep, sec + seconds_before_keep]?
                    # Binary search in sorted detection list
                    protected = False
                    if detection_seconds_sorted:
                        left = sec - seconds_after_keep
                        right = sec + seconds_before_keep
                        j = bisect.bisect_left(detection_seconds_sorted, left)
                        if j < len(detection_seconds_sorted) and detection_seconds_sorted[j] <= right:
                            protected = True

                    if not protected:
                        # Attempt to delete files for this second, with safety age check
                        paths = files_by_second.get(sec, [])
                        survivors = []
                        for p in paths:
                            try:
                                st = os.stat(p)
                                age = time.time() - st.st_mtime
                                if age < min_file_age_seconds:
                                    survivors.append(p)
                                    continue
                                os.remove(p)
                                print(f"detector_based_deleter deleted {p}")
                                sys.stdout.flush()
                            except FileNotFoundError:
                                pass
                            except PermissionError:
                                # If cannot delete now, retry later
                                survivors.append(p)
                            except Exception as e:
                                print(f"detector_based_deleter failed to delete {p}: {e}")
                                sys.stdout.flush()
                                survivors.append(p)
                        if survivors:
                            files_by_second[sec] = survivors
                            idx += 1
                        else:
                            to_remove_seconds.append(sec)
                            idx += 1
                    else:
                        idx += 1

                # Drop empty seconds buckets from index and map
                if to_remove_seconds:
                    for s in to_remove_seconds:
                        files_by_second.pop(s, None)
                    # Remove from sorted index efficiently
                    seconds_index = [s for s in seconds_index if s not in set(to_remove_seconds)]

            # Keep CPU light
            # Loop continues at ~1 Hz from poll timeout

    finally:
        try:
            sub.close(0)
        except Exception:
            pass


if __name__ == "__main__":
    detector_based_deleter()