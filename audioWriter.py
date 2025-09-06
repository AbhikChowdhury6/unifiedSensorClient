import os
import sys
import time
import subprocess
from datetime import datetime

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

    output_pattern = f"{output_root}/%Y/%m/%d/%H/{platform_uuid}_audio_%Y-%m-%d_%H-%M-%S.opus"

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
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            bufsize=0
        )
        print("audio: started ffmpeg:", " ".join(cmd))
        sys.stdout.flush()
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

    ff = spawn_ffmpeg_audio_segments_stdin(
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

    if ff is None:
        print("audio writer failed to start ffmpeg; exiting")
        sys.stdout.flush()
        return

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

            # For audio messages, write raw PCM to ffmpeg stdin
            if topic == audio_writer_config["sub_topic"]:
                try:
                    ts, chunk = obj
                    # Ensure numpy array (samples, channels)
                    if not isinstance(chunk, np.ndarray):
                        continue
                    if chunk.ndim == 1:
                        chunk = chunk.reshape((-1, 1))
                    in_samples, in_channels = chunk.shape[0], chunk.shape[1]

                    # Channel conversion
                    if in_channels != channels:
                        if in_channels > channels:
                            # downmix: average first 'channels'
                            chunk = chunk[:, :channels].mean(axis=1, keepdims=True)
                        else:
                            # upmix: duplicate channels
                            chunk = np.repeat(chunk, repeats=channels, axis=1)[:, :channels]

                    # Resample to expected_samples_per_chunk via linear interpolation
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
                        # Back to int16
                        chunk = np.clip(np.rint(chunk), -32768, 32767).astype(np.int16)

                    if chunk.dtype != np.int16:
                        chunk = chunk.astype(np.int16, copy=False)
                    if not chunk.flags["C_CONTIGUOUS"]:
                        chunk = np.ascontiguousarray(chunk)
                    try:
                        ff.stdin.write(chunk.tobytes())
                        ff.stdin.flush()
                    except BrokenPipeError:
                        print("audio writer: ffmpeg pipe closed")
                        sys.stdout.flush()
                        break
                except Exception as e:
                    print(f"audio writer failed to write chunk: {e}")
                    sys.stdout.flush()

            # Check ffmpeg health on each received message
            if ff.poll() is not None:
                print("audio writer: ffmpeg exited with code", ff.returncode)
                sys.stdout.flush()
                break
    finally:
        stop_ffmpeg(ff)
        try:
            sub.close(0)
        except Exception:
            pass


if __name__ == "__main__":
    audio_writer()

