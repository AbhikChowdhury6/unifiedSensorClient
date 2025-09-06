import os
import sys
import zmq
import subprocess
from datetime import datetime, timezone
import numpy as np

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec

from config import (
    h264_writer_config,
    zmq_control_endpoint,
)


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


def _spawn_ffmpeg(output_path: str, width: int, height: int, fps: int, duration_s: int, input_pix_fmt: str, crf: int, gop_frames: int):
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "rawvideo",
        "-pix_fmt", input_pix_fmt,
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
        "-t", str(duration_s),
        output_path,
    ]
    # Use Popen with a PIPE for stdin
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def h264_writer():
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)

    # Control channel for graceful exit
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")

    # Subscribe to camera frames
    camera_topic = h264_writer_config["camera_name"]
    camera_endpoint = h264_writer_config["camera_endpoint"]
    sub.connect(camera_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, camera_topic.encode())

    write_location = h264_writer_config["write_location"]
    duration_s = int(h264_writer_config.get("video_duration", 4))
    container = h264_writer_config.get("container_type", "mp4")
    cfg_fps = int(h264_writer_config.get("fps", 8))
    fmt = h264_writer_config.get("format", "RGB888")
    quality = int(h264_writer_config.get("quality", 80))
    crf = _quality_to_crf(quality)
    gop_interval_seconds = int(h264_writer_config.get("keyframe_interval_seconds", 1))
    gop_frames = max(1, cfg_fps * gop_interval_seconds)
    # If there's a long gap between frames, start a new file. Default 2 seconds.
    gap_restart_seconds = float(h264_writer_config.get("frame_gap_restart_seconds", .5))

    os.makedirs(write_location, exist_ok=True)

    pix_fmt = "rgb24" if fmt.upper() in ("RGB888", "RGB24") else "bgr24"
    # Always use software libx264 with CRF

    ffmpeg_proc = None
    frames_written_in_segment = 0
    frames_per_segment = cfg_fps * duration_s
    segment_start_ts = None
    last_ts_seconds = None


    print(f"h264 writer subscribed to {camera_topic} at {camera_endpoint}")
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

        ts, frame = msg[0], msg[1]

        # Normalize timestamp and compute seconds for gap detection
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ts_seconds = ts.timestamp()
        else:
            # assume epoch ns integer
            ts_seconds = ts/1_000_000_000

        # Ensure frame is a contiguous uint8 array in expected shape
        if not isinstance(frame, np.ndarray):
            continue
        if frame.ndim != 3 or frame.shape[2] != 3:
            continue
        if not frame.flags["C_CONTIGUOUS"]:
            frame = np.ascontiguousarray(frame)
        if frame.dtype != np.uint8:
            frame = frame.astype(np.uint8, copy=False)

        # If there's a large break in frames, close current segment
        if ffmpeg_proc is not None and last_ts_seconds is not None:
            if (ts_seconds - last_ts_seconds) > gap_restart_seconds:
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
                print(f"h264 writer detected frame gap {(ts_seconds - last_ts_seconds):.3f}s, starting new file")
                sys.stdout.flush()

        # Detect actual WxH from first frame (in case of subsampling)
        if ffmpeg_proc is None:
            height, width, _ = frame.shape
            frames_per_segment = cfg_fps * duration_s
            segment_start_ts = ts if isinstance(ts, datetime) else datetime.fromtimestamp(ts/1_000_000_000, tz=timezone.utc)
            start_str = _format_ts_for_filename(segment_start_ts)
            # Write into UTC hourly folders: YYYY/MM/DD/HH
            hourly_subdir = segment_start_ts.astimezone(timezone.utc).strftime("%Y/%m/%d/%H")
            out_dir = os.path.join(write_location, hourly_subdir)
            os.makedirs(out_dir, exist_ok=True)
            base_name = f"{camera_topic}_{start_str}.{container}"
            out_path = os.path.join(out_dir, base_name)
            ffmpeg_proc = _spawn_ffmpeg(out_path, width, height, cfg_fps, duration_s, pix_fmt, crf, gop_frames)
            frames_written_in_segment = 0
            print(f"h264 writer started segment {out_path} using libx264 crf {crf}")
            sys.stdout.flush()

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
        last_ts_seconds = ts_seconds

        if frames_written_in_segment >= frames_per_segment:
            # Close current segment
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
            # Next iteration will create a new segment

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


if __name__ == "__main__":
    h264_writer()


