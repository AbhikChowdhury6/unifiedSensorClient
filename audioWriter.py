import os
import sys
import time
import subprocess
import threading
from datetime import datetime, timezone, timedelta

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec
from config import audio_writer_config, zmq_control_endpoint, platform_uuid
import zmq
import numpy as np

def ensure_base_dir(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        print(f"audio: failed to create base dir {path}: {e}")
        sys.stdout.flush()


def ensure_hour_dir(root: str, dt_utc: datetime) -> None:
    try:
        hour_dir = os.path.join(root, dt_utc.astimezone(timezone.utc).strftime("%Y/%m/%d/%H"))
        os.makedirs(hour_dir, exist_ok=True)
    except Exception as e:
        print(f"audio: failed to create hour dir {root}: {e}")
        sys.stdout.flush()


def _prepare_chunk(chunk, target_channels: int, expected_samples_per_chunk: int):
    """Validate, channel-match, resample, and return int16 C-contiguous PCM."""
    if not isinstance(chunk, np.ndarray):
        return None
    # Ensure 2D shape (samples, channels)
    if chunk.ndim == 1:
        chunk = chunk.reshape((-1, 1))

    in_samples = int(chunk.shape[0])
    in_channels = int(chunk.shape[1])

    # Channel conversion
    if in_channels != target_channels:
        if in_channels > target_channels:
            # Downmix: average first target channels
            chunk = chunk[:, :target_channels].mean(axis=1, keepdims=True)
        else:
            # Upmix: duplicate channels
            chunk = np.repeat(chunk, repeats=target_channels, axis=1)[:, :target_channels]

    # Resample via linear interpolation to expected samples
    if in_samples != expected_samples_per_chunk:
        x = np.linspace(0, in_samples - 1, num=in_samples, dtype=np.float32)
        xi = np.linspace(0, in_samples - 1, num=expected_samples_per_chunk, dtype=np.float32)
        work = chunk.astype(np.float32, copy=False)
        if work.shape[1] == 1:
            yi = np.interp(xi, x, work.reshape(-1))
            chunk = yi.reshape(-1, 1)
        else:
            cols = [np.interp(xi, x, work[:, c]) for c in range(work.shape[1])]
            chunk = np.stack(cols, axis=1)
        # Convert back to int16
        chunk = np.clip(np.rint(chunk), -32768, 32767).astype(np.int16)

    # Ensure dtype and contiguity
    if chunk.dtype != np.int16:
        chunk = chunk.astype(np.int16, copy=False)
    if not chunk.flags["C_CONTIGUOUS"]:
        chunk = np.ascontiguousarray(chunk)
    return chunk


def spawn_ffmpeg_audio_segments_stdin(
    channels: int = 1,
    sample_rate: int = 16000,
    bitrate: str = audio_writer_config["bitrate"],
    application: str = audio_writer_config["application"],
    frame_duration_ms: int = audio_writer_config["frame_duration_ms"],
    segment_time_s: int = audio_writer_config["segment_time_s"],
    output_root: str = audio_writer_config["write_location"],
    loglevel: str = audio_writer_config["loglevel"],
    sample_fmt: str = "s16le",
):
    """Spawn ffmpeg to capture ALSA audio and write segmented Opus files.

    Returns a subprocess.Popen handle with stdin=None (ffmpeg reads from device).
    """
    ensure_base_dir(output_root)

    output_pattern = f"{output_root}%Y/%m/%d/%H/{platform_uuid}_audio_%Y-%m-%d_%H-%M-%S.opus"

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", loglevel,
        "-fflags", "+genpts",
        "-f", "s16le" if sample_fmt == "s16le" else sample_fmt,
        "-ac", str(channels),
        "-ar", str(sample_rate),
        "-i", "pipe:0",
        "-c:a", "libopus",
        "-b:a", bitrate,
        "-vbr", "on",
        "-application", application,
        "-frame_duration", str(frame_duration_ms),
        "-f", "segment",
        "-segment_time", str(segment_time_s),
        "-strftime", "1",
        output_pattern,
    ]

    try:
        # Force UTC for strftime in ffmpeg so paths match UTC-based folders
        env = os.environ.copy()
        env["TZ"] = "UTC"
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            bufsize=0, env=env
        )
        print("audio: started ffmpeg:", " ".join(cmd))
        sys.stdout.flush()

        # Start a background stderr reader for diagnostics
        def _stderr_reader(p):
            try:
                for raw in iter(p.stderr.readline, b""):
                    line = raw.decode(errors="replace").rstrip()
                    if line:
                        print(f"audio ffmpeg stderr: {line}")
                        sys.stdout.flush()
            except Exception as e:
                print(f"audio ffmpeg stderr reader error: {e}")
                sys.stdout.flush()
            finally:
                print("audio ffmpeg stderr: [closed]")
                sys.stdout.flush()

        t = threading.Thread(target=_stderr_reader, args=(proc,), daemon=True)
        t.start()
        proc._stderr_thread = t  # attach for lifecycle awareness
        return proc
    except FileNotFoundError:
        print("audio: ffmpeg not found. Please install ffmpeg.")
        sys.stdout.flush()
        return None
    except Exception as e:
        print(f"audio: failed to start ffmpeg: {e}")
        sys.stdout.flush()
        return None

