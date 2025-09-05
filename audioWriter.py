import os
import sys
import time
import subprocess
from datetime import datetime

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec
from config import audio_writer_config, zmq_control_endpoint
import zmq

def ensure_base_dir(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        print(f"audio: failed to create base dir {path}: {e}")
        sys.stdout.flush()


def spawn_ffmpeg_audio_segments(
    alsa_device: str = audio_writer_config["alsa_device"],
    channels: int = 1,
    sample_rate: int = 16000,
    bitrate: str = audio_writer_config["bitrate"],
    application: str = "voip",
    frame_duration_ms: int = 20,
    segment_time_s: int = audio_writer_config["segment_time_s"],
    output_root: str = audio_writer_config["write_location"],
    loglevel: str = audio_writer_config["loglevel"],
):
    """Spawn ffmpeg to capture ALSA audio and write segmented Opus files.

    Returns a subprocess.Popen handle with stdin=None (ffmpeg reads from device).
    """
    ensure_base_dir(output_root)

    output_pattern = f"{output_root}/%Y/%m/%d/%H/audio_%Y-%m-%d_%H-%M-%S.opus"

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", loglevel,
        "-f", "alsa",
        "-ac", str(channels),
        "-ar", str(sample_rate),
        "-i", alsa_device,
        "-c:a", "libopus",
        "-b:a", bitrate,
        "-vbr", "on",
        "-application", application,
        "-frame_duration", str(frame_duration_ms),
        "-f", "segment",
        "-segment_time", str(segment_time_s),
        "-segment_atclocktime", "1",
        "-strftime", "1",
        output_pattern,
    ]

    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
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

    ff = spawn_ffmpeg_audio_segments(
        alsa_device=audio_writer_config["alsa_device"],
        channels=audio_writer_config.get("channels", 1),
        sample_rate=audio_writer_config.get("sample_rate", 16000),
        bitrate=audio_writer_config["bitrate"],
        application=audio_writer_config.get("application", "voip"),
        frame_duration_ms=audio_writer_config.get("frame_duration_ms", 20),
        segment_time_s=audio_writer_config.get("segment_time_s", 4),
        output_root=audio_writer_config["write_location"],
        loglevel=audio_writer_config.get("loglevel", "warning"),
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

            if topic == "control" and obj == "exit":
                print("audio writer exiting")
                sys.stdout.flush()
                break

            # For audio publisher messages, we don't need the payload here since ffmpeg
            # writes directly from ALSA. The message simply drives the loop so we can
            # periodically check ffmpeg health and remain responsive.

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

