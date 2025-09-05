import os
import sys
import subprocess


def ensure_base_dir(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        print(f"audio: failed to create base dir {path}: {e}")
        sys.stdout.flush()


def spawn_ffmpeg_audio_segments(
    alsa_device: str = "plughw:CARD=MICTEST,DEV=0",
    channels: int = 1,
    sample_rate: int = 16000,
    bitrate: str = "16k",
    application: str = "voip",
    frame_duration_ms: int = 20,
    segment_time_s: int = 4,
    output_root: str = "/data/audio",
    loglevel: str = "warning",
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