def stop_ffmpeg(proc) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def audio_writer():
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    # Subscribe to control
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    # Subscribe to audio publisher to drive the loop
    sub.connect(audio_writer_config["sub_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, audio_writer_config["sub_topic"].encode())
    print("audio writer subscribed to control and audio publisher topics")
    sys.stdout.flush()

    channels = int(audio_writer_config.get("channels", 1))
    sample_rate = int(audio_writer_config.get("sample_rate", 16000))
    target_frame_hz = float(audio_writer_config.get("frame_hz", 16))
    expected_samples_per_chunk = max(1, int(round(sample_rate / target_frame_hz)))
    # Validate frame duration to common Opus values to avoid ffmpeg exit
    requested_fd = audio_writer_config.get("frame_duration_ms", 20)
    try:
        requested_fd = float(requested_fd)
    except Exception:
        requested_fd = 20.0
    valid_fd = [10.0, 20.0, 40.0, 60.0]  # common safe values
    if requested_fd not in valid_fd:
        nearest = min(valid_fd, key=lambda v: abs(v - requested_fd))
        print(f"audio writer: frame_duration_ms {requested_fd} not supported, using {nearest}")
        sys.stdout.flush()
        requested_fd = nearest

    # Pre-create current and next hour directories so strftime path exists
    output_root = audio_writer_config["write_location"]
    now_utc = datetime.now(timezone.utc)
    ensure_hour_dir(output_root, now_utc)
    ensure_hour_dir(output_root, now_utc + timedelta(hours=1))

    def start_ffmpeg():
        return spawn_ffmpeg_audio_segments_stdin(
            channels=channels,
            sample_rate=sample_rate,
            bitrate=audio_writer_config["bitrate"],
            application=audio_writer_config.get("application", "voip"),
            frame_duration_ms=requested_fd,
            segment_time_s=audio_writer_config.get("segment_time_s", 4),
            output_root=audio_writer_config["write_location"],
            loglevel=audio_writer_config.get("loglevel", "warning"),
            sample_fmt="s16le",
        )

    ff = start_ffmpeg()

    if ff is None:
        print("audio writer failed to start ffmpeg; exiting")
        sys.stdout.flush()
        return

    # Track last ensured hour to avoid redundant mkdirs
    last_ensured_hour = now_utc.strftime("%Y%m%d%H")

    try:
        while True:
            # Block until a message arrives on either control or audio pub topic
            parts = sub.recv_multipart()
            topic, obj = ZmqCodec.decode(parts)
            print(f"audio writer got message: {topic}")
            sys.stdout.flush()

            if topic == "control" and obj == "exit":
                print("audio writer exiting")
                sys.stdout.flush()
                break

            # For audio messages, validate/reshape/resample and write PCM to ffmpeg stdin
            if topic == audio_writer_config["sub_topic"]:
                try:
                    ts, chunk = obj
                    # Ensure the current hour directory exists (handles hour rollovers)
                    now_utc = datetime.now(timezone.utc)
                    hour_key = now_utc.strftime("%Y%m%d%H")
                    if hour_key != last_ensured_hour:
                        ensure_hour_dir(output_root, now_utc)
                        ensure_hour_dir(output_root, now_utc + timedelta(hours=1))
                        last_ensured_hour = hour_key
                    # Prepare chunk to target shape/rate
                    chunk = _prepare_chunk(chunk, channels, expected_samples_per_chunk)
                    if chunk is None:
                        continue
                    try:
                        ff.stdin.write(chunk.tobytes())
                    except BrokenPipeError:
                        print("audio writer: ffmpeg pipe closed")
                        sys.stdout.flush()
                        # Attempt restart
                        ff = start_ffmpeg()
                        if ff is None:
                            break
                except Exception as e:
                    print(f"audio writer failed to write chunk: {e}")
                    sys.stdout.flush()

            # Check ffmpeg health on each received message
            if ff.poll() is not None:
                print("audio writer: ffmpeg exited with code", ff.returncode)
                sys.stdout.flush()
                # Attempt restart
                ff = start_ffmpeg()
                if ff is None:
                    break
    finally:
        stop_ffmpeg(ff)
        try:
            sub.close(0)
        except Exception:
            pass


if __name__ == "__main__":
    audio_writer()

