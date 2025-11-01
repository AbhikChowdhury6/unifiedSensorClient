import os
import sys
import time
import subprocess
import threading
from datetime import datetime, timezone, timedelta

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec
from config import audio_writer_process_config, zmq_control_endpoint,\
 dt_to_path, dt_to_fnString, fnString_to_dt
import zmq
import logging
import numpy as np
from logUtils import worker_configurer, set_process_title
import shutil

config = audio_writer_process_config
l = logging.getLogger(config["short_name"])
def audio_writer(log_queue):
    set_process_title(config["short_name"])
    worker_configurer(log_queue, config["debug_lvl"])
    l.info(config["short_name"] + " writer starting")

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    # Subscribe to control
    sub.connect(zmq_control_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"control")
    # Subscribe to audio publisher to drive the loop
    sub.connect(config["sub_endpoint"])
    sub.setsockopt(zmq.SUBSCRIBE, config["sub_topic"].encode())
    l.info(config["short_name"] + " writer subscribed to control and audio publisher topics")
    

    channels = int(config["channels"])
    sample_rate = int(config["sample_rate"])
    frame_hz = float(config["frame_hz"])
    expected_samples_per_chunk = int(round(sample_rate / frame_hz))
    single_sample_micros = int(round(1_000_000 / sample_rate))
    expected_last_sample_micros_offset = int(round(1_000_000 / frame_hz)) - single_sample_micros
    segment_time_s = int(config["duration_s"])


    ff = None
    segment_end = datetime.min.replace(tzinfo=timezone.utc)
    try:
        while True:
            # Block until a message arrives on either control or audio pub topic
            parts = sub.recv_multipart()
            topic, obj = ZmqCodec.decode(parts)
            #print(f"audio writer got message: {topic}")
            #sys.stdout.flush()

            # Check ffmpeg health early in the loop
            if ff is not None and ff.poll() is not None:
                l.error(config["short_name"] + " writer: ffmpeg exited with code " + \
                    str(ff.returncode))

            if topic == "control" and (obj[0] == "exit_all" or 
                    (obj[0] == "exit" and obj[-1] == config["short_name"])):
                l.info(config["short_name"] + " writer exiting")
                break

            # Ignore messages not on the audio topic
            if topic != config["sub_topic"]:
                continue

            # Handle audio message: validate/reshape/resample and write PCM to ffmpeg stdin
            dt, chunk = obj


            # Determine if we should rotate segment based on timestamp
            should_rotate = (dt >= segment_end)
            if should_rotate:
                if ff is not None:
                    stop_ffmpeg(ff, temp_file_name, last_dt, expected_last_sample_micros_offset)
                segment_start, segment_end = aligned_start_end_dt(dt, segment_time_s)
                #add in the file base
                ff, temp_file_name = spawn_ffmpeg_audio_segments_stdin(segment_start)
                if ff is None:
                    break

            # Prepare chunk to target shape/rate
            chunk = _prepare_chunk(chunk, channels, expected_samples_per_chunk)
            if chunk is None:
                continue
            try:
                ff.stdin.write(chunk.tobytes())
                last_dt = dt
            except BrokenPipeError:
                l.error(config["short_name"] + " writer: ffmpeg pipe closed")
                
                # Attempt restart into a new aligned file
                segment_start, segment_end = aligned_start_end_dt(dt, segment_time_s)
                ff, temp_file_name = spawn_ffmpeg_audio_segments_stdin(segment_start)
                if ff is None:
                    break

                ff.stdin.write(chunk.tobytes())
                last_dt = dt

    finally:
        if ff is not None:
            stop_ffmpeg(ff, temp_file_name, dt, expected_last_sample_micros_offset)
        try:
            sub.close(0)
        except Exception:
            pass


