import os
import sys
import zmq
import subprocess
import threading
from datetime import datetime, timezone, timedelta
import math
import numpy as np
import logging

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec
from logUtils import worker_configurer, check_apply_level, set_process_title
from config import (
    mp4_writer_process_config,
    zmq_control_endpoint,
)

config = mp4_writer_process_config
l = logging.getLogger(config["short_name"])
def mp4_writer(log_queue):
    set_process_title(config["short_name"])
    worker_configurer(log_queue, config["debug_lvl"])
    l.info(config["short_name"] + " process starting")

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)

    # Control channel for graceful exit
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    l.info(config["short_name"] + " process connected to control topic")

    # Subscribe to camera frames
    camera_topic = cfg_get_or_default(config, "camera_name", "camera")
    camera_endpoint = cfg_get_or_default(config, "camera_endpoint", "")
    pub_endpoint = cfg_get_or_default(config, "publish_endpoint", "")
    pub_topic = cfg_get_or_default(config, "publish_topic", "")
    sub.connect(camera_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, camera_topic.encode())
    pub = ctx.socket(zmq.PUB)
    pub.bind(pub_endpoint)

    write_location = cfg_get_or_default(config, "write_location", "/home/pi/mp4_writer/data/")
    duration_s = int(cfg_get_or_default(config, "duration_s", 4))
    # If there's a long gap between frames, start a new file. Default 2 seconds.
    gap_restart_seconds = float(cfg_get_or_default(config, "frame_gap_restart_seconds", .5))

    os.makedirs(write_location, exist_ok=True)

    # Always use software libx264 with CRF

    ffmpeg_proc = None
    frames_written_in_segment = 0
    segment_start_dt = None
    segment_end_dt = None
    last_ts_seconds = None
    current_out_path = None


    l.info(config["short_name"] + " subscribed to " + camera_topic + " at " + camera_endpoint)
    l.info(config["short_name"] + " publishing to " + pub_topic + " at " + pub_endpoint)

    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)
        if topic == "control":
            if msg[0] == "exit_all" or (msg[0] == "exit" and msg[-1] == "mp4"):
                l.info(config["short_name"] + " got control exit")
                try:
                    ffmpeg_proc.stdin.close()
                except Exception:
                    pass
                try:
                    ffmpeg_proc.wait(timeout=3)
                except Exception:
                    pass
                break
            if check_apply_level(msg, config["short_name"]):
                continue
            continue

        if topic != camera_topic:
            continue

        dt_utc, frame = msg[0], msg[1]

        # Ensure frame is a contiguous uint8 array in expected shape
        if not isinstance(frame, np.ndarray):
            l.error(config["short_name"] + " frame is not a numpy array")
            continue
        if frame.ndim != 3 or frame.shape[2] != 3:
            l.error(config["short_name"] + " invalid frame shape " + str(frame.shape) + ", expected (H,W,3)")
            continue
        if not frame.flags["C_CONTIGUOUS"]:
            l.error(config["short_name"] + " frame is not C contiguous, making a copy")
            frame = np.ascontiguousarray(frame)
        if frame.dtype != np.uint8:
            l.error(config["short_name"] + " converting frame from " + str(frame.dtype) + " to uint8")
            frame = frame.astype(np.uint8, copy=False)

        # If there's a large break in frames, close current segment
        if ffmpeg_proc is not None and last_ts_seconds is not None:
            if (dt_utc.timestamp() - last_ts_seconds) > gap_restart_seconds:
                try:
                    ffmpeg_proc.stdin.close()
                except Exception:
                    pass
                try:
                    ffmpeg_proc.wait(timeout=3)
                except Exception:
                    pass
                # Publish just-closed segment due to gap
                try:
                    if current_out_path is not None:
                        pub.send_multipart(ZmqCodec.encode(pub_topic, [segment_start_dt, current_out_path]))
                except Exception:
                    pass
                ffmpeg_proc = None
                frames_written_in_segment = 0
                segment_start_dt = None
                segment_end_dt = None
                current_out_path = None
                l.debug(config["short_name"] + " detected frame gap " + str(dt_utc.timestamp() - last_ts_seconds) + "s, starting new file")

        # If current frame is in a newer 4s grid, roll to the next aligned segment
        if ffmpeg_proc is not None and segment_end_dt is not None and isinstance(dt_utc, datetime):
            if dt_utc >= segment_end_dt:
                try:
                    ffmpeg_proc.stdin.close()
                except Exception:
                    pass
                try:
                    ffmpeg_proc.wait(timeout=3)
                except Exception:
                    pass
                # Publish just-closed segment on rotation
                try:
                    if current_out_path is not None:
                        pub.send_multipart(ZmqCodec.encode(pub_topic, [segment_start_dt, current_out_path]))
                except Exception:
                    pass
                ffmpeg_proc = None
                frames_written_in_segment = 0
                segment_start_dt = None
                segment_end_dt = None
                current_out_path = None

        # Detect actual WxH from first frame (in case of subsampling)
        if ffmpeg_proc is None:
            height, width, _ = frame.shape
            base_ts = dt_utc
            # Align start to 4s grid; allow partial segments at boundaries
            aligned_epoch = int(base_ts.timestamp()) - (int(base_ts.timestamp()) % duration_s)
            segment_start_dt = datetime.fromtimestamp(aligned_epoch, tz=timezone.utc)
            segment_end_dt = segment_start_dt + timedelta(seconds=duration_s)
            start_str = _format_ts_for_filename(segment_start_dt)
            
            # Write into UTC hourly folders: YYYY/MM/DD/HH/MM/
            hourly_subdir = segment_start_dt.astimezone(timezone.utc).strftime("%Y/%m/%d/%H/%M/")
            out_dir = os.path.join(write_location, hourly_subdir)
            os.makedirs(out_dir, exist_ok=True)
            base_name = f"{config['file_base']}_{start_str}.mp4"
            out_path = os.path.join(out_dir, base_name)
            
            # Determine runtime width/height/pix_fmt/fps
            fmt = cfg_get_or_default(config, "format", "RGB888")
            pix_fmt = "rgb24" if str(fmt).upper() in ("RGB888", "RGB24") else "bgr24"
            fps = int(cfg_get_or_default(config, "fps", 8))
            ffmpeg_proc = _spawn_ffmpeg(out_path, width, height, pix_fmt, fps)
            frames_written_in_segment = 0
            l.debug(config["short_name"] + " started segment " + out_path)
            current_out_path = out_path

        # Write frame to ffmpeg stdin
        try:
            ffmpeg_proc.stdin.write(frame.tobytes())
        except (BrokenPipeError, AttributeError):
            # Restart ffmpeg on failure
            if ffmpeg_proc is not None:
                try:
                    ffmpeg_proc.stdin.close()
                except Exception:
                    pass
                try:
                    ffmpeg_proc.wait(timeout=1)
                except Exception:
                    pass
            # Publish just-closed segment on failure
            try:
                if current_out_path is not None:
                    pub.send_multipart(ZmqCodec.encode(pub_topic, [segment_start_dt, current_out_path]))
            except Exception:
                pass
            ffmpeg_proc = None
            frames_written_in_segment = 0
            segment_start_dt = None
            segment_end_dt = None
            current_out_path = None
            continue

        frames_written_in_segment += 1
        last_ts_seconds = dt_utc.timestamp()

        # End the segment only on gap; otherwise allow variable-length files

    # Cleanup on exit
    if ffmpeg_proc is not None:
        try:
            ffmpeg_proc.stdin.close()
        except Exception:
            pass
        try:
            ffmpeg_proc.wait(timeout=3)
        except Exception:
            pass
        # Publish just-closed segment on shutdown
        try:
            if current_out_path is not None:
                pub.send_multipart(ZmqCodec.encode(pub_topic, [segment_start_dt, current_out_path]))
        except Exception:
            pass

    l.info(config["short_name"] + " exiting")




