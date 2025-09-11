import os
import sys
import zmq
import subprocess
from datetime import datetime, timezone, timedelta
import math
import numpy as np

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec

from config import (
    h264_writer_config,
    zmq_control_endpoint,
)



def h264_writer():
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)

    # Control channel for graceful exit
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")

    # Subscribe to camera frames
    camera_topic = cfg_get_or_default(h264_writer_config, "camera_name", "camera")
    camera_endpoint = cfg_get_or_default(h264_writer_config, "camera_endpoint", "")
    pub_endpoint = cfg_get_or_default(h264_writer_config, "publish_endpoint", "")
    pub_topic = cfg_get_or_default(h264_writer_config, "publish_topic", "")
    sub.connect(camera_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, camera_topic.encode())
    pub = ctx.socket(zmq.PUB)
    pub.bind(pub_endpoint)

    write_location = cfg_get_or_default(h264_writer_config, "write_location", "/home/pi/h264_writer/data/")
    duration_s = int(cfg_get_or_default(h264_writer_config, "video_duration", 4))
    # If there's a long gap between frames, start a new file. Default 2 seconds.
    gap_restart_seconds = float(cfg_get_or_default(h264_writer_config, "frame_gap_restart_seconds", .5))

    os.makedirs(write_location, exist_ok=True)

    # Always use software libx264 with CRF

    ffmpeg_proc = None
    frames_written_in_segment = 0
    segment_start_ts = None
    segment_end_ts = None
    last_ts_seconds = None


    print(f"h264 writer subscribed to {camera_topic} at {camera_endpoint}")
    print(f"h264 writer publishing to {pub_topic} at {pub_endpoint}")
    sys.stdout.flush()

    while True:
        parts = sub.recv_multipart()
        topic, msg = ZmqCodec.decode(parts)
        if topic == "control":
            if msg == "exit":
                print("h264 writer got control exit")
                sys.stdout.flush()
                break
            continue

        if topic != camera_topic:
            continue

        dt_utc, frame = msg[0], msg[1]

        # Ensure frame is a contiguous uint8 array in expected shape
        if not isinstance(frame, np.ndarray):
            print("h264 writer: frame is not a numpy array")
            sys.stdout.flush()
            continue
        if frame.ndim != 3 or frame.shape[2] != 3:
            print(f"h264 writer: invalid frame shape {frame.shape}, expected (H,W,3)")
            sys.stdout.flush() 
            continue
        if not frame.flags["C_CONTIGUOUS"]:
            print("h264 writer: frame is not C contiguous, making a copy")
            sys.stdout.flush()
            frame = np.ascontiguousarray(frame)
        if frame.dtype != np.uint8:
            print(f"h264 writer: converting frame from {frame.dtype} to uint8")
            sys.stdout.flush()
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
                ffmpeg_proc = None
                frames_written_in_segment = 0
                segment_start_ts = None
                print(f"h264 writer detected frame gap {(dt_utc.timestamp() - last_ts_seconds):.3f}s, starting new file")
                sys.stdout.flush()

        # If current frame is in a newer 4s grid, roll to the next aligned segment
        if ffmpeg_proc is not None and segment_end_ts is not None and isinstance(dt_utc, datetime):
            if dt_utc >= segment_end_dt:
                try:
                    ffmpeg_proc.stdin.close()
                except Exception:
                    pass
                try:
                    ffmpeg_proc.wait(timeout=3)
                except Exception:
                    pass
                ffmpeg_proc = None
                frames_written_in_segment = 0
                segment_start_ts = None
                segment_end_ts = None

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
            base_name = f"{camera_topic}_{start_str}.h264"
            out_path = os.path.join(out_dir, base_name)
            
            ffmpeg_proc = _spawn_ffmpeg(out_path)
            frames_written_in_segment = 0
            print(f"h264 writer started segment {out_path}")
            sys.stdout.flush()
            pub.send_multipart(ZmqCodec.encode(pub_topic, [segment_start_dt, out_dir]))

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
            ffmpeg_proc = None
            frames_written_in_segment = 0
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

    print("h264 writer exiting")
    sys.stdout.flush()




def _spawn_ffmpeg(output_path: str):
    # Read settings from config
    cfg_fps = int(cfg_get_or_default(h264_writer_config, "fps", 8))
    fmt = cfg_get_or_default(h264_writer_config, "format", "RGB888")
    quality = int(cfg_get_or_default(h264_writer_config, "quality", 80))
    crf = _quality_to_crf(quality)
    gop_interval_seconds = int(cfg_get_or_default(h264_writer_config, "keyframe_interval_seconds", 1))
    gop_frames = max(1, cfg_fps * gop_interval_seconds)
    width = int(cfg_get_or_default(h264_writer_config, "width", 640))
    height = int(cfg_get_or_default(h264_writer_config, "height", 480))
    pix_fmt = "rgb24" if fmt.upper() in ("RGB888", "RGB24") else "bgr24"

    cmd = [
        "ffmpeg",
        "-y", 
        "-f", "rawvideo",
        "-pix_fmt", pix_fmt,
        "-s", f"{width}x{height}",
        "-r", str(cfg_fps),
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
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)



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
        print(f"h264 writer: config missing '{key}', using default {default}")
        sys.stdout.flush()
        return default
    return value

if __name__ == "__main__":
    h264_writer()