def spawn_ffmpeg_audio_segments_stdin(dt: datetime,):
    """Spawn ffmpeg to encode PCM from stdin into Opus segments using config.

    Reads all parameters from audio_writer_config for simplicity.
    Returns a subprocess.Popen handle with stdin PIPE for feeding PCM.
    """
    channels = int(config["channels"])
    sample_rate = int(config["sample_rate"])
    bitrate = str(config["bitrate"])
    application = str(config["application"])
    frame_duration_ms = int(config["frame_duration_ms"])
    segment_time_s = int(config["duration_s"])
    output_root = config["temp_write_location_base"]
    loglevel = str(config["loglevel"])
    sample_fmt = "s16le"
    file_base = config["file_base"]
    temp_file_name = file_base + "_" + dt_to_fnString(dt, 6) + ".opus"

    os.makedirs(output_root, exist_ok=True)
    output_path = output_root + temp_file_name

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", loglevel,
        "-f", sample_fmt,
        "-ac", str(channels),
        "-ar", str(sample_rate),
        "-i", "pipe:0",
        "-c:a", "libopus",
        "-b:a", bitrate,
        "-frame_duration", str(frame_duration_ms),
    ]
    if application:
        cmd += ["-application", application]
    
    # Single-file output; we will close/restart per segment
    cmd += [
        "-t", str(segment_time_s),
        output_path,
    ]

    #standard error reader and running ffmpeg
    try:
        # Force UTC for strftime in ffmpeg so paths match UTC-based folders
        env = os.environ.copy()
        env["TZ"] = "UTC"
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            bufsize=0, env=env
        )
        l.debug(config["short_name"] + " writer: started ffmpeg: " + " ".join(cmd))

        # Start a background stderr reader for diagnostics
        t = threading.Thread(target=_stderr_reader, args=(proc,), daemon=True)
        t.start()
        proc._stderr_thread = t  # attach for lifecycle awareness
        return proc, temp_file_name
    except FileNotFoundError:
        l.error(config["short_name"] + " writer: ffmpeg not found. Please install ffmpeg.")
        return None
    except Exception as e:
        l.error(config["short_name"] + " writer: failed to start ffmpeg: " + str(e))
        return None

def _stderr_reader(p):
    try:
        for raw in iter(p.stderr.readline, b""):
            line = raw.decode(errors="replace").rstrip()
            if line:
                l.debug(config["short_name"] + " writer: ffmpeg stderr: " + line)
    except Exception as e:
        l.error(config["short_name"] + " writer: ffmpeg stderr reader error: " + str(e))
    finally:
        l.debug(config["short_name"] + " writer: ffmpeg stderr: [closed]")


def stop_ffmpeg(proc, file_name, last_chunk_dt, expected_last_sample_micros_offset) -> None:
    l.debug(config["short_name"] + " writer: stopping ffmpeg")
    temp_root = config["temp_write_location_base"]
    completed_root = config["completed_write_location_base"]
    if proc is None:
        return
    first_sample_dt = fnString_to_dt(file_name)
    last_sample_dt = last_chunk_dt + timedelta(microseconds=expected_last_sample_micros_offset)
    l.trace(config["short_name"] + " writer: last sample dt: " + str(last_sample_dt))
    
    # Close stdin first so ffmpeg knows no more data is coming
    try:
        if proc.stdin is not None:
            proc.stdin.close()
    except Exception as e:
        l.warning(config["short_name"] + " writer: error closing ffmpeg stdin: " + str(e))
    
    try:
        proc.terminate()
        proc.wait(timeout=5)
        #rename the file adding the end timestamp
        new_file_name = file_name.replace(".opus", "_" + dt_to_fnString(last_sample_dt, 6) + ".opus")
        os.rename(temp_root + file_name, temp_root + new_file_name)
        new_base_path = dt_to_path(first_sample_dt, completed_root)
        #move from the temp location to the upload location
        shutil.move(temp_root + new_file_name, new_base_path + new_file_name)
        l.debug(config["short_name"] + " writer: moved file from " + temp_root + new_file_name + " to " + new_base_path + new_file_name)

    except subprocess.TimeoutExpired:
        l.warning(config["short_name"] + " writer: ffmpeg did not terminate within timeout, killing")
        try:
            proc.kill()
            proc.wait(timeout=2)  # Give it a moment after kill
        except Exception as e:
            l.error(config["short_name"] + " writer: failed to kill ffmpeg: " + str(e))
    except Exception as e:
        l.error(config["short_name"] + " writer: failed to stop ffmpeg: " + str(e))
        try:
            proc.kill()
            proc.wait(timeout=2)
        except Exception as e2:
            l.error(config["short_name"] + " writer: failed to kill ffmpeg: " + str(e2))


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

def aligned_start_end_dt(ts: datetime, segment_time_s: int) -> tuple[datetime, datetime]:
    aligned_epoch = int(ts.timestamp()) - (int(ts.timestamp()) % segment_time_s)
    return datetime.fromtimestamp(aligned_epoch, tz=timezone.utc), \
        datetime.fromtimestamp(aligned_epoch + segment_time_s, tz=timezone.utc)

if __name__ == "__main__":
    audio_writer(None)