def _spawn_ffmpeg(output_path: str, width: int, height: int, pix_fmt: str, fps: int):
    # Read settings from config
    quality = int(cfg_get_or_default(config, "quality", 80))
    crf = _quality_to_crf(quality)
    gop_interval_seconds = int(cfg_get_or_default(config, "keyframe_interval_seconds", 1))
    gop_frames = max(1, fps * gop_interval_seconds)
    loglevel = str(cfg_get_or_default(config, "loglevel", "warning"))

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", loglevel,
        "-y", 
        "-f", "rawvideo",
        "-pix_fmt", pix_fmt,
        "-s", f"{width}x{height}",
        "-r", str(fps),
        "-i", "pipe:0",
    ]

    # Use libx264 with CRF-based quality control
    cmd += [
        "-c:v", "libx264",
        "-preset", "veryfast", 
        "-crf", str(crf),
        # Control keyframe interval: exactly one I-frame every gop_frames
        "-g", str(gop_frames),
        "-keyint_min", str(gop_frames),
        "-sc_threshold", "0",
        # Ensure broad compatibility
        "-vf", "format=yuv420p",
    ]

    cmd += [
        "-movflags", "+faststart",
        output_path,
    ]
    # Use Popen with a PIPE for stdin
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        l.debug(config["short_name"] + " started ffmpeg: " + " ".join(cmd))
        t = threading.Thread(target=_stderr_reader, args=(proc,), daemon=True)
        t.start()
        proc._stderr_thread = t  # attach for lifecycle awareness
        return proc
    except FileNotFoundError:
        l.error(config["short_name"] + " ffmpeg not found. Please install ffmpeg.")
        return None
    except Exception as e:
        l.error(config["short_name"] + " failed to start ffmpeg: " + str(e))
        return None


def _stderr_reader(p):
    try:
        for raw in iter(p.stderr.readline, b""):
            line = raw.decode(errors="replace").rstrip()
            if line:
                l.debug(config["short_name"] + " ffmpeg stderr: " + line)
    except Exception as e:
        l.error(config["short_name"] + " ffmpeg stderr reader error: " + str(e))
    finally:
        l.debug(config["short_name"] + " ffmpeg stderr: [closed]")



def _format_ts_for_filename(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts_utc = ts.astimezone(timezone.utc)
    return ts_utc.strftime("%Y%m%dT%H%M%S") + "p" + str(ts_utc.microsecond // 1000).zfill(3) + "Z"


def _quality_to_crf(quality_0_100: int) -> int:
    # Map 0..100 (low..high) to CRF 51..16 (high..low)
    q = max(0, min(100, int(quality_0_100)))
    # Linear map to a reasonable CRF window
    return int(round(51 - (q / 100.0) * 35))

def cfg_get_or_default(cfg, key, default):
    try:
        value = cfg.get(key)
    except Exception:
        value = None
    if value is None:
        l.error(config["short_name"] + " config missing '" + key + "', using default " + str(default))
        return default
    return value

if __name__ == "__main__":
    mp4_writer(None)


